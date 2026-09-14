"""W8 2026-09-14 — toplu sual iş masası: pano (clipboard) / sürükləmə ilə şəkil yapışdırma.

w3import yarımçıq 7 / NIGHT_WAVES §5 maddə 11. Yapışdırılan şəkil DOCX-formatlı
stash bundle-ına (`kind="docx"`, `source.origin="paste"`) düşür; `[[img:N]]`
markeri ilə preview → save mövcud DOCX bağlama kodu ilə işləyir.
"""

from __future__ import annotations

import io
import json
import re
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from PIL import Image

from apps.accounts.models import ProfileRole
from apps.exams.models import BankQuestion, QuestionBank
from apps.exams.services import import_media
from apps.exams.services.import_media_docx import load_docx_manifest
from apps.exams.services.import_media_paste import (
    SOURCE_ORIGIN,
    pasted_image_chips,
    remove_pasted_image,
    stash_pasted_image,
)
from apps.exams.services.import_media_store import bundle_name, default_storage
from apps.exams.services.parsing.docx_reader import MAX_IMAGES
from apps.exams.services.visual_import_upload import prepare_question_upload
from apps.exams.tests.test_w3_import_docx import build_docx
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


def _png(width=40, height=30, color="red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, "PNG")
    return buffer.getvalue()


def _upload(data: bytes = b"", name="paste_1.png") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, data or _png(), content_type="image/png")


class _MediaMixin:
    def _enable_media(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name, MEDIA_URL="/media/")
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.media_directory.cleanup)


