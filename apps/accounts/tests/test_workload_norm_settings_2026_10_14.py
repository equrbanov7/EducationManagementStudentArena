"""«Sistem tənzimləmələri» → «Dərs yükü norması və ştat» (sahib 2026-10-14).

Kilidlənən qaydalar:

* norma / ştat həddi açarlarını YALNIZ RİM rəhbəri yazır (dekan 403), bölmədə «workload» qrupu görünür;
* onluq ştat dəyəri «1,75» / «1.75» qəbul olunur, mətn kimi saxlanır, hədd xaricindəki / «ən az > ən çox» rədd
  olunur; «standarta qaytar» sətri silir; dəyişiklik audit jurnalına düşür;
* kafedra profilinin qeydi və KPI faizi cari normadan gəlir;
* Forma 7 tutuşdurması həddən kənar ştatı profilə yazmır və qeyd edir (səssiz 1,5-ə kəsmə yoxdur).
"""

from __future__ import annotations

import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import RuntimeSetting
from apps.accounts.services import runtime_settings_admin
from apps.accounts.services.teacher_roster.parsing import parse_rate
from apps.accounts.services.teacher_roster.plan import checked_rate
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from apps.workload.models import TeacherWorkloadProfile
from core import runtime_settings as rs
from core.constants import OrganizationType, OrgUnitType, RoleScopeType

User = get_user_model()

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "norm-settings"}}
YEAR = "2026/2027"


class _Row:
    def __init__(self, text):
        self.rate = parse_rate(text)


