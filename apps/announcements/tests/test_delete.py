"""Elanın silinməsi (sahib, 2026-10-07): qəbzsiz qaralama → birdəfəlik; qalanı yumşaq silmə.

Yumşaq silinmiş elan istifadəçi səthlərinin HAMISINDAN çıxır (siyahı, detal, popup, sayğac,
oxundu, müraciət, sənəd), menecer «Silinmişlər» filtrində görür və bərpa edir (→ qaralama).
Əhatəli menecer (dekan) yalnız redaktə edə bildiyini silə bilər.
"""

from __future__ import annotations

import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.announcements.constants import SNAPSHOT_KEY
from apps.announcements.models import Announcement, AnnouncementAttachment, AnnouncementReceipt
from apps.announcements.services import apply as apply_service
from apps.announcements.services import snapshot
from apps.announcements.services.popup import badge_count
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, Organization
from core.rls import bypass_rls

from .world import build_world, client_for, make_announcement

CABINET = "/accounts/profile/?section=announcements"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "ann-delete"}}


def _action(client, item, action):
    return client.post(reverse("announcements:manage_action", args=[item.pk]), {"action": action})


def _fresh(item) -> Announcement:
    with bypass_rls():
        return Announcement.objects.get(pk=item.pk)


def _fresh_org(world) -> Organization:
    with bypass_rls():
        return Organization.objects.get(pk=world["org"].pk)


def _memberships(world, user):
    with bypass_rls():
        return list(
            Membership.objects.filter(user=user, organization=world["org"], is_active=True).select_related(
                "role", "scope_unit", "organization"
            )
        )


def _badge(world, user) -> int:
    for attr in ("_announcements_badge", "_announcements_viewer"):
        if hasattr(user, attr):
            delattr(user, attr)
    with bypass_rls():
        return badge_count(user, _fresh_org(world), _memberships(world, user))


class SoftDeletePublishedTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("anndel")
        cls.item = make_announcement(
            cls.w,
            title="Silinəcək popup elan",
            show_as_popup=True,
            units=[cls.w["f1"].pk],
            apply_mode="url",
            apply_url="https://forms.example.org/x",
        )

    def test_delete_published_hides_it_from_targeted_student_everywhere(self):
        student = client_for(self.w["org"], self.w["s1"])
        self.assertIn("Silinəcək popup elan", student.get(reverse("announcements:list")).json()["html"])
        self.assertIn("data-ann-popup", student.get("/accounts/profile/").content.decode())
        self.assertEqual(_badge(self.w, self.w["s1"]), 1)

        response = _action(client_for(self.w["org"], self.w["owner"]), self.item, "delete")
        self.assertRedirects(response, reverse("announcements:manage_list"), fetch_redirect_response=False)

        item = _fresh(self.item)
        self.assertTrue(item.is_deleted)
        self.assertIsNotNone(item.deleted_at)
        self.assertEqual(item.deleted_by_id, self.w["owner"].pk)
        self.assertEqual(item.status, "published")  # vəziyyət saxlanılır — yalnız gizlənir

        # Siyahı (aktiv və «hamısı»), detal, popup, sayğac, oxundu, müraciət — hamısında yoxdur.
        for params in ({}, {"state": "all"}, {"q": "Silinəcək"}):
            self.assertNotIn(
                "Silinəcək popup elan", student.get(reverse("announcements:list"), params).json()["html"], params
            )
        detail = student.get(f"{CABINET}&elan={self.item.pk}").content.decode()
        self.assertNotIn("Silinəcək popup elan", detail)
        self.assertIn("Elan tapılmadı", detail)
        self.assertNotIn("data-ann-popup", student.get("/accounts/profile/").content.decode())
        self.assertEqual(_badge(self.w, self.w["s1"]), 0)
        self.assertEqual(student.post(reverse("announcements:read", args=[self.item.pk])).status_code, 404)
        self.assertEqual(student.post(reverse("announcements:apply", args=[self.item.pk])).status_code, 404)
        self.assertTrue(apply_service.apply_closed_reason(item))
        seen = student.post(
            reverse("announcements:popup_seen"),
            data=json.dumps({"ids": [str(self.item.pk)]}),
            content_type="application/json",
        )
        self.assertEqual(seen.json()["recorded"], 0)
        # Xülasə (DB-dəki təşkilat sətri) artıq bu elanı daşımır.
        stored = _fresh_org(self.w).settings[SNAPSHOT_KEY]["items"]
        self.assertNotIn(str(self.item.pk), [entry["id"] for entry in stored])

    @override_settings(CACHES=LOCMEM)
    def test_popup_summary_and_badge_cache_are_invalidated(self):
        from django.core.cache import cache

        cache.clear()
        # İkinci aktiv elan — silmədən sonra xülasə boş qalmır, sayğac KEŞ yolundan keçir.
        other = make_announcement(self.w, title="Qalan elan", show_as_popup=True)
        version_before = snapshot.version(_fresh_org(self.w))
        self.assertEqual(_badge(self.w, self.w["s1"]), 2)  # keşə yazıldı (versiya açarda)
        org, memberships = _fresh_org(self.w), _memberships(self.w, self.w["s1"])
        user = self.w["s1"]
        user.__dict__.pop("_announcements_badge", None)
        with self.assertNumQueries(0):  # keşdən — DB-yə getmir
            self.assertEqual(badge_count(user, org, memberships), 2)
        student = client_for(self.w["org"], self.w["s1"])
        popup_html = student.get("/accounts/profile/").content.decode()
        self.assertIn("Silinəcək popup elan", popup_html)

        _action(client_for(self.w["org"], self.w["owner"]), self.item, "delete")

        org = _fresh_org(self.w)
        self.assertNotEqual(snapshot.version(org), version_before)
        self.assertEqual([entry["id"] for entry in snapshot.active_items(org)], [str(other.pk)])
        self.assertEqual(_badge(self.w, self.w["s1"]), 1)  # köhnə versiyanın keşi oxunmur
        popup_html = student.get("/accounts/profile/").content.decode()
        self.assertNotIn("Silinəcək popup elan", popup_html)
        self.assertIn("Qalan elan", popup_html)
        cache.clear()

    def test_receipts_and_attachments_kept_download_only_for_manager(self):
        student = client_for(self.w["org"], self.w["s1"])
        self.assertEqual(student.post(reverse("announcements:apply", args=[self.item.pk])).status_code, 200)
        owner = client_for(self.w["org"], self.w["owner"])
        upload = owner.post(
            reverse("announcements:manage_edit", args=[self.item.pk]),
            {
                "title": "Silinəcək popup elan",
                "category": "exam",
                "priority": "0",
                "audience_families": ["students"],
                "audience_units": [str(self.w["f1"].pk)],
                "apply_mode": "url",
                "apply_url": "https://forms.example.org/x",
                "show_as_popup": "1",
                "files": SimpleUploadedFile("cedvel.pdf", PDF, content_type="application/pdf"),
            },
        )
        self.assertEqual(upload.status_code, 302)
        with bypass_rls():
            attachment = AnnouncementAttachment.objects.get(announcement=self.item)
        url = reverse("announcements:attachment_download", args=[self.item.pk, attachment.pk])
        self.assertEqual(student.get(url).status_code, 200)

        _action(owner, self.item, "delete")

        with bypass_rls():
            self.assertTrue(AnnouncementAttachment.objects.filter(pk=attachment.pk).exists())
            self.assertTrue(
                AnnouncementReceipt.objects.filter(
                    announcement=self.item, user=self.w["s1"], applied_at__isnull=False
                ).exists()
            )
        self.assertEqual(student.get(url).status_code, 404)
        self.assertEqual(owner.get(url).status_code, 200)
        # Sənəd silmə əməli silinmiş elanda işləmir (audit üçün saxlanılır).
        owner.post(
            reverse("announcements:manage_action", args=[self.item.pk]),
            {"action": "remove_attachment", "attachment": str(attachment.pk)},
        )
        with bypass_rls():
            self.assertTrue(AnnouncementAttachment.objects.filter(pk=attachment.pk).exists())
        # Statistika «Silinmişlər» siyahısında görünür.
        rows = owner.get(reverse("announcements:manage_rows"), {"state": "deleted"}).json()
        self.assertEqual(rows["total"], 1)

    def test_manager_sees_deleted_filter_and_restores_to_draft(self):
        owner = client_for(self.w["org"], self.w["owner"])
        _action(owner, self.item, "delete")

        default = owner.get(reverse("announcements:manage_rows")).json()
        self.assertNotIn("Silinəcək popup elan", default["html"])
        for state in ("active", "draft", "archived"):
            html = owner.get(reverse("announcements:manage_rows"), {"state": state}).json()["html"]
            self.assertNotIn("Silinəcək popup elan", html, state)
        deleted = owner.get(reverse("announcements:manage_rows"), {"state": "deleted"}).json()
        self.assertEqual(deleted["total"], 1)
        self.assertIn("Silinəcək popup elan", deleted["html"])
        self.assertIn('value="undelete"', deleted["html"])
        page = owner.get(reverse("announcements:manage_list"), {"state": "deleted"}).content.decode()
        self.assertIn("Silinəcək popup elan", page)

        edit = owner.get(reverse("announcements:manage_edit", args=[self.item.pk])).content.decode()
        self.assertIn("Bu elan silinib", edit)
        self.assertIn('value="undelete"', edit)
        self.assertNotIn('id="annm-form"', edit)

        response = _action(owner, self.item, "undelete")
        self.assertRedirects(
            response, reverse("announcements:manage_edit", args=[self.item.pk]), fetch_redirect_response=False
        )
        item = _fresh(self.item)
        self.assertFalse(item.is_deleted)
        self.assertIsNone(item.deleted_at)
        self.assertIsNone(item.deleted_by_id)
        self.assertEqual(item.status, "draft")
        self.assertIn("Silinəcək popup elan", owner.get(reverse("announcements:manage_rows")).json()["html"])
        # Qaralama — tələbə hələ də görmür; yenidən dərc şüurlu addımdır.
        student = client_for(self.w["org"], self.w["s1"])
        self.assertNotIn("Silinəcək popup elan", student.get(reverse("announcements:list")).json()["html"])
        _action(owner, self.item, "publish")
        self.assertIn("Silinəcək popup elan", student.get(reverse("announcements:list")).json()["html"])

        with bypass_rls():
            logs = list(
                AuditLog.objects.filter(resource_type="announcement", resource_id=str(self.item.pk)).values_list(
                    "action", "new_values", "user_id"
                )
            )
        self.assertIn(("delete", {"mode": "soft", "status": "published"}, self.w["owner"].pk), logs)
        self.assertIn(("update", {"action": "undelete", "status": "draft"}, self.w["owner"].pk), logs)

    def test_deleted_announcement_cannot_be_edited_or_published(self):
        owner = client_for(self.w["org"], self.w["owner"])
        _action(owner, self.item, "delete")
        _action(owner, self.item, "unpublish")
        _action(owner, self.item, "archive")
        item = _fresh(self.item)
        self.assertTrue(item.is_deleted)
        self.assertEqual(item.status, "published")
        response = owner.post(
            reverse("announcements:manage_edit", args=[self.item.pk]),
            {
                "title": "Dəyişdirilmiş başlıq",
                "category": "exam",
                "priority": "0",
                "audience_families": ["students"],
                "audience_units": [str(self.w["f1"].pk)],
                "apply_mode": "none",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_fresh(self.item).title, "Silinəcək popup elan")

    def test_edit_page_confirm_text_differs_for_published(self):
        owner = client_for(self.w["org"], self.w["owner"])
        html = owner.get(reverse("announcements:manage_edit", args=[self.item.pk])).content.decode()
        self.assertIn('value="delete"', html)
        self.assertIn("bütün alıcılar üçün dərhal yox olacaq", html)
        self.assertNotIn("bu əməliyyat geri qaytarılmır", html)


class DeleteAnyStatusTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("anddel")

    def test_draft_without_receipts_is_hard_deleted(self):
        draft = make_announcement(self.w, title="Heç kim görməyib", publish=False)
        owner = client_for(self.w["org"], self.w["owner"])
        html = owner.get(reverse("announcements:manage_edit", args=[draft.pk])).content.decode()
        self.assertIn("bu əməliyyat geri qaytarılmır", html)
        _action(owner, draft, "delete")
        with bypass_rls():
            self.assertFalse(Announcement.objects.filter(pk=draft.pk).exists())
            log = AuditLog.objects.get(resource_type="announcement", resource_id=str(draft.pk), action="delete")
        self.assertEqual(log.new_values, {"mode": "hard"})
        self.assertEqual(owner.get(reverse("announcements:manage_rows"), {"state": "deleted"}).json()["total"], 0)

    def test_draft_with_receipts_is_soft_deleted(self):
        item = make_announcement(self.w, title="Görülmüş, sonra qaralama")
        client_for(self.w["org"], self.w["s1"]).post(reverse("announcements:read", args=[item.pk]))
        owner = client_for(self.w["org"], self.w["owner"])
        _action(owner, item, "unpublish")
        self.assertEqual(_fresh(item).status, "draft")
        _action(owner, item, "delete")
        item = _fresh(item)
        self.assertTrue(item.is_deleted)
        with bypass_rls():
            self.assertEqual(AnnouncementReceipt.objects.filter(announcement=item).count(), 1)

    def test_archived_can_be_deleted(self):
        item = make_announcement(self.w, title="Arxivdəki elan")
        owner = client_for(self.w["org"], self.w["owner"])
        _action(owner, item, "archive")
        _action(owner, item, "delete")
        item = _fresh(item)
        self.assertTrue(item.is_deleted)
        self.assertEqual(item.status, "archived")
        _action(owner, item, "undelete")
        self.assertEqual(_fresh(item).status, "draft")

    def test_undelete_of_live_announcement_is_rejected(self):
        item = make_announcement(self.w, title="Canlı elan")
        _action(client_for(self.w["org"], self.w["owner"]), item, "undelete")
        item = _fresh(item)
        self.assertFalse(item.is_deleted)
        self.assertEqual(item.status, "published")


class ScopedDeleteTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annsdel")
        cls.org_wide = make_announcement(cls.w, title="Rektorluq elanı")
        cls.faculty = make_announcement(cls.w, title="Fakültə elanı", author=cls.w["dean"], units=[cls.w["g1"].pk])

    def test_dean_cannot_delete_org_wide_announcement(self):
        dean = client_for(self.w["org"], self.w["dean"])
        self.assertEqual(_action(dean, self.org_wide, "delete").status_code, 404)
        self.assertFalse(_fresh(self.org_wide).is_deleted)

    def test_dean_cannot_restore_org_wide_announcement_or_see_it_deleted(self):
        _action(client_for(self.w["org"], self.w["owner"]), self.org_wide, "delete")
        dean = client_for(self.w["org"], self.w["dean"])
        rows = dean.get(reverse("announcements:manage_rows"), {"state": "deleted"}).json()
        self.assertNotIn("Rektorluq elanı", rows["html"])
        self.assertEqual(_action(dean, self.org_wide, "undelete").status_code, 404)
        self.assertTrue(_fresh(self.org_wide).is_deleted)

    def test_dean_deletes_and_restores_own_faculty_announcement(self):
        dean = client_for(self.w["org"], self.w["dean"])
        _action(dean, self.faculty, "delete")
        item = _fresh(self.faculty)
        self.assertTrue(item.is_deleted)
        self.assertEqual(item.deleted_by_id, self.w["dean"].pk)
        self.assertIn(
            "Fakültə elanı", dean.get(reverse("announcements:manage_rows"), {"state": "deleted"}).json()["html"]
        )
        student = client_for(self.w["org"], self.w["s1"])
        self.assertNotIn("Fakültə elanı", student.get(reverse("announcements:list")).json()["html"])
        _action(dean, self.faculty, "undelete")
        self.assertFalse(_fresh(self.faculty).is_deleted)
