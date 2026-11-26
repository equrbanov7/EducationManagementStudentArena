"""Sahib 2026-11-26 (Kalo / Ghaffar, 04-əcnəbilər 2026): qrupa yeni yaradılan tələbə qrupun cari jurnallarına düşür.

Əvvəl qəbul / RİM «Yeni yarat» yolu yalnız reyestr qeydini yazırdı — tələbə reyestrdə görünür, jurnalda görünmürdü.
Köçürmə (legacy) yolu ``join_group_journals=False`` verir — öz yazılışlarını özü yazır.
"""

from __future__ import annotations

import datetime

from apps.accounts.services.intake import create_account, student_role
from apps.organizations.models import AcademicPeriod
from apps.registrar.models import CourseOffering, Enrollment, Subject
from core.rls import bypass_rls

from .test_first_year_data_2026_10_27 import PLACEHOLDER, _FirstYearBase


class IntakeJoinsGroupJournalsTest(_FirstYearBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        today = datetime.date.today()
        with bypass_rls():
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız semestri",
                academic_year="2026/2027",
                start_date=today - datetime.timedelta(days=60),
                end_date=today + datetime.timedelta(days=60),
                is_current=True,
                is_active=True,
            )
            subject = Subject.objects.create(organization=cls.org, code="AZD-1", name="Azərbaycan dili")
            cls.offering = CourseOffering.objects.create(
                organization=cls.org, subject=subject, period=cls.period, group=cls.g_a, is_active=True
            )
            other = Subject.objects.create(organization=cls.org, code="AZD-2", name="Ədəbiyyat")
            cls.other_group = CourseOffering.objects.create(
                organization=cls.org, subject=other, period=cls.period, group=cls.g_b, is_active=True
            )

    def _create(self, *, join=True, n=1):
        values = {
            "username": f"ij.st{n}",
            "email": PLACEHOLDER.format(900 + n),
            "first_name": "Yeni",
            "last_name": "Tələbə",
            "fin": None,
            "patronymic": "Ata",
            "gender": "unspecified",
            "birth_date": None,
            "phone": "",
            "student_code": "",
        }
        with bypass_rls():
            user, _password = create_account(
                organization=self.org,
                kind="student",
                values=values,
                role=student_role(self.org),
                actor=self.admin,
                student_targets={"group": self.g_a, "program": self.program, "admission_year": 2026},
                group_name=self.g_a.name,
                join_group_journals=join,
            )
        return user

    def test_new_student_is_enrolled_in_the_groups_current_journals_only(self):
        user = self._create()
        with bypass_rls():
            rows = list(Enrollment.objects.filter(student=user).values_list("offering_id", "status", "kind"))
        self.assertEqual(rows, [(self.offering.pk, "enrolled", "mandatory")])

    def test_legacy_path_opts_out(self):
        user = self._create(join=False, n=2)
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(student=user).exists())
