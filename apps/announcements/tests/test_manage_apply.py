"""Elanlar — idarə əhatəsi, «Müraciət et» marşrutu/təkrarsızlığı, sənəd yoxlaması, icazə kataloqu."""

from __future__ import annotations

import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.announcements.forms import safe_apply_url
from apps.announcements.models import Announcement, AnnouncementAttachment, AnnouncementReceipt
from apps.applications.models import Application, ApplicationKind, ApplicationUnit
from core.rls import bypass_rls

from .world import build_world, client_for, days, make_announcement

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _post_form(client, url, **overrides):
    data = {
        "title": "Dekanlıq elanı",
        "summary": "Qısa",
        "body": "Mətn",
        "category": "general",
        "priority": "0",
        "audience_families": ["students"],
        "apply_mode": "none",
        "then": "save",
    }
    data.update(overrides)
    return client.post(url, data)


class ScopedManagerTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annsc")

    def test_dean_can_target_own_faculty(self):
        client = client_for(self.w["org"], self.w["dean"])
        response = _post_form(client, reverse("announcements:manage_create"), audience_units=[str(self.w["g1"].pk)])
        self.assertEqual(response.status_code, 302)
        with bypass_rls():
            item = Announcement.objects.get(title="Dekanlıq elanı")
        self.assertEqual(item.audience_units, [str(self.w["g1"].pk)])

    def test_dean_cannot_target_other_faculty(self):
        client = client_for(self.w["org"], self.w["dean"])
        response = _post_form(client, reverse("announcements:manage_create"), audience_units=[str(self.w["g2"].pk)])
        self.assertEqual(response.status_code, 200)
        self.assertIn("əhatənizdən kənardadır", response.content.decode())
        with bypass_rls():
            self.assertFalse(Announcement.objects.filter(title="Dekanlıq elanı").exists())

    def test_dean_cannot_target_whole_organization(self):
        client = client_for(self.w["org"], self.w["dean"])
        response = _post_form(client, reverse("announcements:manage_create"))
        self.assertEqual(response.status_code, 200)
        with bypass_rls():
            self.assertFalse(Announcement.objects.filter(title="Dekanlıq elanı").exists())

    def test_dean_cannot_edit_org_wide_announcement(self):
        item = make_announcement(self.w, title="Rektorluq elanı")
        client = client_for(self.w["org"], self.w["dean"])
        self.assertEqual(client.get(reverse("announcements:manage_edit", args=[item.pk])).status_code, 404)
        response = client.post(reverse("announcements:manage_action", args=[item.pk]), {"action": "archive"})
        self.assertEqual(response.status_code, 404)

    def test_teacher_has_no_manage_access(self):
        client = client_for(self.w["org"], self.w["t1"])
        self.assertEqual(_post_form(client, reverse("announcements:manage_create")).status_code, 403)

    def test_owner_targets_whole_org_and_publishes(self):
        client = client_for(self.w["org"], self.w["owner"])
        response = _post_form(client, reverse("announcements:manage_create"), then="publish", show_as_popup="1")
        self.assertEqual(response.status_code, 302)
        with bypass_rls():
            item = Announcement.objects.get(title="Dekanlıq elanı")
            self.w["org"].refresh_from_db()
        self.assertEqual(item.status, "published")
        self.assertIsNotNone(item.publish_at)
        from apps.announcements.services.snapshot import active_items

        self.assertEqual([entry["id"] for entry in active_items(self.w["org"])], [str(item.pk)])

    def test_manage_rows_fragment_search(self):
        make_announcement(self.w, title="Kitabxana saatları")
        make_announcement(self.w, title="Tədbir dəvəti", category="event")
        client = client_for(self.w["org"], self.w["owner"])
        payload = client.get(reverse("announcements:manage_rows"), {"q": "kitabxana"}).json()
        self.assertEqual(payload["total"], 1)
        self.assertIn("Kitabxana saatları", payload["html"])

    def test_draft_delete_and_archive(self):
        draft = make_announcement(self.w, title="Silinəcək", publish=False)
        client = client_for(self.w["org"], self.w["owner"])
        client.post(reverse("announcements:manage_action", args=[draft.pk]), {"action": "delete"})
        with bypass_rls():
            self.assertFalse(Announcement.objects.filter(pk=draft.pk).exists())
        live = make_announcement(self.w, title="Arxivlənəcək")
        client.post(reverse("announcements:manage_action", args=[live.pk]), {"action": "archive"})
        with bypass_rls():
            self.assertEqual(Announcement.objects.get(pk=live.pk).status, "archived")
        # Dərc olunmuş/arxivdəki elan da silinir — yumşaq (sətir qalır), bax test_delete.py.
        client.post(reverse("announcements:manage_action", args=[live.pk]), {"action": "delete"})
        with bypass_rls():
            self.assertTrue(Announcement.objects.get(pk=live.pk).is_deleted)

    def test_published_edit_with_cleared_publish_time_and_past_expiry_is_a_form_error(self):
        # Review 2026-10-07: dərc olunmuş elanda «Dərc vaxtı» boşaldılıb «Bitmə vaxtı» keçmişə
        # qoyulanda servis `publish_at = indi` qoyurdu → `ann_window_ordered` CHECK-i → 500.
        live = make_announcement(self.w, title="Pəncərəsi pozulan")
        client = client_for(self.w["org"], self.w["owner"])
        past = days(-1).astimezone(timezone.get_current_timezone()).strftime("%Y-%m-%dT%H:%M")
        response = _post_form(
            client,
            reverse("announcements:manage_edit", args=[live.pk]),
            title="Pəncərəsi pozulan",
            publish_at="",
            expires_at=past,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("dərc vaxtından sonra olmalıdır", response.content.decode())
        with bypass_rls():
            live.refresh_from_db()
        self.assertIsNone(live.expires_at)


class ApplyTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annap")
        with bypass_rls():
            cls.kind = ApplicationKind.objects.get(organization=cls.w["org"], code="arayis")
            cls.dean_unit = ApplicationUnit.objects.get(organization=cls.w["org"], code="dekan")
        cls.item = make_announcement(
            cls.w,
            title="Təqaüd müsabiqəsi",
            apply_mode="internal",
            apply_kind=cls.kind.pk,
            apply_unit=cls.dean_unit.pk,
            deadline_at=days(5),
        )

    def test_apply_creates_exactly_one_application_routed_to_unit(self):
        client = client_for(self.w["org"], self.w["s1"])
        url = reverse("announcements:apply", args=[self.item.pk])
        first = client.post(url, data=json.dumps({"note": "Sənədlərim hazırdır."}), content_type="application/json")
        self.assertEqual(first.status_code, 200, first.content)
        self.assertTrue(first.json()["created"])
        second = client.post(url, data=json.dumps({}), content_type="application/json")
        self.assertFalse(second.json()["created"])
        self.assertEqual(second.json()["number"], first.json()["number"])
        with bypass_rls():
            applications = list(Application.objects.filter(organization=self.w["org"], created_by=self.w["s1"]))
            receipt = AnnouncementReceipt.objects.get(user=self.w["s1"], announcement=self.item)
        self.assertEqual(len(applications), 1)
        application = applications[0]
        self.assertEqual(application.kind_id, self.kind.pk)
        self.assertEqual(application.current_unit_id, self.dean_unit.pk)
        self.assertIn("Təqaüd müsabiqəsi", application.subject)
        self.assertIn("Sənədlərim hazırdır.", application.body)
        self.assertEqual(receipt.application_id, application.pk)
        self.assertIsNotNone(receipt.applied_at)
        detail = client.get(f"/accounts/profile/?section=announcements&elan={self.item.pk}").content.decode()
        self.assertIn(application.number, detail)
        # Siyahı kartı müraciət edildiyini göstərir («mümkündür» yox).
        listing = client.get(reverse("announcements:list")).json()["html"]
        self.assertIn("Müraciət edilib", listing)
        self.assertNotIn("Müraciət mümkündür", listing)

    def test_apply_after_deadline_is_closed(self):
        with bypass_rls():
            Announcement.objects.filter(pk=self.item.pk).update(publish_at=days(-10), deadline_at=days(-1))
        client = client_for(self.w["org"], self.w["s2"])
        response = client.post(reverse("announcements:apply", args=[self.item.pk]))
        self.assertEqual(response.status_code, 409)
        with bypass_rls():
            self.assertFalse(Application.objects.filter(created_by=self.w["s2"]).exists())

    def test_kind_must_be_open_to_audience(self):
        """«Arayış» yalnız tələbə növüdür — müəllim auditoriyası ilə forma rədd olunur."""
        from apps.announcements.forms import AnnouncementForm

        form = AnnouncementForm(
            {
                "title": "Müəllimlərə",
                "category": "general",
                "priority": "0",
                "audience_families": ["teachers"],
                "apply_mode": "internal",
                "apply_kind": str(self.kind.pk),
            },
            organization=self.w["org"],
        )
        self.assertFalse(form.is_valid())
        self.assertIn("apply_kind", form.errors)

    def test_url_mode_records_click_once(self):
        item = make_announcement(
            self.w, title="Qeydiyyat formu", apply_mode="url", apply_url="https://forms.example.org/x"
        )
        client = client_for(self.w["org"], self.w["s1"])
        payload = client.post(reverse("announcements:apply", args=[item.pk])).json()
        self.assertEqual(payload["redirect"], "https://forms.example.org/x")
        client.post(reverse("announcements:apply", args=[item.pk]))
        with bypass_rls():
            self.assertEqual(AnnouncementReceipt.objects.filter(announcement=item, applied_at__isnull=False).count(), 1)


class AttachmentTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annat")
        cls.item = make_announcement(cls.w, title="Sənədli elan", units=[cls.w["f1"].pk])

    def _upload(self, name, content, content_type):
        client = client_for(self.w["org"], self.w["owner"])
        data = {
            "title": "Sənədli elan",
            "category": "exam",
            "priority": "0",
            "audience_families": ["students"],
            "audience_units": [str(self.w["f1"].pk)],
            "apply_mode": "none",
            "files": SimpleUploadedFile(name, content, content_type=content_type),
        }
        return client.post(reverse("announcements:manage_edit", args=[self.item.pk]), data)

    def test_dangerous_files_rejected(self):
        for name, content, ctype in (
            ("virus.exe", b"MZ\x90\x00", "application/octet-stream"),
            ("page.html", b"<html><script>alert(1)</script></html>", "text/html"),
            ("fake.pdf", b"<html><script>alert(1)</script></html>", "application/pdf"),
        ):
            with self.subTest(name=name):
                response = self._upload(name, content, ctype)
                self.assertEqual(response.status_code, 200)
                with bypass_rls():
                    self.assertFalse(AnnouncementAttachment.objects.filter(announcement=self.item).exists())

    def test_pdf_accepted_and_download_is_gated(self):
        response = self._upload("cedvel.pdf", PDF, "application/pdf")
        self.assertEqual(response.status_code, 302)
        with bypass_rls():
            attachment = AnnouncementAttachment.objects.get(announcement=self.item)
        url = reverse("announcements:attachment_download", args=[self.item.pk, attachment.pk])
        ok = client_for(self.w["org"], self.w["s1"]).get(url)
        self.assertEqual(ok.status_code, 200)
        self.assertIn("attachment", ok["Content-Disposition"])
        self.assertEqual(ok["X-Content-Type-Options"], "nosniff")
        self.assertEqual(client_for(self.w["org"], self.w["s2"]).get(url).status_code, 404)


class SafeUrlTest(SimpleTestCase):
    def test_only_http_https_and_same_site_paths(self):
        self.assertEqual(safe_apply_url("https://a.example/x?y=1"), "https://a.example/x?y=1")
        self.assertEqual(safe_apply_url("/muracietler/"), "/muracietler/")
        for bad in ("javascript:alert(1)", "//evil.example/x", "data:text/html,1", "ftp://x", "https:///x", "/a b", ""):
            with self.subTest(bad=bad):
                self.assertIsNone(safe_apply_url(bad))


class PermissionCatalogTest(TestCase):
    def test_permission_in_catalog_and_granted_to_dean_template(self):
        from apps.organizations.default_roles_university import UNIVERSITY_ROLES
        from apps.organizations.permissions import PERMISSION_CATEGORIES, PERMISSION_LABELS

        self.assertIn("announcement.manage", PERMISSION_CATEGORIES["announcement"])
        self.assertIn("announcement.manage", PERMISSION_LABELS)
        roles = {role["name"]: role for role in UNIVERSITY_ROLES}
        for name in ("dean", "vice_dean", "chair_head", "teaching_office_head", "student_services", "vice_rector"):
            self.assertIn("announcement.manage", roles[name]["permissions"], name)
        self.assertNotIn("announcement.manage", roles["student"]["permissions"])
        self.assertNotIn("announcement.manage", roles["teacher"]["permissions"])