class PasteStashServiceTests(_MediaMixin, TestCase):
    def setUp(self):
        self._enable_media()
        self.scope = {"owner_id": 7, "organization_id": 3}

    def test_first_paste_creates_docx_kind_bundle_with_paste_origin(self):
        pasted = stash_pasted_image(_upload(), **self.scope)
        self.assertEqual(len(pasted.token), 32)
        self.assertEqual((pasted.index, pasted.marker), (1, "[[img:1]]"))
        self.assertEqual(pasted.content_type, "image/png")
        self.assertEqual((pasted.width, pasted.height), (40, 30))
        self.assertTrue(pasted.thumb.startswith("data:image/png;base64,"))

        manifest = load_docx_manifest(pasted.token)
        self.assertEqual(manifest["source"]["origin"], SOURCE_ORIGIN)
        self.assertEqual(manifest["source"]["owner_id"], 7)
        self.assertEqual(manifest["source"]["organization_id"], 3)
        self.assertEqual(manifest["canonical_text"], "[[img:1]]")
        [entry] = manifest["images"]
        self.assertEqual(entry["name"], "img_1.png")
        self.assertEqual(entry["origin"], SOURCE_ORIGIN)
        self.assertTrue(default_storage.exists(bundle_name(pasted.token, "img_1.png")))

    def test_second_paste_appends_to_same_bundle(self):
        first = stash_pasted_image(_upload(), **self.scope)
        second = stash_pasted_image(_upload(_png(color="blue")), token=first.token, **self.scope)
        self.assertEqual(second.token, first.token)
        self.assertEqual(second.marker, "[[img:2]]")
        manifest = load_docx_manifest(first.token)
        self.assertEqual([entry["index"] for entry in manifest["images"]], [1, 2])
        self.assertEqual(manifest["canonical_text"], "[[img:1]]\n[[img:2]]")
        self.assertEqual(
            [chip["marker"] for chip in pasted_image_chips(first.token, **self.scope)], ["[[img:1]]", "[[img:2]]"]
        )

    def test_paste_appends_after_docx_document_images(self):
        _text, token = prepare_question_upload(SimpleUploadedFile("q.docx", build_docx(1)), **self.scope)
        pasted = stash_pasted_image(_upload(), token=token, **self.scope)
        self.assertEqual(pasted.token, token)
        self.assertEqual(pasted.index, 2)
        # Çiplər yalnız yapışdırılanları göstərir — sənəd şəkilinin öz kart önizləməsi var.
        self.assertEqual([chip["index"] for chip in pasted_image_chips(token, **self.scope)], [2])
        import_media.clear_stash(token)

    def test_stale_token_starts_a_fresh_bundle(self):
        first = stash_pasted_image(_upload(), **self.scope)
        import_media.clear_stash(first.token)
        again = stash_pasted_image(_upload(), token=first.token, **self.scope)
        self.assertNotEqual(again.token, first.token)
        self.assertEqual(again.index, 1)

    def test_unsupported_bytes_and_oversized_upload_are_rejected(self):
        with self.assertRaises(ValueError):
            stash_pasted_image(_upload(b"not an image at all"), **self.scope)
        big = _upload()
        big.size = 12 * 1024 * 1024 + 1
        with self.assertRaises(ValueError):
            stash_pasted_image(big, **self.scope)
        # Rədd edilən yapışdırma stash qalığı qoymur.
        self.assertFalse(Path(settings.MEDIA_ROOT, "question_imports").exists())

    def test_svg_is_not_a_raster_image(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        with self.assertRaises(ValueError):
            stash_pasted_image(_upload(svg, name="x.svg"), **self.scope)

    def test_image_limit_is_enforced(self):
        first = stash_pasted_image(_upload(), **self.scope)
        manifest = load_docx_manifest(first.token)
        manifest["images"] = [dict(manifest["images"][0], index=i) for i in range(1, MAX_IMAGES + 1)]
        from apps.exams.services.import_media_docx import _write_manifest

        _write_manifest(first.token, manifest)
        with self.assertRaises(ValueError):
            stash_pasted_image(_upload(), token=first.token, **self.scope)

    def test_visual_pdf_bundle_refuses_paste(self):
        token = "a" * 32
        from django.core.files.base import ContentFile

        default_storage.save(
            bundle_name(token, "manifest.json"),
            ContentFile(json.dumps({"schema_version": 2, "source": {"owner_id": 7}}).encode("utf-8")),
        )
        with self.assertRaises(ValueError):
            stash_pasted_image(_upload(), token=token, **self.scope)
        self.assertFalse(default_storage.exists(bundle_name(token, "img_1.png")))

    def test_bundle_is_scoped_to_owner(self):
        pasted = stash_pasted_image(_upload(), **self.scope)
        with self.assertRaises(PermissionDenied):
            stash_pasted_image(_upload(), token=pasted.token, owner_id=8, organization_id=3)
        with self.assertRaises(PermissionDenied):
            remove_pasted_image(pasted.token, 1, owner_id=7, organization_id=4)

    def test_remove_deletes_file_and_clears_bundle_when_empty(self):
        first = stash_pasted_image(_upload(), **self.scope)
        stash_pasted_image(_upload(), token=first.token, **self.scope)
        self.assertEqual(remove_pasted_image(first.token, 1, **self.scope), first.token)
        manifest = load_docx_manifest(first.token)
        self.assertEqual([entry["index"] for entry in manifest["images"]], [2])
        self.assertEqual(manifest["canonical_text"], "[[img:2]]")
        self.assertFalse(default_storage.exists(bundle_name(first.token, "img_1.png")))
        with self.assertRaises(ValueError):
            remove_pasted_image(first.token, 1, **self.scope)
        self.assertEqual(remove_pasted_image(first.token, 2, **self.scope), "")
        self.assertFalse(default_storage.exists(bundle_name(first.token, "manifest.json")))
        self.assertEqual(pasted_image_chips(first.token, **self.scope), [])


class PasteBulkAddFlowTests(_MediaMixin, TestCase):
    """Bank toplu əlavə: yapışdır (JSON) → preview (marker → şəkil bağlı) → save → `image` sahələri."""

    def setUp(self):
        self._enable_media()
        self.teacher = User.objects.create_user(
            username="w8-paste-teacher", email="w8-paste@example.com", password="StrongPass123!"
        )
        self.organization = Organization.objects.create(
            name="W8 Paste Org",
            slug="w8-paste-org",
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
        self.bank = QuestionBank.objects.create(
            name="W8 Paste Bank",
            created_by=self.teacher,
            organization=self.organization,
            default_question_type="test",
        )
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.organization.slug
        session.save()
        self.url = reverse("exams:question_bank_bulk_add", kwargs={"bank_id": self.bank.id})

    def _paste(self, token="", data: bytes = b"", name="paste.png"):
        return self.client.post(
            self.url,
            {"action": "paste_image", "math_token": token, "image": _upload(data, name=name)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_page_enables_paste_only_with_url_and_defer_script(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn(f'data-paste-url="{self.url}"', html)
        self.assertIn('id="wbPasteStrip"', html)
        self.assertIn('id="wb-paste-images"', html)
        self.assertRegex(html, r'<script defer src="[^"]*exams/js/bulk_workbench_paste\.js\?v=\d{8}-\d+"></script>')
        self.assertNotIn("<style", html.split('id="wbPasteStrip"', 1)[1].split("</main>", 1)[0])

    def test_paste_returns_marker_then_preview_binds_and_save_attaches(self):
        first = self._paste()
        self.assertEqual(first.status_code, 200, first.content)
        payload = first.json()
        self.assertTrue(payload["ok"])
        token = payload["token"]
        self.assertEqual(payload["marker"], "[[img:1]]")
        self.assertTrue(payload["thumb"].startswith("data:image/png;base64,"))

        second = self._paste(token=token, data=_png(color="blue")).json()
        self.assertEqual((second["token"], second["marker"]), (token, "[[img:2]]"))

        raw_text = "1. Şəkildəki fiqur nədir? [[img:1]]\nA) dairə [[img:2]]\n*B) kvadrat\nC) üçbucaq\nD) xətt\n"
        preview = self.client.post(
            self.url, {"action": "preview", "raw_text": raw_text, "math_token": token, "language": "az"}
        )
        self.assertEqual(preview.status_code, 200)
        html = preview.content.decode("utf-8")
        [question] = preview.context["parsed"]
        self.assertTrue(question["has_media"])
        self.assertEqual(question["media_slots"], ["A", "stem"])
        self.assertEqual(question["text"], "Şəkildəki fiqur nədir?")
        self.assertEqual(question["options"]["A"], "dairə")
        self.assertIn("q-badge--image", html)
        self.assertIn('class="q-media-preview__img"', html)
        preview_url = reverse("exams:question_import_visual_preview", kwargs={"token": token, "source_index": 0})
        self.assertIn(preview_url, html)
        image = self.client.get(preview_url)
        self.assertEqual(image.status_code, 200)
        self.assertTrue(image.content.startswith(b"\x89PNG"))
        # Çiplər preview POST-dan sonra da bərpa olunur (manifest thumbnail-ləri).
        chips = json.loads(
            re.search(r'<script id="wb-paste-images" type="application/json">(.*?)</script>', html).group(1)
        )
        self.assertEqual([chip["marker"] for chip in chips], ["[[img:1]]", "[[img:2]]"])
        self.assertTrue(all(chip["thumb"].startswith("data:image/png;base64,") for chip in chips))
        self.assertIn(f'name="math_token" value="{token}"', html)

        save = self.client.post(
            self.url,
            {"action": "save", "raw_text": raw_text, "math_token": token, "language": "az", "selected_indices": "1"},
        )
        self.assertEqual(save.status_code, 302)
        [saved] = BankQuestion.objects.filter(bank=self.bank)
        self.assertEqual(saved.text, "Şəkildəki fiqur nədir?")
        self.assertTrue(saved.image)
        self.assertFalse(saved.image_replaces_text)
        self.assertTrue(saved.image.storage.exists(saved.image.name))
        options = {opt.label: opt for opt in saved.options.all()}
        self.assertTrue(options["A"].image)
        self.assertEqual(options["A"].text, "dairə")
        self.assertFalse(options["B"].image)
        self.assertTrue(options["B"].is_correct)
        self.assertFalse(default_storage.exists(bundle_name(token, "manifest.json")))

    def test_remove_action_drops_image_and_clears_token_when_last(self):
        token = self._paste().json()["token"]
        removed = self.client.post(self.url, {"action": "paste_image_remove", "math_token": token, "index": "1"})
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.json(), {"ok": True, "token": "", "index": 1})
        self.assertFalse(default_storage.exists(bundle_name(token, "manifest.json")))

    def test_bad_requests_are_json_400_without_stash_residue(self):
        missing = self.client.post(self.url, {"action": "paste_image", "math_token": ""})
        self.assertEqual(missing.status_code, 400)
        self.assertFalse(missing.json()["ok"])
        garbage = self._paste(data=b"garbage bytes")
        self.assertEqual(garbage.status_code, 400)
        self.assertIn("error", garbage.json())
        bad_index = self.client.post(self.url, {"action": "paste_image_remove", "math_token": "", "index": "x"})
        self.assertEqual(bad_index.status_code, 400)
        wrong_token = self.client.post(self.url, {"action": "paste_image_remove", "math_token": "zz", "index": "1"})
        self.assertEqual(wrong_token.status_code, 400)
        self.assertFalse(Path(settings.MEDIA_ROOT, "question_imports").exists())

    def test_foreign_teacher_cannot_append_to_bundle(self):
        token = self._paste().json()["token"]
        other = User.objects.create_user(username="w8-other", email="w8-other@example.com", password="StrongPass123!")
        profile = other.profile
        profile.organization = self.organization
        profile.organization_type = self.organization.org_type
        profile.role = ProfileRole.TEACHER
        profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
        Membership.objects.update_or_create(
            user=other,
            organization=self.organization,
            defaults={"role": self.organization.roles.get(name="teacher"), "is_primary": True, "is_active": True},
        )
        self.client.force_login(other)
        session = self.client.session
        session["active_organization"] = self.organization.slug
        session.save()
        # Yad müəllim: bank onun deyil → 404 (accessible_banks); token-ə çatmır.
        response = self._paste(token=token)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(load_docx_manifest(token)["images"]), 1)
        import_media.clear_stash(token)

    def test_paste_query_count_is_independent_of_image_count(self):
        token = self._paste().json()["token"]
        with CaptureQueriesContext(connection) as first:
            self._paste(token=token)
        with CaptureQueriesContext(connection) as third:
            self._paste(token=token)
        self.assertEqual(len(first), len(third))
        self.assertLessEqual(len(first), 12, [q["sql"] for q in first])
        import_media.clear_stash(token)


class PasteStaticAssetsTests(SimpleTestCase):
    """JS AJAX-safe (EMSReady, DOMContentLoaded yox) və CSP-uyğun (inline yoxdur)."""

    def test_paste_script_is_ems_ready_and_uses_ems_core(self):
        path = Path(settings.BASE_DIR, "apps/exams/static/exams/js/bulk_workbench_paste.js")
        source = path.read_text(encoding="utf-8")
        self.assertIn("window.EMSReady(function", source)
        self.assertNotIn("DOMContentLoaded", source)
        self.assertIn("EMSCore.fetchJSON", source)
        self.assertIn('"paste_image"', source)
        self.assertIn('"paste_image_remove"', source)
        self.assertNotIn(".style.cssText", source)

    def test_strip_styles_live_in_external_css(self):
        css = Path(settings.BASE_DIR, "apps/exams/static/exams/css/bulk_workbench_rich.css").read_text(encoding="utf-8")
        for selector in (".wb-paste-strip", ".wb-paste-chip", ".custom-editor.is-dragover", ".upload-zone.is-dragover"):
            self.assertIn(selector, css)
