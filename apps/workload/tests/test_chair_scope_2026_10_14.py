"""Kafedra müdiri / dekan əhatəsi — «Dərs yükü mərkəzi» və «Yük — ümumi baxış» (sahib, 2026-10-14).

«Hər kafedra müdiri öz kafedrasının ancaq dərs yükünü görə bilər»: sətirlər, KPI-lar və filtr
seçimləri ``workload.manage`` / ``workload.report`` əhatəsindəndir; əhatədə TƏK fakültə varsa
«Fakültə» filtri avtomatik seçilir və gizlənir; URL-dəki kənar id sızma vermir. Dekan öz
fakültəsini, org-wide rol (tədris şöbəsi, rektorluq) hamısını görür.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.organizations.models import OrgUnit
from core.constants import OrgUnitType, RoleScopeType

from .factories import activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

OFFICE_PERMS = ["workload.view", "workload.manage", "workload.submit", "workload.report"]
CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]
DEAN_PERMS = ["workload.view", "workload.approve", "workload.report"]


class ChairScopeBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("chs-1014")
        cls.s1 = make_structure(cls.org, code="CHA")  # F1 → K1
        cls.s2 = make_structure(cls.org, code="CHB")  # F2 → K3
        cls.f1, cls.k1 = cls.s1["faculty"], cls.s1["chair"]
        cls.f2, cls.k3 = cls.s2["faculty"], cls.s2["chair"]
        cls.k2 = OrgUnit.objects.create(
            organization=cls.org,
            name="CHA-ikinci-kafedra",
            slug="chs-1014-k2",
            unit_type=OrgUnitType.CHAIR,
            parent=cls.f1,
        )
        cls.office = User.objects.create_user("chs.office", "chs.office@x.test", "pw")
        cls.chair_head = User.objects.create_user("chs.chair", "chs.chair@x.test", "pw")
        cls.dean = User.objects.create_user("chs.dean", "chs.dean@x.test", "pw")
        activate_member(cls.org, cls.office, "teaching_office_head", permissions=OFFICE_PERMS, level=85)
        activate_member(
            cls.org,
            cls.chair_head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=cls.k1,
            scope_type=RoleScopeType.UNIT,
            level=60,
        )
        activate_member(
            cls.org,
            cls.dean,
            "dean",
            permissions=DEAN_PERMS,
            scope_unit=cls.f1,
            scope_type=RoleScopeType.UNIT,
            level=70,
        )
        for chair, stack, hours in ((cls.k1, cls.s1, 10), (cls.k2, cls.s1, 20), (cls.k3, cls.s2, 40)):
            task = make_task(cls.org, chair, created_by=cls.office)
            make_row(task, stack, lecture_total=hours, seminar_total=0)

    def section(self, user, name, key, **params):
        self.client.force_login(user)
        response = self.client.get(reverse("accounts:profile"), {"section": name, **params})
        self.assertEqual(response.status_code, 200)
        return response, response.context[key]

    @staticmethod
    def field(section, name):
        return next(field for field in section["filter_fields"] if field["name"] == name)


class WorkloadCenterChairScopeTest(ChairScopeBase):
    def center(self, user, **params):
        return self.section(user, "workload-center", "workload_center_section", **params)

    def test_chair_head_sees_only_own_chair_and_no_foreign_faculties(self):
        response, section = self.center(self.chair_head)
        self.assertEqual([card["name"] for card in section["cards"]], [self.k1.name])
        self.assertEqual(section["kpi"]["chairs"], 1)
        self.assertEqual([row["label"] for row in section["faculty_options"]], [self.f1.name])
        field = self.field(section, "wc_faculty")
        self.assertEqual(field["kind"], "hidden")
        self.assertEqual(field["value"], str(self.f1.pk))
        self.assertNotContains(response, self.f2.name)
        self.assertNotContains(response, self.k3.name)
        self.assertEqual([row["label"] for row in section["chair_options"]], [self.k1.name])

    def test_out_of_scope_params_are_ignored(self):
        _response, section = self.center(self.chair_head, wc_faculty=str(self.f2.pk))
        self.assertEqual([card["name"] for card in section["cards"]], [self.k1.name])
        self.assertEqual(section["filters"]["faculty"], str(self.f1.pk))
        response, section = self.center(self.chair_head, wc_view="tasks", wc_chair=str(self.k3.pk))
        self.assertIsNone(section["task"])
        self.assertNotContains(response, self.k3.name)

    def test_other_tabs_stay_scoped(self):
        for view in ("tasks", "import", "reports", "settings"):
            response, section = self.center(self.chair_head, wc_view=view)
            self.assertEqual([card["chair_id"] for card in section["cards"]], [str(self.k1.pk)], view)
            self.assertNotContains(response, self.k3.name)

    def test_office_sees_every_chair_and_can_filter_by_faculty(self):
        _response, section = self.center(self.office)
        self.assertEqual({card["name"] for card in section["cards"]}, {self.k1.name, self.k2.name, self.k3.name})
        field = self.field(section, "wc_faculty")
        self.assertEqual(field["kind"], "select")
        self.assertTrue({self.f1.name, self.f2.name} <= {row["label"] for row in field["options"]})
        _response, section = self.center(self.office, wc_faculty=str(self.f2.pk))
        self.assertEqual([card["name"] for card in section["cards"]], [self.k3.name])

    def test_foreign_chair_write_is_denied_server_side(self):
        self.client.force_login(self.chair_head)
        response = self.client.post(
            reverse("workload:action"),
            {"action": "create_task", "chair": str(self.k3.pk), "academic_year": "2027/2028"},
        )
        self.assertEqual(response.status_code, 403)


class WorkloadOverviewChairScopeTest(ChairScopeBase):
    def overview(self, user, **params):
        return self.section(user, "workload-overview", "workload_overview_section", **params)

    def test_chair_head_kpis_and_lists_follow_own_chair(self):
        response, section = self.overview(self.chair_head)
        self.assertEqual(section["scope_kind"], "chair")
        self.assertEqual([row["name"] for row in section["chairs"]], [self.k1.name])
        self.assertEqual(section["totals"]["planned_hours"], 10)
        self.assertEqual(section["totals"]["chairs"], 1)
        self.assertEqual(sum(item["count"] for item in section["status_map"]), 1)
        self.assertTrue(all(row["name"] == self.k1.name for row in section["risky"]))
        self.assertNotIn("fac", [tab["key"] for tab in section["view_tabs"]])
        self.assertEqual(self.field(section, "wo_faculty")["kind"], "hidden")
        self.assertNotContains(response, self.k3.name)
        self.assertNotContains(response, self.f2.name)

    def test_chair_head_cannot_open_faculty_view_or_foreign_faculty(self):
        _response, section = self.overview(self.chair_head, wo_view="fac")
        self.assertEqual(section["view"], "overview")
        _response, section = self.overview(self.chair_head, wo_faculty=str(self.f2.pk))
        self.assertEqual([row["name"] for row in section["chairs"]], [self.k1.name])
        self.assertEqual(section["totals"]["planned_hours"], 10)

    def test_dean_sees_own_faculty_with_locked_filter(self):
        _response, section = self.overview(self.dean)
        self.assertEqual(section["scope_kind"], "faculty")
        self.assertEqual({row["name"] for row in section["chairs"]}, {self.k1.name, self.k2.name})
        self.assertEqual(section["totals"]["planned_hours"], 30)
        self.assertIn("fac", [tab["key"] for tab in section["view_tabs"]])
        field = self.field(section, "wo_faculty")
        self.assertEqual((field["kind"], field["value"]), ("hidden", str(self.f1.pk)))

    def test_office_sees_all_and_faculty_filter_narrows_kpis(self):
        _response, section = self.overview(self.office)
        self.assertEqual(section["scope_kind"], "org")
        self.assertEqual(section["totals"]["planned_hours"], 70)
        self.assertEqual(self.field(section, "wo_faculty")["kind"], "select")
        _response, section = self.overview(self.office, wo_faculty=str(self.f2.pk))
        self.assertEqual([row["name"] for row in section["chairs"]], [self.k3.name])
        self.assertEqual(section["totals"]["planned_hours"], 40)
        self.assertEqual(section["totals"]["chairs"], 1)
        self.assertEqual([row["name"] for row in section["faculties"]], [self.f2.name])
