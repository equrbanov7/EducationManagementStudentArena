"""Yeni semestr düsturu (sahib 2026-10-10 «Yeni qayda var»): aktivlik 5 + 5 və midterm tavanı 20 → 30.

* :func:`activity_kinds.activity` — saf qayda: yalnız seminar / yalnız lab / hər ikisi (5 + 5) / hər ikisi
  planlı, amma lab balı hələ yoxdur / RİM-də bölgü söndürülüb (köhnə birgə orta);
* :func:`activity_kinds.bits_map` — fənnin növləri: təsdiqlənmiş plan → cədvəl slotları; balı olan növ
  həmişə əlavə olunur;
* «Midterm» komponentinin tavanı: QALDIRMAQ bal olsa da (bal saxlanılır), ENDİRMƏK yalnız yeni tavandan böyük
  bal yoxdursa; ``save_components`` qoruması; DB qoruyucusu (miqrasiya ``0087``) eyni qaydanı tətbiq edir, başqa
  növ / rubrikli komponent isə əvvəlki kimi bağlıdır; ``normalize_interim_components`` dry-run / ``--apply``.

Giriş balının bütün yollar üzrə pariteti və sorğu büdcələri ``test_entry_standard_parity``-dədir.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from io import StringIO

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings

import pytest

from apps.registrar import activity_kinds, gradebook, interim_components, journal_extras
from apps.registrar.management.commands import normalize_interim_components as normalize_command
from apps.registrar.models import (
    AssessmentComponent,
    ComponentKind,
    ComponentScore,
    Curriculum,
    CurriculumSubject,
    PlanStatus,
    ScheduleSlot,
)
from apps.registrar.tests.test_journal_rules import _setup_offering
from core.rls import bypass_rls

SEM, LAB = activity_kinds.SEMINAR, activity_kinds.LAB


def _totals(*marks):
    totals = activity_kinds.LessonTotals()
    for kind, score in marks:
        totals.add(kind, Decimal(score))
    return totals


# ── Aktivlik qaydası (saf) ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "marks, bits, split, value, is_split",
    [
        # yalnız seminar fənni → seminar ortası (10-luq şkala)
        (((SEM, 8), (SEM, 9)), activity_kinds.SEMINAR_BIT, True, "8.50", False),
        # yalnız laboratoriya fənni → lab ortası
        (((LAB, 7), (LAB, 10)), activity_kinds.LAB_BIT, True, "8.50", False),
        # seminar + lab → round2(8.5 / 2) + round2(6 / 2) = 4.25 + 3.00
        (((SEM, 8), (SEM, 9), (LAB, 6)), activity_kinds.BOTH, True, "7.25", True),
        # hər iki növ planlıdır, lab balı hələ yoxdur → yalnız seminarın yarısı: round2(9.5 / 2)
        (((SEM, 10), (SEM, 9)), activity_kinds.BOTH, True, "4.75", True),
        # yarım-yuxarı: 25 / 3 = 8.333… → 4.17; lab 9 / 2 = 4.50
        (((SEM, 8), (SEM, 8), (SEM, 9), (LAB, 9)), activity_kinds.BOTH, True, "8.67", True),
        # RİM-də bölgü söndürülüb → köhnə birgə orta: 23 / 3 = 7.67
        (((SEM, 8), (SEM, 9), (LAB, 6)), activity_kinds.BOTH, False, "7.67", False),
        # heç bal yoxdur → 0
        ((), activity_kinds.BOTH, True, "0", False),
    ],
)
def test_activity_rule(marks, bits, split, value, is_split):
    detail = activity_kinds.activity(_totals(*marks), bits, split_enabled=split)
    assert (detail.value, detail.split) == (Decimal(value), is_split)


def test_activity_detail_carries_means_and_halves():
    detail = activity_kinds.activity(_totals((SEM, 8), (SEM, 9), (LAB, 6)), activity_kinds.BOTH, split_enabled=True)
    assert (detail.seminar_mean, detail.lab_mean) == (Decimal("8.50"), Decimal("6.00"))
    assert (detail.seminar_part, detail.lab_part) == (Decimal("4.25"), Decimal("3.00"))


def test_offering_kinds_are_read_only_when_needed():
    """Açılışın maskası (sorğu) yalnız tələbənin balları TƏK növdə olanda və bölgü açıq olanda oxunur."""
    calls = []

    def lazy_bits():
        calls.append(1)
        return activity_kinds.BOTH

    both = activity_kinds.activity(_totals((SEM, 8), (LAB, 6)), lazy_bits, split_enabled=True)
    assert (both.value, calls) == (Decimal("7.00"), [])
    pooled = activity_kinds.activity(_totals((SEM, 8)), lazy_bits, split_enabled=False)
    assert (pooled.value, calls) == (Decimal("8.00"), [])
    half = activity_kinds.activity(_totals((SEM, 8)), lazy_bits, split_enabled=True)
    assert (half.value, calls) == (Decimal("4.00"), [1])


# ── Fənnin növləri (SQL maskası) ─────────────────────────────────────────────


class ActivityKindsResolverTest(TestCase):
    """Planlı növlər (təsdiqlənmiş plan → cədvəl slotları) ∪ balı olan növlər — TƏK sorğu."""

    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "akr")

    def _bits(self):
        with bypass_rls():
            return activity_kinds.bits_map([self.offering.id])[self.offering.id]

    def _slot(self, kind):
        ScheduleSlot.objects.create(
            organization=self.org,
            offering=self.offering,
            weekday=1,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(10, 20),
            kind=kind,
        )

    def test_schedule_slots_then_scored_kinds(self):
        self.assertEqual(self._bits(), 0)
        with bypass_rls():
            self._slot(LAB)
        self.assertEqual(self._bits(), activity_kinds.LAB_BIT)
        with bypass_rls():
            lesson = gradebook.create_lesson(
                allow_past=True, offering=self.offering, date=datetime.date(2026, 9, 21), kind=SEM
            )
            gradebook.save_marks(
                enforce_day=False,
                offering=self.offering,
                entries=[
                    {"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": "present", "score": 8}
                ],
                by_user=self.teacher,
            )
        self.assertEqual(self._bits(), activity_kinds.BOTH)
        with bypass_rls():
            with self.assertNumQueries(1):  # plan + dərs yükü + slotlar + ballar — TƏK sorğu
                activity_kinds.bits_map([self.offering.id])

    def test_approved_plan_wins_over_schedule(self):
        with bypass_rls():
            self._slot(LAB)
            CurriculumSubject.objects.filter(curriculum=self.curriculum, subject=self.subject).update(
                seminar_hours=30, lab_hours=0
            )
            Curriculum.objects.filter(pk=self.curriculum.pk).update(status=PlanStatus.APPROVED)
        self.assertEqual(self._bits(), activity_kinds.SEMINAR_BIT)


# ── Midterm tavanı: 20 → 30 (bal saxlanılır) ─────────────────────────────────


def _midterm(case, max_score, score=None):
    component = AssessmentComponent.objects.create(
        organization=case.org,
        offering=case.offering,
        name="Midterm",
        kind=ComponentKind.KOLLOKVIUM,
        max_score=max_score,
        order=1,
    )
    if score is not None:
        ComponentScore.objects.create(
            organization=case.org, component=component, enrollment=case.enrollment, score=Decimal(score)
        )
    return component


class MidtermMaxUpgradeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "mmx")

    def test_raise_20_to_30_keeps_existing_score(self):
        with bypass_rls():
            component = _midterm(self, 20, "18")
            ensured = journal_extras.ensure_kollokviums(self.offering)
            options = journal_extras.interim_score_options(self.offering)
            component.refresh_from_db()
            score = ComponentScore.objects.get(component=component).score
            entry = gradebook.entry_score_for(self.enrollment, 50)
        self.assertEqual([c.id for c in ensured], [component.id])
        self.assertEqual((component.max_score, score), (30, Decimal("18")))
        self.assertEqual(options, list(range(0, 31)))
        # davamiyyət 10 (qayıb yoxdur) + aktivlik 0 + midterm 18; sərbəst iş yoxdur.
        self.assertEqual(entry, Decimal("28"))

    @override_settings(ACADEMIC_SELFWORK_ENABLED=True)
    def test_lowering_waits_until_no_score_exceeds_new_max(self):
        with bypass_rls():
            component = _midterm(self, 30, "25")
            with self.assertLogs("apps.registrar.interim_components", level="WARNING"):
                journal_extras.ensure_kollokviums(self.offering)
            options = journal_extras.interim_score_options(self.offering)
            component.refresh_from_db()
            self.assertEqual(component.max_score, 30)  # 25 > 20 → tavan saxlanılır
            self.assertEqual(options, list(range(0, 31)))  # seçim yazılmış balı əhatə edir
            ComponentScore.objects.filter(component=component).update(score=Decimal("15"))
            journal_extras.ensure_kollokviums(self.offering)
            component.refresh_from_db()
        self.assertEqual(component.max_score, 20)

    def test_save_components_allows_raising_but_not_lowering_with_evidence(self):
        with bypass_rls():
            component = _midterm(self, 20, "18")
            gradebook.save_components(
                offering=self.offering,
                definitions=[{"id": component.id, "name": "Midterm", "max_score": 30}],
                by_user=self.teacher,
            )
            component.refresh_from_db()
            self.assertEqual(component.max_score, 30)
            with self.assertRaises(ValidationError) as caught:
                gradebook.save_components(
                    offering=self.offering,
                    definitions=[{"id": component.id, "name": "Midterm", "max_score": 10}],
                    by_user=self.teacher,
                )
            component.refresh_from_db()
        self.assertEqual(caught.exception.code, "component_evidence_protected")
        self.assertEqual(component.max_score, 30)

    def test_generic_component_max_stays_protected(self):
        with bypass_rls():
            generic = AssessmentComponent.objects.create(
                organization=self.org, offering=self.offering, name="Layihə", max_score=10, order=2
            )
            ComponentScore.objects.create(
                organization=self.org, component=generic, enrollment=self.enrollment, score=Decimal("7")
            )
            with self.assertRaises(ValidationError):
                gradebook.save_components(
                    offering=self.offering,
                    definitions=[{"id": generic.id, "name": "Layihə", "max_score": 20}],
                    by_user=self.teacher,
                )
            self.assertFalse(interim_components.max_change_allowed(generic, 20))

    def test_database_refusal_keeps_old_max_without_crashing(self):
        """Tətbiq yoxlamasından yan keçən dəyişikliyi DB rədd edəndə (yarış, miqrasiya hələ yoxdur) jurnal yıxılmır."""
        with bypass_rls():
            component = _midterm(self, 30, "18")
            with self.assertLogs("apps.registrar.interim_components", level="WARNING"):
                interim_components._save_max(component, 10)  # 18 > 10 → PostgreSQL qoruyucusu rədd edir
            self.assertEqual(component.max_score, 30)
            component.refresh_from_db()
        self.assertEqual(component.max_score, 30)


class ComponentMaxDatabaseGuardTest(TestCase):
    """Miqrasiya ``0087``: DB qoruyucusu yalnız rubriksiz aralıq komponentinin tavanını, bütün ballar sığırsa, buraxır."""

    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "cmg")

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL trigger")

    def _update(self, component, assignment, values=()):
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE registrar_assessmentcomponent SET {assignment} WHERE id = %s", [*values, component.id]
            )

    def test_interim_max_follows_scores_other_identity_stays_locked(self):
        with bypass_rls():
            midterm = _midterm(self, 20, "18")
            self._update(midterm, "max_score = %s", [30])  # qaldırmaq — bal sığır
            self._update(midterm, "max_score = %s", [18])  # endirmək — 18 hələ sığır
            for assignment, values in (("max_score = %s", [17]), ("name = %s", ["Ara imtahan"])):
                with self.subTest(assignment=assignment, values=values), self.assertRaises(IntegrityError):
                    self._update(midterm, assignment, values)
            generic = AssessmentComponent.objects.create(
                organization=self.org, offering=self.offering, name="Layihə", max_score=10, order=2
            )
            ComponentScore.objects.create(
                organization=self.org, component=generic, enrollment=self.enrollment, score=Decimal("7")
            )
            with self.assertRaises(IntegrityError):
                self._update(generic, "max_score = %s", [20])
            midterm.refresh_from_db()
            generic.refresh_from_db()
        self.assertEqual((midterm.max_score, generic.max_score), (18, 10))


class NormalizeMidtermMaxCommandTest(TestCase):
    """``normalize_interim_components``: dry-run yalnız hesabat verir; ``--apply`` tavanı qaldırır (audit ilə)."""

    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "nmx")

    def _run(self, *extra):
        out = StringIO()
        call_command("normalize_interim_components", "--organization", self.org.slug, *extra, stdout=out)
        return out.getvalue()

    def test_dry_run_then_apply_raises_max_and_keeps_score(self):
        with bypass_rls():
            component = _midterm(self, 20, "18")
        dry = self._run()
        self.assertIn("DRY-RUN", dry)
        self.assertIn("tavanı 0–30-ə gətirilən Midterm 1", dry)
        with bypass_rls():
            component.refresh_from_db()
        self.assertEqual(component.max_score, 20)  # dry-run heç nə yazmır

        applied = self._run("--apply")
        self.assertIn("YAZILDI", applied)
        self.assertIn("tavanı 0–30-ə gətirilən Midterm 1", applied)
        audit_log = django_apps.get_model("audit", "AuditLog")
        with bypass_rls():
            component.refresh_from_db()
            score = ComponentScore.objects.get(component=component).score
            audit = audit_log.objects.filter(organization=self.org, reason=normalize_command.AUDIT_REASON).get()
        self.assertEqual((component.max_score, score), (30, Decimal("18")))
        self.assertEqual(audit.changes["midterm_max"], [20, 30])

        again = self._run("--apply")
        self.assertIn("dəyişən 0", again)
        self.assertIn("tavanı 0–30-ə gətirilən Midterm 0", again)

    @override_settings(ACADEMIC_SELFWORK_ENABLED=True)
    def test_blocked_lowering_is_reported_not_applied(self):
        with bypass_rls():
            component = _midterm(self, 30, "25")
        report = self._run("--apply")
        self.assertIn("tavanı endirilə bilməyən (yeni tavandan böyük bal var) 1", report)
        with bypass_rls():
            component.refresh_from_db()
        self.assertEqual(component.max_score, 30)
