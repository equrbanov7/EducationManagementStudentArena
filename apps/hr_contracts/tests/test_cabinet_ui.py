"""Kabinet — menyu görünürlüyü, HR paneli (KPI, filtr, cədvəl), işçinin «Müqavilələrim» paneli (yalnız öz),
fraqment ucu (AJAX), Excel ixracı, tarixçə, işçi seçicisi, şəxs səhifəsinin kartı."""

from __future__ import annotations

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.hr_contracts.services import contracts as service
from core.rls import bypass_rls

from .world import actor, build_world, client_for, days, make_contract

PROFILE = "/accounts/profile/"


def _aside(html: str) -> str:
    start = html.find('<aside class="profile-sidebar"')
    return html[start : html.find("</aside>", start)]


class SidebarTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("hrcside")

    def setUp(self):
        cache.clear()

    def _menu(self, key):
        response = client_for(self.w["org"], self.w[key]).get(PROFILE)
        self.assertEqual(response.status_code, 200)
        return _aside(response.content.decode())

    def test_hr_menu_for_key_holders_only(self):
        for key in ("hr", "unit_hr", "trustee", "rector"):
            self.assertIn('data-section="hr-contracts"', self._menu(key), key)
        for key in ("t1", "dean", "s1", "m1"):
            self.assertNotIn('data-section="hr-contracts"', self._menu(key), key)

    def test_my_contracts_menu_only_with_a_visible_contract(self):
        self.assertNotIn('data-section="my-contracts"', self._menu("t1"))
        make_contract(self.w, "t1", number="SB-1")
        aside = self._menu("t1")
        self.assertIn('data-section="my-contracts"', aside)
        self.assertIn('data-sidebar-layout="teacher"', aside)  # müəllimin düz menyusu pozulmur
        make_contract(self.w, "m1", number="SB-2")
        self.assertIn('data-section="my-contracts"', self._menu("m1"))
        self.assertNotIn('data-section="my-contracts"', self._menu("s1"))
        make_contract(self.w, "t2", number="SB-3", status="draft")
        self.assertNotIn('data-section="my-contracts"', self._menu("t2"))  # qaralama göndərilməyib


class PanelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("hrcpanel")
        cls.soon = make_contract(cls.w, "t1", number="P-1", end_date=days(20))
        cls.staff = make_contract(cls.w, "m1", number="P-2", end_date=days(300))
        cls.gone = make_contract(cls.w, "t2", number="P-3", start_date=days(-400), end_date=days(-3))
        with bypass_rls():
            service.mark_sent(actor(cls.w, "hr"), cls.soon.pk)

    def setUp(self):
        cache.clear()

    def _section(self, key, section="hr-contracts", **params):
        query = "&".join(f"{name}={value}" for name, value in params.items())
        response = client_for(self.w["org"], self.w[key]).get(f"{PROFILE}?section={section}&{query}")
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_hr_panel_lists_kpis_and_actions(self):
        html = self._section("hr")
        for number in ("P-1", "P-2", "P-3"):
            self.assertIn(number, html)
        self.assertIn("data-hrc-create", html)
        self.assertIn('id="hrcContractDialog"', html)
        self.assertIn("hr_contracts/js/hr_contracts.js", html)
        self.assertIn("Təsdiq gözləyir", html)

    def test_filters(self):
        html = self._section("hr", hrc_status="expired")
        self.assertIn("P-3", html)
        self.assertNotIn("P-1", html)
        html = self._section("hr", hrc_q="mühasib")  # dözümlü axtarış (vəzifə)
        self.assertNotIn("P-3", html)
        html = self._section("hr", hrc_status="awaiting_ack")
        self.assertIn("P-1", html)
        self.assertNotIn("P-2", html)
        html = self._section("hr", hrc_unit=self.w["f2"].pk)
        self.assertIn("P-2", html)
        self.assertNotIn("P-1", html)

    def test_unit_scoped_and_read_only_views(self):
        html = self._section("unit_hr")
        self.assertIn("P-1", html)
        self.assertNotIn("P-2", html)  # F2 əhatədən kənar
        html = self._section("trustee")
        self.assertIn("P-2", html)
        self.assertNotIn("data-hrc-create", html)
        self.assertNotIn('id="hrcContractDialog"', html)

    def test_fragment_endpoint(self):
        client = client_for(self.w["org"], self.w["hr"])
        response = client.get(reverse("accounts:profile_section_fragment", args=["hr-contracts"]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("P-1", response.json()["html"])
        denied = client_for(self.w["org"], self.w["t1"]).get(
            reverse("accounts:profile_section_fragment", args=["hr-contracts"])
        )
        self.assertIn(denied.status_code, (403, 404))

    def test_employee_panel_shows_only_own_and_pending_card(self):
        html = self._section("t1", section="my-contracts")
        self.assertIn("P-1", html)
        self.assertNotIn("P-2", html)
        self.assertIn("Yeni müqaviləniz e-poçtunuza göndərilib", html)
        self.assertIn("Tanış oldum, təsdiqləyirəm", html)
        self.assertIn(reverse("hr_contracts:acknowledge", args=[self.soon.pk]), html)
        other = self._section("m1", section="my-contracts")
        self.assertIn("P-2", other)
        self.assertNotIn("Tanış oldum, təsdiqləyirəm", other)

    def test_export_xlsx_is_audited(self):
        response = client_for(self.w["org"], self.w["hr"]).get(
            reverse("hr_contracts:export"), {"hrc_status": "expired"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"PK"))
        with bypass_rls():
            self.assertTrue(AuditLog.objects.filter(resource_type=service.AUDIT_RESOURCE, action="export").exists())
        self.assertEqual(client_for(self.w["org"], self.w["t1"]).get(reverse("hr_contracts:export")).status_code, 403)

    def test_history_and_staff_picker(self):
        client = client_for(self.w["org"], self.w["hr"])
        history = client.get(reverse("hr_contracts:history", args=[self.soon.pk]))
        self.assertEqual(history.status_code, 200)
        self.assertIn("İşçiyə göndərildi", history.json()["html"])
        self.assertEqual(
            client_for(self.w["org"], self.w["unit_hr"])
            .get(reverse("hr_contracts:history", args=[self.staff.pk]))
            .status_code,
            404,
        )
        results = client.get(reverse("hr_contracts:staff"), {"q": ""}).json()["results"]
        ids = {row["id"] for row in results}
        self.assertIn(str(self.w["t1"].pk), ids)
        self.assertIn(str(self.w["m1"].pk), ids)
        self.assertNotIn(str(self.w["s1"].pk), ids)  # tələbə seçicidə yoxdur
        scoped = client_for(self.w["org"], self.w["unit_hr"]).get(reverse("hr_contracts:staff")).json()["results"]
        self.assertNotIn(str(self.w["m1"].pk), {row["id"] for row in scoped})
        self.assertEqual(
            client_for(self.w["org"], self.w["trustee"]).get(reverse("hr_contracts:staff")).status_code, 403
        )

    def test_person_page_card(self):
        url = reverse("accounts:people_person_page", args=[self.w["t1"].pk])
        html = client_for(self.w["org"], self.w["hr"]).get(url).content.decode()
        self.assertIn("Əmək müqaviləsi", html)
        self.assertIn("P-1", html)