@override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
class WorkloadNormSettingsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("wns_owner", "wns_owner@qku.edu.az", "pw")
        cls.org = Organization.objects.create(
            name="WNS Univ", slug="wns-univ", org_type=OrganizationType.UNIVERSITY, owner=cls.owner, status="active"
        )
        cls.chair = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.CHAIR, name="Norma kafedrası", slug="wns-kaf"
        )

        def member(username, role_name, level, permissions, *, scope_type=RoleScopeType.ORGANIZATION, unit=None):
            role, _ = Role.objects.update_or_create(
                organization=cls.org,
                name=role_name,
                defaults={
                    "display_name": role_name,
                    "level": level,
                    "scope_type": scope_type,
                    "permissions": permissions,
                    "is_active": True,
                },
            )
            user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
            Membership.objects.create(
                user=user, organization=cls.org, role=role, scope_unit=unit, is_primary=True, is_active=True
            )
            return user

        cls.rim = member("wns_rim", "ikt_rehber", 95, ["semester.view"])
        cls.dean = member("wns_dean", "dean", 80, ["semester.view"])
        cls.head = member(
            "wns_head", "chair_head", 70, ["unit.view", "member.view"], scope_type=RoleScopeType.UNIT, unit=cls.chair
        )
        cls.teacher = member("wns_teacher", "teacher", 50, ["course.view"], unit=cls.chair)
        TeacherWorkloadProfile.objects.create(
            organization=cls.org, teacher=cls.teacher, academic_year=YEAR, staff_fraction=Decimal("0.5")
        )

    def setUp(self):
        rs.invalidate()

    def tearDown(self):
        rs.invalidate()

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _save(self, user, data):
        return self._client(user).post(
            reverse("accounts:system_settings_save"), data=json.dumps(data), content_type="application/json"
        )

    def test_only_rim_head_writes_norm_settings(self):
        denied = self._save(self.dean, {"workload.norm_hours_full": "600"})
        self.assertEqual(denied.status_code, 403)
        self.assertFalse(RuntimeSetting.objects.filter(key__startswith="workload.").exists())

        allowed = self._save(self.rim, {"workload.norm_hours_full": "600", "workload.norm_hours_half": "320"})
        self.assertEqual(allowed.status_code, 200, allowed.content)
        self.assertEqual(
            dict(RuntimeSetting.objects.filter(key__startswith="workload.").values_list("key", "value")),
            {"workload.norm_hours_full": 600, "workload.norm_hours_half": 320},
        )
        self.assertTrue(AuditLog.objects.filter(resource_type="core.runtime_settings").exists())

        fragment = self._client(self.rim).get(
            reverse("accounts:profile_section_fragment", kwargs={"section": "system-settings"})
        )
        groups = {group["key"]: group for group in fragment.context["system_settings_section"]["groups"]}
        keys = [field["key"] for field in groups["workload"]["fields"]]
        self.assertEqual(
            keys,
            [
                "workload.norm_hours_full",
                "workload.norm_hours_half",
                "workload.norm_hours_admin",
                "workload.staff_rate_min",
                "workload.staff_rate_max",
            ],
        )
        rate_max = groups["workload"]["fields"][-1]
        self.assertEqual((rate_max["value"], rate_max["default"], rate_max["step"]), ("1.5", "1.5", "0.01"))
        self.assertIn('step="0.01"', fragment.json()["html"])

    def test_decimal_parsing_ranges_pairs_and_reset(self):
        result = runtime_settings_admin.save_values(actor=self.rim, data={"workload.staff_rate_max": "1,75"})
        self.assertEqual([item["key"] for item in result["changed"]], ["workload.staff_rate_max"])
        self.assertEqual(RuntimeSetting.objects.get(key="workload.staff_rate_max").value, "1.75")
        self.assertEqual(rs.get("workload.staff_rate_max"), Decimal("1.75"))
        # Eyni dəyər başqa yazılışda — dəyişiklik yoxdur.
        self.assertEqual(
            runtime_settings_admin.save_values(actor=self.rim, data={"workload.staff_rate_max": "1.750"})["changed"],
            [],
        )
        for bad in ("9", "abc", "0.2"):
            with self.subTest(bad=bad), self.assertRaises(runtime_settings_admin.RuntimeSettingsError) as ctx:
                runtime_settings_admin.save_values(actor=self.rim, data={"workload.staff_rate_max": bad})
            self.assertIn("workload.staff_rate_max", ctx.exception.errors)
        runtime_settings_admin.save_values(actor=self.rim, data={"workload.staff_rate_min": "1"})  # 1 ≤ 1,75
        self.assertEqual(rs.get("workload.staff_rate_min"), Decimal("1.00"))
        with self.assertRaises(runtime_settings_admin.RuntimeSettingsError) as ctx:
            runtime_settings_admin.save_values(actor=self.rim, data={"workload.staff_rate_max": "0.75"})
        self.assertEqual(set(ctx.exception.errors), {"workload.staff_rate_max"})  # ən çox < saxlanmış ən az
        with self.assertRaises(runtime_settings_admin.RuntimeSettingsError) as ctx:
            runtime_settings_admin.save_values(
                actor=self.rim, data={"workload.staff_rate_min": "0.9", "workload.staff_rate_max": "0.75"}
            )
        self.assertEqual(set(ctx.exception.errors), {"workload.staff_rate_min", "workload.staff_rate_max"})
        runtime_settings_admin.save_values(
            actor=self.rim, data={"workload.staff_rate_max": "1.5", "workload.staff_rate_min": "0.25"}
        )
        self.assertFalse(RuntimeSetting.objects.filter(key__startswith="workload.staff_rate").exists())

    def test_chair_profile_note_and_kpi_follow_settings(self):
        url = reverse("accounts:profile_section_fragment", kwargs={"section": "chair-profile"})
        section = self._client(self.head).get(url, {"cp_year": YEAR}).context["chair_profile_section"]
        self.assertIn("1 ştat — 500 saat", section["norm_source_note"])
        self.assertIn("0,5 ştat — 250 saat", section["norm_source_note"])
        self.assertNotIn("sahib qərarını", section["norm_source_note"])
        row = next(item for item in section["staff_rows"] if item["user_id"] == str(self.teacher.pk))
        self.assertEqual(row["norm_hours"], 250)

        runtime_settings_admin.save_values(
            actor=self.rim, data={"workload.norm_hours_half": "200", "workload.norm_hours_admin": "300"}
        )
        section = self._client(self.head).get(url, {"cp_year": YEAR}).context["chair_profile_section"]
        self.assertIn("0,5 ştat — 200 saat", section["norm_source_note"])
        self.assertIn("inzibati vəzifəli — 300 saat", section["norm_source_note"])
        row = next(item for item in section["staff_rows"] if item["user_id"] == str(self.teacher.pk))
        self.assertEqual(row["norm_hours"], 200)

    def test_roster_rate_out_of_range_is_flagged_not_capped(self):
        self.assertEqual(checked_rate([_Row("ştat"), _Row("0,5")]), (Decimal("1.5"), False, ""))
        fraction, external, error = checked_rate([_Row("ştat"), _Row("ştat")])
        self.assertIsNone(fraction)
        self.assertFalse(external)
        self.assertIn("1.5", error)
        self.assertEqual(checked_rate([_Row("s/h")]), (Decimal("0"), True, ""))
        runtime_settings_admin.save_values(actor=self.rim, data={"workload.staff_rate_max": "2"})
        self.assertEqual(checked_rate([_Row("ştat"), _Row("ştat")]), (Decimal("2"), False, ""))
