"""Rəsmi transkriptdə hələ başlamamış semestr göstərilmir (sahib 2026-10-26).

MR-000003/4 yoxlamasında möhürlü transkriptdə payızda hələ başlamamış «Yaz» semestri də çıxırdı.
"""

from __future__ import annotations

import datetime as dt

from django.test import TestCase

from apps.organizations.models import AcademicPeriod
from apps.registrar import transcript
from apps.registrar.models import CourseOffering, Enrollment
from core.constants import AcademicPeriodType
from core.rls import bypass_rls

from .world import build_world, download_transcript


class StartedOnlyTranscriptTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("qkuso")
        w = cls.w
        with bypass_rls():
            future = AcademicPeriod.objects.create(
                organization=w["org"],
                name="2099/2100 Yaz",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2099/2100",
                start_date="2100-02-01",
                end_date="2100-06-30",
            )
            offering = CourseOffering.objects.create(
                organization=w["org"], subject=w["enrollment"].offering.subject, period=future, group=w["g1"]
            )
            Enrollment.objects.create(organization=w["org"], student=w["student"], offering=offering)

    def _periods(self, **kwargs):
        w = self.w
        with bypass_rls():
            data = transcript.build_student_transcript(
                student=w["student"], organization=w["org"], program=w["record"].program, **kwargs
            )
        return [bucket["period"].name for bucket in data["semesters"]]

    def test_default_keeps_every_semester(self):
        self.assertIn("2099/2100 Yaz", self._periods())

    def test_started_only_drops_future_semester(self):
        periods = self._periods(started_only=True, today=dt.date(2026, 10, 26))
        self.assertNotIn("2099/2100 Yaz", periods)
        self.assertIn("2024/2025 Payız", periods)

    def test_sealed_pdf_is_issued(self):
        self.assertEqual(download_transcript(self.w).status_code, 200)
