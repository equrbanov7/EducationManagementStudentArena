"""PERF-2 H5 (2026-10-17): avatar yükləmədə kiçildilir, versiyalı URL uzun keşlənir.

* JSON API və köhnə «update-avatar» / «Profili redaktə et» forma yolları şəkli ≤512 px
  WebP-yə çevirir; EXIF oriyentasiyası tətbiq olunur, metadata atılır; şəffaflıq qalır.
* Emal alınmayan (yoxlamadan keçmiş) fayl orijinal kimi saxlanılır.
* ``accounts:profile_avatar``: ``?v=`` cari versiyadırsa ``max-age=31536000, immutable``,
  versiyasız / köhnə versiyada ``max-age=300``; hər halda ``private``.
* ``shrink_avatars`` defolt quru qaçışdır; ``--apply`` yeni fayla yönəldir, köhnəni saxlayır.
* Review: piksel tavanı (dekompressiya «bombası») dekoddan ƏVVƏL rədd edilir; ICC saxlanılır;
  ``?v=`` mikrosaniyə dəqiqliyindədir; skip qaydası formatdan asılı deyil.
"""

import io
import shutil
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from PIL import Image

from apps.accounts.models import UserProfile
from apps.accounts.services.avatar_image import (
    AVATAR_MAX_PIXELS,
    AVATAR_MAX_SIDE,
    AVATAR_PIXELS_ERROR,
    AvatarImageError,
    avatar_version,
    encode_avatar_bytes,
    normalize_avatar_upload,
)
from apps.accounts.services.profile_actions import validate_profile_avatar_upload

User = get_user_model()


def _image_bytes(size=(2000, 1200), mode="RGB", fmt="PNG", exif_orientation=None):
    buffer = io.BytesIO()
    color = (20, 120, 200, 128) if mode == "RGBA" else (20, 120, 200)
    image = Image.new(mode, size, color)
    kwargs = {}
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        kwargs["exif"] = exif.tobytes()
    image.save(buffer, format=fmt, **kwargs)
    return buffer.getvalue()


def _upload(name="big.png", **kwargs):
    content_type = "image/jpeg" if name.endswith(".jpg") else "image/png"
    return SimpleUploadedFile(name, _image_bytes(**kwargs), content_type=content_type)


def _open(data_or_file):
    if hasattr(data_or_file, "read"):
        data_or_file.seek(0)
        data_or_file = data_or_file.read()
    return Image.open(io.BytesIO(data_or_file))


class NormalizeAvatarUploadTest(SimpleTestCase):
    def test_large_png_becomes_small_webp(self):
        result = normalize_avatar_upload(_upload())
        self.assertTrue(result.name.endswith(".webp"))
        image = _open(result)
        self.assertEqual(image.format, "WEBP")
        self.assertEqual(max(image.size), AVATAR_MAX_SIDE)
        self.assertEqual(image.size, (512, 307))  # nisbət saxlanılır

    def test_small_image_is_not_upscaled(self):
        image = _open(normalize_avatar_upload(_upload(size=(64, 48))))
        self.assertEqual(image.size, (64, 48))

    def test_exif_orientation_applied_and_metadata_dropped(self):
        upload = _upload("phone.jpg", size=(800, 400), fmt="JPEG", exif_orientation=6)  # 90° döndər
        image = _open(normalize_avatar_upload(upload))
        self.assertEqual(image.size, (256, 512))
        self.assertNotIn(0x0112, image.getexif())

    def test_transparency_is_kept(self):
        image = _open(normalize_avatar_upload(_upload(mode="RGBA", size=(600, 600))))
        self.assertEqual(image.mode, "RGBA")

    def test_unreadable_file_falls_back_to_original(self):
        upload = SimpleUploadedFile("x.png", b"not-an-image", content_type="image/png")
        with self.assertLogs("apps.accounts.services.avatar_image", level="WARNING"):
            self.assertIs(normalize_avatar_upload(upload), upload)


def _bomb_png():
    """Kiçik fayl, nəhəng ölçü: 1-bit 7000×6000 = 42M piksel (tavan 40M) — ~10 KB PNG."""
    buffer = io.BytesIO()
    Image.new("1", (7000, 6000), 0).save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


class AvatarPixelCapTest(SimpleTestCase):
    def test_validation_rejects_huge_dimensions_before_decoding(self):
        data = _bomb_png()
        self.assertLess(len(data), 200 * 1024)
        upload = SimpleUploadedFile("bomb.png", data, content_type="image/png")
        self.assertEqual(validate_profile_avatar_upload(upload), AVATAR_PIXELS_ERROR)

    def test_encoder_refuses_instead_of_storing_the_original(self):
        with self.assertRaises(AvatarImageError):
            encode_avatar_bytes(io.BytesIO(_bomb_png()))
        upload = SimpleUploadedFile("bomb.png", _bomb_png(), content_type="image/png")
        with self.assertRaises(AvatarImageError):
            normalize_avatar_upload(upload)

    def test_cap_boundary(self):
        self.assertGreater(7000 * 6000, AVATAR_MAX_PIXELS)
        upload = _upload(size=(4000, 3000))  # 12M — keçir
        self.assertEqual(validate_profile_avatar_upload(upload), "")


class AvatarIccAndVersionTest(SimpleTestCase):
    def test_icc_profile_is_kept(self):
        from PIL import ImageCms

        icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        buffer = io.BytesIO()
        Image.new("RGB", (900, 900), (10, 20, 30)).save(buffer, format="JPEG", icc_profile=icc)
        image = _open(encode_avatar_bytes(io.BytesIO(buffer.getvalue())))
        self.assertEqual(image.info.get("icc_profile"), icc)

    def test_version_has_microsecond_precision(self):
        from datetime import datetime, timedelta, timezone

        first = datetime(2026, 10, 17, 12, 0, 0, 100, tzinfo=timezone.utc)
        second = first + timedelta(microseconds=1)
        self.assertNotEqual(avatar_version(first), avatar_version(second))
        self.assertEqual(avatar_version(first), str(int(first.timestamp()) * 1_000_000 + 100))
        self.assertEqual(avatar_version(None), "")


