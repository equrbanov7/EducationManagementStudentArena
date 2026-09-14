"""2026-09-14 səhər — pano/sürükləmə ilə şəkil yapışdırma DİGƏR iş masalarında.

NIGHT_WAVES §5 «pano yapışdırma digər bank görünüşlərində». W8 yalnız bank toplu
əlavədə idi; indi `views/teacher/workbench_paste.py` ortaq qolu ilə imtahan dil
meneceri və kafedra göndərişi (yarat / redaktə) də eyni JSON qolunu işlədir.
"""

from __future__ import annotations

import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from PIL import Image

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam
from apps.exams.services.import_media_docx import load_docx_manifest
from apps.exams.services.language_variants import create_variant
from apps.exams.tests.test_question_submission import VALID_TEXT, _Base
from apps.exams.tests.test_w8_paste_images import _MediaMixin
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


def _png(color="blue") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(buffer, "PNG")
    return buffer.getvalue()


def _upload(name="paste.png") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, _png(), content_type="image/png")


def _paste(client, url, token=""):
    return client.post(
        url,
        {"action": "paste_image", "math_token": token, "image": _upload()},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )


class LanguageManagerPasteTests(_MediaMixin, TestCase):
    """İmtahan dil meneceri iş masası: yapışdır → marker; səhifə çipləri bərpa edir."""

    def setUp(self):
        self._enable_media()
        self.teacher = User.objects.create_user(
            username="w9-paste-lang-teacher", email="w9-paste-lang@example.com", password="StrongPass123!"
        )
        self.organization = Organization.objects.create(
            name="W9 Paste Lang Org",
            slug="w9-paste-lang-org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        profile = self.teacher.profile
        profile.organization = self.organization
        profile.organization_type = self.organization.org_type
        profile.role = ProfileRole.TEACHER
        profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
        Membership.objects.update_or_create(
            user=self.teacher,
            organization=self.organization,
            defaults={"role": self.organization.roles.get(name="teacher"), "is_primary": True, "is_active": True},
        )
        self.exam = Exam.objects.create(
            title="W9 Paste Exam", author=self.teacher, organization=self.organization, exam_type="test", is_active=True
        )
        create_variant(self.exam, "ru", display_name="Rus")
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.organization.slug
        session.save()
        self.url = reverse("exams:exam_language_manager", args=[self.exam.slug])

    def test_page_enables_paste_with_own_url(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn(f'data-paste-url="{self.url}"', html)
        self.assertIn('id="wbPasteStrip"', html)
        self.assertIn("exams/js/bulk_workbench_paste.js", html)

    def test_paste_creates_marker_and_preview_restores_chip(self):
        response = _paste(self.client, self.url)
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["marker"], "[[img:1]]")
        manifest = load_docx_manifest(payload["token"])
        self.assertEqual(manifest["source"]["owner_id"], self.teacher.pk)
        self.assertEqual(manifest["source"]["organization_id"], str(self.organization.pk))

        preview = self.client.post(
            self.url,
            {
                "action": "preview",
                "raw_text": "1. Şəkil [[img:1]]\nA) a\nB) b",
                "math_token": payload["token"],
                "language": "ru",
            },
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(len(preview.context["wb_paste_images"]), 1)
        self.assertEqual(preview.context["wb_paste_images"][0]["marker"], "[[img:1]]")

    def test_remove_action_and_bad_index(self):
        token = _paste(self.client, self.url).json()["token"]
        bad = self.client.post(self.url, {"action": "paste_image_remove", "math_token": token, "index": "x"})
        self.assertEqual(bad.status_code, 400)
        removed = self.client.post(self.url, {"action": "paste_image_remove", "math_token": token, "index": "1"})
        self.assertEqual(removed.status_code, 200)
        self.assertTrue(removed.json()["ok"])

    def test_paste_action_does_not_leak_to_other_post_branches(self):
        # Yapışdırma qolu `add_variant` və s. əməllərdən əvvəl qayıdır; şəkilsiz 400.
        response = self.client.post(self.url, {"action": "paste_image", "math_token": ""})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertEqual(self.exam.language_variants.count(), 1)


class SubmissionWorkbenchPasteTests(_MediaMixin, _Base):
    """Kafedra göndərişi yarat / redaktə: eyni qol; redaktə hüququ olmayan 403."""

    def setUp(self):
        super().setUp()
        self._enable_media()

    def test_create_page_enables_paste_and_accepts_image(self):
        client = self._client_for(self.teacher)
        url = reverse("exams:question_submission_create")
        page = client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertIn(f'data-paste-url="{url}"', page.content.decode("utf-8"))

        response = _paste(client, url)
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["index"], 1)
        manifest = load_docx_manifest(payload["token"])
        self.assertEqual(manifest["source"]["organization_id"], str(self.org.pk))

    def test_detail_page_paste_requires_edit_right(self):
        submission = self._submission(raw_text=VALID_TEXT)
        url = reverse("exams:question_submission_detail", kwargs={"submission_id": submission.pk})

        owner_client = self._client_for(self.teacher)
        page = owner_client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertIn(f'data-paste-url="{url}"', page.content.decode("utf-8"))
        response = _paste(owner_client, url)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["ok"])

        # Mərkəz göndərişi kafedra təsdiqindən əvvəl görmür (404) — yapışdıra da bilməz.
        center_client = self._client_for(self.exam_center)
        self.assertEqual(_paste(center_client, url).status_code, 404)

        # Kafedra təsdiqindən sonra mərkəz görür, amma redaktə edə bilməz → 403.
        self._to_center(submission)
        self.assertEqual(_paste(center_client, url).status_code, 403)
