"""Məcburi elan (sahib, 2026-10-07) — menecer tərəfi.

* forma: üç rejim (``popup_mode``) → ``show_as_popup`` / ``requires_ack``; köhnə ``show_as_popup``;
  servis və DB CHECK-i «məcburi ⇒ popup»;
* «Kim görəcək» sayı: yalnız menecerə, əhatə serverdə, sorğu sayı sətirlərdən asılı deyil;
* «Təsdiq edən: X / Y (hədəf)» + alıcı siyahısı (vəziyyət, axtarış, səhifə; N+1 yoxdur).
"""

from __future__ import annotations

import json

from django.db import IntegrityError, connection, transaction
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.announcements.forms import AnnouncementForm
from apps.announcements.models import Announcement
from apps.announcements.services import manage, recipients
from apps.announcements.services.access import manage_scope
from apps.announcements.services.audience import family_of
from apps.organizations.models import Membership
from core.rls import bypass_rls

from .world import _record, _Req, build_world, client_for, make_announcement, member

BASE = {
    "title": "Məcburi elan",
    "category": "general",
    "priority": "0",
    "audience_families": ["students"],
    "apply_mode": "none",
}


class PopupModeFormTest(SimpleTestCase):
    def _clean(self, **extra):
        form = AnnouncementForm({**BASE, **extra})
        self.assertTrue(form.is_valid(), form.errors)
        data = form.cleaned_data
        return data["popup_mode"], data["show_as_popup"], data["requires_ack"]

    def test_three_modes_map_to_flags(self):
        self.assertEqual(self._clean(popup_mode="none"), ("none", False, False))
        self.assertEqual(self._clean(popup_mode="once"), ("once", True, False))
        self.assertEqual(self._clean(popup_mode="mandatory"), ("mandatory", True, True))

    def test_mode_wins_over_legacy_checkbox_and_legacy_still_works(self):
        self.assertEqual(self._clean(popup_mode="none", show_as_popup="1"), ("none", False, False))
        self.assertEqual(self._clean(show_as_popup="1"), ("once", True, False))
        self.assertEqual(self._clean(), ("none", False, False))

    def test_unknown_mode_is_rejected(self):
        form = AnnouncementForm({**BASE, "popup_mode": "always"})
        self.assertFalse(form.is_valid())
        self.assertIn("popup_mode", form.errors)


class MandatoryPersistenceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annmper")

    def test_create_form_posts_mandatory_and_service_forces_popup(self):
        client = client_for(self.w["org"], self.w["owner"])
        response = client.post(
            reverse("announcements:manage_create"), {**BASE, "popup_mode": "mandatory", "then": "publish"}
        )
        self.assertEqual(response.status_code, 302)
        with bypass_rls():
            item = Announcement.objects.get(title="Məcburi elan")
        self.assertTrue(item.requires_ack and item.show_as_popup)
        page = client.get(reverse("announcements:manage_edit", args=[item.pk])).content.decode()
        self.assertIn('name="popup_mode" value="mandatory" checked', page)
        self.assertIn("annm-choice", page)
        self.assertNotIn('name="show_as_popup"', page)  # köhnə checkbox yoxdur
        self.assertNotIn('<select name="popup_mode"', page)  # native select yoxdur
        self.assertIn("data-annm-summary", page)

    def test_service_enforces_popup_for_mandatory(self):
        with bypass_rls():
            item = manage.save_announcement(
                _Req(self.w["owner"], self.w["org"]),
                self.w["org"],
                manage_scope(self.w["owner"], self.w["org"]),
                {
                    **BASE,
                    "summary": "",
                    "body": "",
                    "priority": 0,
                    "is_pinned": False,
                    "publish_at": None,
                    "expires_at": None,
                    "deadline_at": None,
                    "requires_ack": True,
                    "show_as_popup": False,
                },
            )
            item.refresh_from_db()
        self.assertTrue(item.requires_ack)
        self.assertTrue(item.show_as_popup)

    def test_check_constraint_rejects_mandatory_without_popup(self):
        item = make_announcement(self.w, title="Adi elan")
        with bypass_rls(), self.assertRaises(IntegrityError), transaction.atomic():
            Announcement.objects.filter(pk=item.pk).update(requires_ack=True, show_as_popup=False)

    def test_switching_back_to_none_clears_both_flags(self):
        item = make_announcement(self.w, title="Sonra adi olacaq", requires_ack=True)
        client = client_for(self.w["org"], self.w["owner"])
        client.post(
            reverse("announcements:manage_edit", args=[item.pk]),
            {**BASE, "title": "Sonra adi olacaq", "popup_mode": "none", "then": "save"},
        )
        with bypass_rls():
            item.refresh_from_db()
        self.assertFalse(item.requires_ack)
        self.assertFalse(item.show_as_popup)


class AudienceCountTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annaudc")
        cls.other = build_world("annaudx")

    def _get(self, user, org=None, **params):
        client = client_for(org or self.w["org"], user)
        return client.get(reverse("announcements:manage_audience_count"), params)

    def test_only_managers(self):
        for user in (self.w["s1"], self.w["t1"]):
            self.assertEqual(self._get(user, families=["students"]).status_code, 403)

    def test_counts_follow_audience_rules(self):
        owner = self.w["owner"]
        payload = self._get(owner, families=["students"]).json()
        self.assertEqual(payload["count"], 2)
        self.assertIn("Kim görəcək", payload["text"])
        self.assertIn("Tələbələr", payload["text"])
        self.assertIn("bütün təşkilat", payload["text"])
        payload = self._get(owner, families=["students"], units=[str(self.w["f1"].pk)]).json()
        self.assertEqual(payload["count"], 1)
        self.assertIn("Fakulte F1", payload["text"])
        payload = self._get(owner, families=["teachers"], units=[str(self.w["f1"].pk)]).json()
        self.assertEqual(payload["count"], 1)  # t1 — Kafedra A (F1-in alt-ağacı)
        payload = self._get(owner, families=["teachers"], units=[str(self.w["f2"].pk)]).json()
        self.assertEqual(payload["count"], 0)
        payload = self._get(owner, families=["students", "teachers", "staff"]).json()
        # İstinad: bütün aktiv üzvlərin Python-da ailə üzrə sayı (middleware sahibə də üzvlük yaradır).
        with bypass_rls():
            expected = {
                user_id
                for user_id, role_name in Membership.objects.filter(
                    organization=self.w["org"], is_active=True, user__is_active=True
                ).values_list("user_id", "role__name")
                if family_of(role_name)
            }
        self.assertGreaterEqual(len(expected), 4)
        self.assertEqual(payload["count"], len(expected))

    def test_matches_legacy_targeted_count(self):
        item = make_announcement(
            self.w, title="Say yoxlaması", families=["students", "teachers"], units=[self.w["f1"].pk]
        )
        with bypass_rls():
            self.assertEqual(manage.targeted_count(item), 2)

    def test_scope_and_foreign_units_are_enforced(self):
        payload = self._get(self.w["dean"], families=["students"], units=[str(self.w["g2"].pk)]).json()
        self.assertTrue(payload["warning"])
        self.assertIsNone(payload["count"])
        self.assertIn("əhatənizdən kənardadır", payload["text"])
        payload = self._get(self.w["dean"], families=["students"]).json()  # dekan bütün təşkilatı seçə bilməz
        self.assertTrue(payload["warning"])
        payload = self._get(self.w["dean"], families=["students"], units=[str(self.w["f1"].pk)]).json()
        self.assertEqual(payload["count"], 1)
        payload = self._get(self.w["owner"], families=["students"], units=[str(self.other["f1"].pk)]).json()
        self.assertTrue(payload["warning"])  # başqa təşkilatın bölməsi — tapılmadı
        payload = self._get(self.w["owner"]).json()
        self.assertTrue(payload["warning"])  # ailə seçilməyib

    def test_other_org_manager_counts_only_own_members(self):
        payload = self._get(self.other["owner"], org=self.other["org"], families=["students"]).json()
        self.assertEqual(payload["count"], 2)

    def test_query_count_does_not_grow_with_members(self):
        client = client_for(self.w["org"], self.w["owner"])
        url = reverse("announcements:manage_audience_count")
        params = {"families": ["students", "teachers"], "units": [str(self.w["f1"].pk)]}
        client.get(url, params)
        with CaptureQueriesContext(connection) as before:
            client.get(url, params)
        with bypass_rls():
            from apps.registrar.models import Curriculum, Program

            program, curriculum = Program.objects.get(organization=self.w["org"]), Curriculum.objects.get(
                organization=self.w["org"]
            )
            for index in range(6):
                student = member(self.w["org"], f"annaudc_extra{index}", "student")
                _record(self.w["org"], student, self.w["g1"], program, curriculum)
        with CaptureQueriesContext(connection) as after:
            payload = client.get(url, params).json()
        self.assertEqual(payload["count"], 8)
        self.assertEqual(len(before.captured_queries), len(after.captured_queries))


class AckStatsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annstat")
        cls.item = make_announcement(cls.w, title="Statistika məcburi", requires_ack=True)
        cls.plain = make_announcement(cls.w, title="Statistika adi", show_as_popup=True)

    def _ack(self, user):
        client = client_for(self.w["org"], user)
        response = client.post(
            reverse("announcements:ack", args=[self.item.pk]),
            data=json.dumps({"confirm": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    def _rows(self, user=None, **params):
        client = client_for(self.w["org"], user or self.w["owner"])
        return client.get(reverse("announcements:manage_recipients", args=[self.item.pk]), params)

    def test_summary_kpi_and_lists(self):
        self._ack(self.w["s1"])
        with bypass_rls():
            self.assertEqual(recipients.ack_summary(self.item), {"targeted": 2, "acked": 1, "pending": 1})
        client = client_for(self.w["org"], self.w["owner"])
        page = client.get(reverse("announcements:manage_edit", args=[self.item.pk])).content.decode()
        self.assertIn("Təsdiq edən", page)
        self.assertIn("data-annm-ack", page)
        self.assertIn("annstat_s2", page)  # ilk səhifə — gözləyənlər
        pending = self._rows(status="pending").json()
        self.assertEqual(pending["total"], 1)
        self.assertIn("annstat_s2", pending["html"])
        self.assertNotIn("annstat_s1", pending["html"])
        acked = self._rows(status="acked").json()
        self.assertEqual(acked["total"], 1)
        self.assertIn("annstat_s1", acked["html"])
        self.assertIn("Təsdiq edib", acked["html"])
        self.assertEqual(self._rows(status="all").json()["total"], 2)
        self.assertEqual(self._rows(status="weird").json()["total"], 1)  # ağ siyahı → pending

    def test_search_and_pagination(self):
        with bypass_rls():
            Membership.objects.filter(user=self.w["s2"]).update(is_active=True)
        searched = self._rows(status="all", q="annstat_s2").json()
        self.assertEqual(searched["total"], 1)
        self.assertIn("annstat_s2", searched["html"])
        with bypass_rls():
            listing = recipients.recipient_page(self.item, status="all", page=2, page_size=1)
        self.assertEqual((listing["page"], listing["pages"], len(listing["items"])), (2, 2, 1))
        with bypass_rls():
            listing = recipients.recipient_page(self.item, status="all", page=99, page_size=1)
        self.assertEqual(listing["page"], 2)

    def test_list_query_count_is_bounded(self):
        url = reverse("announcements:manage_recipients", args=[self.item.pk])
        client = client_for(self.w["org"], self.w["owner"])
        client.get(url, {"status": "all"})
        with CaptureQueriesContext(connection) as before:
            client.get(url, {"status": "all"})
        with bypass_rls():
            for index in range(5):
                member(self.w["org"], f"annstat_more{index}", "student")
        with CaptureQueriesContext(connection) as after:
            payload = client.get(url, {"status": "all"}).json()
        self.assertEqual(payload["total"], 7)
        self.assertEqual(len(before.captured_queries), len(after.captured_queries))

    def test_permissions_and_non_mandatory(self):
        self.assertEqual(self._rows(user=self.w["s1"]).status_code, 403)
        self.assertEqual(self._rows(user=self.w["dean"]).status_code, 404)  # təşkilat səviyyəli elan — əhatədən kənar
        client = client_for(self.w["org"], self.w["owner"])
        url = reverse("announcements:manage_recipients", args=[self.plain.pk])
        self.assertEqual(client.get(url).status_code, 404)
        page = client.get(reverse("announcements:manage_edit", args=[self.plain.pk])).content.decode()
        self.assertNotIn("data-annm-ack", page)

    def test_manage_rows_show_mandatory_chip_and_ack_count(self):
        self._ack(self.w["s1"])
        html = client_for(self.w["org"], self.w["owner"]).get(reverse("announcements:manage_rows")).json()["html"]
        self.assertIn("ann-chip--mandatory", html)
        self.assertIn("annm-stats__ack", html)