class _MediaTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp(prefix="avatar_perf_media_")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)

    def setUp(self):
        self.user = User.objects.create_user(username="avperf", email="avperf@example.com", password="testpass123")
        self.client.force_login(self.user)


class AvatarUploadPathsTest(_MediaTestCase):
    def _stored(self):
        profile = UserProfile.objects.get(user=self.user)
        with default_storage.open(profile.avatar.name, "rb") as handle:
            return profile.avatar.name, Image.open(io.BytesIO(handle.read()))

    def test_json_api_stores_downscaled_webp(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("accounts:profile_avatar_api"), {"action": "upload", "avatar": _upload()}
            )
        self.assertEqual(response.status_code, 200, response.content)
        name, image = self._stored()
        self.assertTrue(name.startswith("avatars/") and name.endswith(".webp"), name)
        self.assertNotIn("big", name)  # ad yenə təsadüfidir
        self.assertEqual((image.format, max(image.size)), ("WEBP", AVATAR_MAX_SIDE))

    def test_json_api_rejects_a_decompression_bomb_and_stores_nothing(self):
        upload = SimpleUploadedFile("bomb.png", _bomb_png(), content_type="image/png")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("accounts:profile_avatar_api"), {"action": "upload", "avatar": upload})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], AVATAR_PIXELS_ERROR)
        self.assertFalse(UserProfile.objects.get(user=self.user).avatar)

    def test_legacy_update_avatar_form_stores_downscaled_webp(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("accounts:profile"), {"profile_form": "update-avatar", "avatar": _upload()})
        name, image = self._stored()
        self.assertTrue(name.endswith(".webp"), name)
        self.assertLessEqual(max(image.size), AVATAR_MAX_SIDE)


class AvatarCacheHeaderTest(_MediaTestCase):
    def setUp(self):
        super().setUp()
        profile = UserProfile.objects.get(user=self.user)
        profile.avatar = default_storage.save("avatars/avperf.webp", ContentFile(_image_bytes((40, 40), fmt="WEBP")))
        profile.save(update_fields=["avatar", "updated_at"])
        self.version = avatar_version(UserProfile.objects.get(pk=profile.pk).updated_at)
        self.url = reverse("accounts:profile_avatar", args=[self.user.id])

    def test_current_version_is_cached_immutably(self):
        response = self.client.get(f"{self.url}?v={self.version}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, max-age=31536000, immutable")
        self.assertEqual(response["Content-Type"], "image/webp")

    def test_unversioned_or_stale_version_keeps_short_cache(self):
        seconds = self.version[:-6]  # köhnə (saniyə) formatı da qısa keşdə qalır
        for query in ("", "?v=1", f"?v={seconds}"):
            with self.subTest(query=query):
                response = self.client.get(self.url + query)
                self.assertEqual(response["Cache-Control"], "private, max-age=300")


class ShrinkAvatarsCommandTest(_MediaTestCase):
    def setUp(self):
        super().setUp()
        self.profile = UserProfile.objects.get(user=self.user)
        self.original = default_storage.save("avatars/old_big.png", ContentFile(_image_bytes((1600, 1600))))
        UserProfile.objects.filter(pk=self.profile.pk).update(avatar=self.original)

    def _run(self, *args):
        out = StringIO()
        call_command("shrink_avatars", *args, stdout=out, stderr=StringIO())
        return out.getvalue()

    def test_default_is_a_dry_run(self):
        output = self._run()
        self.assertIn("QURU QAÇIŞ", output)
        self.assertEqual(UserProfile.objects.get(pk=self.profile.pk).avatar.name, self.original)

    def test_apply_repoints_and_keeps_the_original_file(self):
        before = UserProfile.objects.get(pk=self.profile.pk).updated_at
        self._run("--apply")
        profile = UserProfile.objects.get(pk=self.profile.pk)
        self.assertNotEqual(profile.avatar.name, self.original)
        self.assertTrue(profile.avatar.name.endswith(".webp"))
        self.assertEqual(profile.updated_at, before)
        self.assertTrue(default_storage.exists(self.original))
        self._run("--apply")  # təkrar qaçış artıq kiçik faylı ötürür
        self.assertEqual(UserProfile.objects.get(pk=self.profile.pk).avatar.name, profile.avatar.name)

    def test_delete_originals_removes_the_old_file(self):
        self._run("--apply", "--delete-originals")
        self.assertFalse(default_storage.exists(self.original))

    def test_small_light_file_is_skipped_whatever_its_format(self):
        small = default_storage.save("avatars/small.png", ContentFile(_image_bytes((128, 128))))
        UserProfile.objects.filter(pk=self.profile.pk).update(avatar=small)
        self.assertIn("ötürülən 1", self._run("--apply"))
        self.assertEqual(UserProfile.objects.get(pk=self.profile.pk).avatar.name, small)

    def test_oversized_dimensions_are_reported_and_left_alone(self):
        bomb = default_storage.save("avatars/bomb.png", ContentFile(_bomb_png()))
        UserProfile.objects.filter(pk=self.profile.pk).update(avatar=bomb)
        self.assertIn("xəta 1", self._run("--apply"))
        self.assertEqual(UserProfile.objects.get(pk=self.profile.pk).avatar.name, bomb)
