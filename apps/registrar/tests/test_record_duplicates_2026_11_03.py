"""Akademik qeyd: eyni fənnin eyni semestrdə imtahansız boş dublikatı göstərilmir (SYS-1 yoxlaması).

Sətir siyahısı (``build_student_overall_record``) və ucuz sayğac (``count_student_record_rows``) EYNİ çoxluqdan
çıxır — biri gizlədib digəri saysaydı tab nişanı «36», siyahı 35 göstərərdi.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from apps.organizations.models import AcademicPeriod, OrgUnit
from apps.registrar import finals, transcript
from apps.registrar.models import CourseOffering, Enrollment
from core.constants import OrgUnitType
from core.rls import bypass_rls

from .test_exam_eligibility_frozen import _seed_org, _seed_period, _seed_student


class EmptyDuplicateIsHidden(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = _seed_org("dup")
        cls.period = _seed_period(cls.ctx, name="2025/2026 Yaz", year="2025/2026", start="2026-02-01", end="2026-06-30")
        cls.student, _record, cls.home = _seed_student(cls.ctx, "dup_s", cls.period)
        with bypass_rls():
            other_group = OrgUnit.objects.create(
                organization=cls.ctx["org"], name="QR-102", slug="dup-grp2", unit_type=OrgUnitType.GROUP
            )
            guest_offering = CourseOffering.objects.create(
                organization=cls.ctx["org"], subject=cls.ctx["subject"], period=cls.period, group=other_group
            )
            cls.guest = Enrollment.objects.create(
                organization=cls.ctx["org"], student=cls.student, offering=guest_offering
            )

    def _rows(self):
        data = transcript.build_student_overall_record(student=self.student, organization=self.ctx["org"])
        return [row for sem in data["semesters"] for row in sem["rows"]]

    def _count(self):
        return transcript.count_student_record_rows(student=self.student, organization=self.ctx["org"])

    def test_both_empty_in_an_ended_semester_shows_one(self):
        """Bitmiş semestrdə eyni fənn iki dəfə «nəticə yoxdur» göstərilmir — daha çox komponenti olan qalır."""
        from apps.registrar.models import AssessmentComponent, ComponentScore

        with bypass_rls():
            component = AssessmentComponent.objects.create(
                organization=self.ctx["org"], offering=self.guest.offering, name="Kollokvium 1", kind="kollokvium"
            )
            ComponentScore.objects.create(
                organization=self.ctx["org"], component=component, enrollment=self.guest, score=Decimal("7")
            )
        self.assertEqual([row["enrollment_id"] for row in self._rows()], [self.guest.pk])
        self.assertEqual(self._count(), 1)

    def test_both_empty_in_the_current_semester_both_shown(self):
        with bypass_rls():
            AcademicPeriod.objects.filter(pk=self.period.pk).update(end_date="2099-06-30")
        self.assertEqual(len(self._rows()), 2)
        self.assertEqual(self._count(), 2)

    def test_scored_row_hides_the_empty_twin(self):
        with bypass_rls():
            finals.set_exam_score(enrollment=self.home, score=Decimal("30"), by_user=self.ctx["teacher"])
        rows = self._rows()
        self.assertEqual([row["enrollment_id"] for row in rows], [self.home.pk])
        self.assertEqual(self._count(), 1)

    def test_two_scored_rows_stay_visible(self):
        with bypass_rls():
            finals.set_exam_score(enrollment=self.home, score=Decimal("30"), by_user=self.ctx["teacher"])
            finals.set_exam_score(enrollment=self.guest, score=Decimal("10"), by_user=self.ctx["teacher"])
        self.assertEqual(len(self._rows()), 2)
        self.assertEqual(self._count(), 2)
