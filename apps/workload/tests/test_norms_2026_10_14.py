"""Norma «Sistem tənzimləmələri»ndən (sahib 2026-10-14): 1 ştat / 0,5 ştat / inzibati ayrıca + ştat həddi.

Kilidlənən qaydalar:

* defoltlar: profil yoxdur / 1 ştat / inzibati / saathesabı → 500 (əvvəlki davranış), 0,5 ştat → 250,
  digər paylar 1 ştata mütənasib (0,75 → 375, 1,5 → 750);
* hər açarın dəyişməsi hesablanan normanı və doluluq faizini dəyişir — bölgü paneli, «Dərs yüküm» xülasəsi,
  toplu xülasə (kafedra profili / kadr analitikası), RİM icmalı «normadan artıq»;
* ştat həddi (0,25–1,5) yük profilinə yazan yolda (``sync_roster_profile``) tətbiq olunur; 0 = saathesabı azad;
  hədd tənzimləmədən dəyişir.
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.accounts.models import RuntimeSetting
from apps.workload.constants import Activity, TaskStatus
from apps.workload.models import TeacherAssignment, TeacherWorkloadProfile
from apps.workload.public import StaffRateError, chair_staff_load, norm_rule_note, staff_rate_error
from apps.workload.services import (
    resolve_actor,
    teacher_load_panel,
    teacher_workload_summaries,
    teacher_workload_summary,
)
from apps.workload.services.norms import current_rule, norms_for
from apps.workload.services.overview import build_overview
from apps.workload.services.roster_profile import sync_roster_profile
from core import runtime_settings as rs
from core.constants import RoleScopeType

from .factories import TEACHER_PERMS, YEAR, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "wl-norms"}}


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("wl-norms")
        cls.stack = make_structure(cls.org, code="WLN")
        chair = cls.stack["chair"]

        def teacher(username, fraction=None, *, external=False):
            user = User.objects.create_user(username, f"{username}@x.test", "pw")
            activate_member(
                cls.org,
                user,
                "teacher",
                permissions=TEACHER_PERMS,
                scope_unit=chair,
                scope_type=RoleScopeType.COURSE,
            )
            if fraction is not None:
                TeacherWorkloadProfile.objects.create(
                    organization=cls.org,
                    teacher=user,
                    academic_year=YEAR,
                    staff_fraction=Decimal(fraction),
                    is_external=external,
                )
            return user

        cls.none = teacher("wln_none")
        cls.full = teacher("wln_full", "1.00")
        cls.half = teacher("wln_half", "0.50")
        cls.partial = teacher("wln_partial", "0.75")
        cls.max = teacher("wln_max", "1.50")
        cls.hourly = teacher("wln_hourly", "0.00", external=True)
        cls.admin = teacher("wln_admin", "0.50")
        activate_member(cls.org, cls.admin, "dean", permissions=["org.view"], level=80)
        cls.ids = [cls.none.pk, cls.full.pk, cls.half.pk, cls.partial.pk, cls.max.pk, cls.hourly.pk, cls.admin.pk]

        cls.task = make_task(cls.org, chair, status=TaskStatus.DISTRIBUTED)
        cls.row = make_row(cls.task, cls.stack, lecture_total=3000, seminar_total=0)
        for user in (cls.full, cls.half, cls.admin):
            TeacherAssignment.objects.create(
                organization=cls.org, row=cls.row, teacher=user, activity=Activity.LECTURE, hours=300
            )

    def setUp(self):
        rs.invalidate()

    def tearDown(self):
        rs.invalidate()

    def _set(self, **values):
        for key, value in values.items():
            RuntimeSetting.objects.update_or_create(key=f"workload.{key}", defaults={"value": value})
        rs.invalidate()

    def _profiles(self):
        return {p.teacher_id: p for p in TeacherWorkloadProfile.objects.filter(organization=self.org)}


class NormDefaultsTest(_Base):
    def test_defaults_keep_full_norm_and_split_half(self):
        norms = norms_for(self.org, self.ids, self._profiles())
        self.assertEqual(norms[self.none.pk], 500)  # profil yoxdur → 1 ştat (əvvəlki kimi)
        self.assertEqual(norms[self.full.pk], 500)
        self.assertEqual(norms[self.hourly.pk], 500)  # saathesabı: müqayisə bazası 1 ştat (əvvəlki kimi)
        self.assertEqual(norms[self.admin.pk], 500)  # inzibati defolt = 1 ştat normasıdır
        self.assertEqual(norms[self.half.pk], 250)
        self.assertEqual(norms[self.partial.pk], 375)
        self.assertEqual(norms[self.max.pk], 750)
        rule = current_rule()
        self.assertEqual((rule.full, rule.half, rule.admin), (500, 250, 500))
        self.assertEqual((rule.rate_min, rule.rate_max), (Decimal("0.25"), Decimal("1.50")))

    def test_note_shows_current_values(self):
        note = norm_rule_note()
        for part in ("500", "250", "0.25", "1.5"):
            self.assertIn(part, note)

    def test_admin_lookup_is_skipped_when_it_cannot_change_anything(self):
        profiles = {self.full.pk: self._profiles()[self.full.pk]}
        with self.assertNumQueries(0):
            norms_for(self.org, [self.full.pk, self.none.pk], profiles)

    def test_summaries_and_panel_use_the_rule(self):
        summaries = teacher_workload_summaries(organization=self.org, teacher_ids=self.ids, academic_year=YEAR)
        self.assertEqual((summaries[self.half.pk]["norm_hours"], summaries[self.half.pk]["fill_percent"]), (250, 120))
        self.assertTrue(summaries[self.half.pk]["is_over_norm"])
        self.assertEqual((summaries[self.admin.pk]["norm_hours"], summaries[self.admin.pk]["fill_percent"]), (500, 60))
        single = teacher_workload_summary(organization=self.org, teacher=self.half, academic_year=YEAR)
        self.assertEqual(single["norm_hours"], 250)
        cards = {card["teacher_id"]: card for card in teacher_load_panel(self.task)}
        self.assertEqual(cards[str(self.half.pk)]["norm_hours"], 250)
        self.assertEqual(cards[str(self.admin.pk)]["norm_hours"], 500)
        load = chair_staff_load(organization=self.org, teacher_ids=self.ids, academic_year=YEAR)
        self.assertEqual(load["by_teacher"][self.half.pk]["load_band"], "loaded")  # 120%
        self.assertEqual(load["by_teacher"][self.full.pk]["load_band"], "free")  # 60%


@override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
class NormSettingsTest(_Base):
    def test_full_setting_changes_full_proportional_and_missing_profiles(self):
        self._set(norm_hours_full=600)
        norms = norms_for(self.org, self.ids, self._profiles())
        self.assertEqual(
            (norms[self.none.pk], norms[self.full.pk], norms[self.partial.pk], norms[self.max.pk]), (600, 600, 450, 900)
        )
        self.assertEqual(norms[self.half.pk], 250)  # 0,5 ştat ayrıca dəyərdir — törəmir
        summary = teacher_workload_summary(organization=self.org, teacher=self.full, academic_year=YEAR)
        self.assertEqual((summary["norm_hours"], summary["fill_percent"]), (600, 50))
        self.assertIn("600", norm_rule_note())

    def test_half_setting_changes_only_half_rate(self):
        self._set(norm_hours_half=300)
        summaries = teacher_workload_summaries(organization=self.org, teacher_ids=self.ids, academic_year=YEAR)
        self.assertEqual((summaries[self.half.pk]["norm_hours"], summaries[self.half.pk]["fill_percent"]), (300, 100))
        self.assertFalse(summaries[self.half.pk]["is_over_norm"])
        self.assertEqual(summaries[self.full.pk]["norm_hours"], 500)

    def test_admin_setting_applies_to_teachers_with_admin_role(self):
        self._set(norm_hours_admin=200)
        cards = {card["teacher_id"]: card for card in teacher_load_panel(self.task)}
        self.assertEqual(cards[str(self.admin.pk)]["norm_hours"], 200)
        self.assertEqual(cards[str(self.admin.pk)]["fill_percent"], 150)
        self.assertTrue(cards[str(self.admin.pk)]["is_over_norm"])
        self.assertEqual(cards[str(self.half.pk)]["norm_hours"], 250)  # inzibati vəzifəsi yoxdur
        load = chair_staff_load(organization=self.org, teacher_ids=self.ids, academic_year=YEAR)
        self.assertEqual(load["by_teacher"][self.admin.pk]["load_band"], "risk")

    def test_overview_over_norm_counts_follow_the_rule(self):
        rector = User.objects.create_user("wln_rector", "wln_rector@x.test", "pw")
        activate_member(self.org, rector, "rector", permissions=["workload.view", "workload.report"], level=95)

        def over_norm():
            data = build_overview(actor=resolve_actor(rector, self.org), academic_year=YEAR)
            return sum(row["over_norm"] for row in data["chairs"])

        self.assertEqual(over_norm(), 1)  # 0,5 ştat: 300 > 250
        self._set(norm_hours_half=400)
        self.assertEqual(over_norm(), 0)
        self._set(norm_hours_full=250)
        self.assertEqual(over_norm(), 1)  # 1 ştat: 300 > 250 (inzibati 500 qalır)

    def test_invalid_stored_value_falls_back_to_default(self):
        self._set(norm_hours_full=5)  # hədd 100–1500
        self.assertEqual(current_rule().full, 500)


@override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
class StaffRateLimitTest(_Base):
    def _sync(self, fraction, *, external=None, dry_run=True):
        return sync_roster_profile(
            organization=self.org,
            teacher=self.none,
            academic_year=YEAR,
            staff_fraction=fraction,
            is_external=external,
            dry_run=dry_run,
        )

    def test_default_limits_reject_outside_values(self):
        for fraction in ("0.1", "1.75", "2"):
            with self.subTest(fraction=fraction), self.assertRaises(StaffRateError) as caught:
                self._sync(Decimal(fraction))
            self.assertIn("0.25", caught.exception.message)
            self.assertIn("1.5", caught.exception.message)
        for fraction in ("0.25", "0.5", "1", "1.5", "0"):
            with self.subTest(fraction=fraction):
                after = self._sync(Decimal(fraction))["after"]["staff_fraction"]
                self.assertEqual(Decimal(after), Decimal(fraction))
        self.assertFalse(TeacherWorkloadProfile.objects.filter(teacher=self.none).exists())  # dry-run

    def test_limits_follow_settings(self):
        self._set(staff_rate_max="2", staff_rate_min="0.5")
        self.assertEqual(staff_rate_error(Decimal("2")), "")
        self.assertTrue(staff_rate_error(Decimal("0.25")))
        self._sync(Decimal("2"), dry_run=False)
        self.assertEqual(TeacherWorkloadProfile.objects.get(teacher=self.none).staff_fraction, Decimal("2.00"))
        with self.assertRaises(StaffRateError):
            self._sync(Decimal("2.5"))
        self.assertEqual(staff_rate_error("abc"), staff_rate_error(None))
