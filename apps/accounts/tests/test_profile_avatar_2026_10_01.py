"""Profil şəkli — yerində yüklə / dəyiş / sil (2026-10-01, sahib).

accounts:profile_avatar_api: yükləmə, əvəzləmə (köhnə fayl silinir), silmə
(baş hərflərə qayıdış), rədd edilən tiplər/ölçü, audit, view-as bloku, və
köhnə `update-avatar` forma yolunun da köhnə faylı silməsi.
"""

import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from PIL import Image

User = get_user_model()


def _png(name="avatar.png", size=(32, 32)):
    buffer = io.BytesIO()
    Image.new("RGB", size, (20, 120, 200)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class ProfileAvatarApiTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp(prefix="avatar_media_")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)

    def setUp(self):
        self.user = User.objects.create_user(
            username="avatar10",
            email="avatar10@example.com",
            password="testpass123",
            first_name="Elvin",
            last_name="Qurbanov",
        )
        self.url = reverse("accounts:profile_avatar_api")
        self.client.force_login(self.user)

    def _post(self, **data):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.url, data=data)

    def test_requires_login_and_post(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.url, {"action": "remove"}).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_upload_sets_avatar_and_returns_state(self):
        from apps.audit.models import AuditLog

        response = self._post(action="upload", avatar=_png())
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertTrue(payload["has_avatar"])
        self.assertTrue(payload["avatar_url"].startswith(reverse("accounts:profile_avatar", args=[self.user.id])))
        self.assertIn("?v=", payload["avatar_url"])
        self.assertEqual(payload["initials"], "EQ")
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.avatar.name.startswith("avatars/"))
        self.assertNotIn("avatar.png", self.user.profile.avatar.name)  # təsadüfi ad
        self.assertTrue(default_storage.exists(self.user.profile.avatar.name))
        log = AuditLog.objects.get(user=self.user, resource_type="UserProfileAvatar")
        self.assertEqual(log.changes, {"avatar": "uploaded"})
        # Serve route şəkli verir.
        served = self.client.get(payload["avatar_url"])
        self.assertEqual(served.status_code, 200)
        b"".join(served.streaming_content)

    def test_replace_deletes_old_file(self):
        self._post(action="upload", avatar=_png("a.png"))
        self.user.profile.refresh_from_db()
        old_name = self.user.profile.avatar.name
        response = self._post(action="upload", avatar=_png("b.png", size=(40, 40)))
        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertNotEqual(self.user.profile.avatar.name, old_name)
        self.assertTrue(default_storage.exists(self.user.profile.avatar.name))
        self.assertFalse(default_storage.exists(old_name))

    def test_remove_deletes_file_and_falls_back_to_initials(self):
        from apps.audit.models import AuditLog

        self._post(action="upload", avatar=_png())
        self.user.profile.refresh_from_db()
        old_name = self.user.profile.avatar.name
        response = self._post(action="remove")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["has_avatar"])
        self.assertEqual(payload["avatar_url"], "")
        self.assertEqual(payload["initial"], "E")
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.avatar)
        self.assertFalse(default_storage.exists(old_name))
        self.assertTrue(AuditLog.objects.filter(resource_type="UserProfileAvatar", action="delete").exists())
        # Şəkil yoxkən ikinci silmə zərərsizdir.
        self.assertEqual(self._post(action="remove").status_code, 200)

    def test_rejected_types_and_oversize(self):
        bad_uploads = [
            SimpleUploadedFile("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", content_type="image/svg+xml"),
            SimpleUploadedFile("x.png", b"<html><script>alert(1)</script></html>", content_type="image/png"),
            SimpleUploadedFile("x.pdf", b"%PDF-1.4", content_type="application/pdf"),
            SimpleUploadedFile("x.png", b"\x89PNG\r\n\x1a\n" + b"0" * (10 * 1024 * 1024), content_type="image/png"),
        ]
        for upload in bad_uploads:
            with self.subTest(name=upload.name, size=upload.size):
                response = self._post(action="upload", avatar=upload)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()["success"])
        self.assertEqual(self._post(action="upload").status_code, 400)  # fayl yoxdur
        self.assertEqual(self._post(action="bogus").status_code, 400)
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.avatar)

    def test_legacy_update_avatar_form_also_deletes_old_file(self):
        self._post(action="upload", avatar=_png("a.png"))
        self.user.profile.refresh_from_db()
        old_name = self.user.profile.avatar.name
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("accounts:profile"),
                {"profile_form": "update-avatar", "section": "profile-info", "avatar": _png("c.png")},
            )
        self.assertEqual(response.status_code, 302)
        self.user.profile.refresh_from_db()
        self.assertNotEqual(self.user.profile.avatar.name, old_name)
        self.assertFalse(default_storage.exists(old_name))

    def test_profile_pages_render_avatar_widget(self):
        response = self.client.get(reverse("accounts:profile") + "?section=profile-info")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("data-avatar-scope", html)
        self.assertIn(self.url, html)
        self.assertIn("profile_avatar.js", html)
        self.assertIn("data-avatar-remove-wrap hidden", html)  # şəkil yoxdur → «Sil» gizli
        response = self.client.get(reverse("accounts:profile") + "?section=edit-profile")
        html = response.content.decode()
        self.assertIn('class="avatar-editor"', html)
        self.assertNotIn('name="avatar"', html)  # əsas forma şəkli GÖNDƏRMİR

    def test_view_as_blocks_avatar_api(self):
        from apps.accounts.middleware import ViewAsMiddleware

        self.assertIn("accounts:profile_avatar_api", ViewAsMiddleware.BLOCKED_URL_NAMES)
