"""DELTA ``graduation`` fazası — cari jurnallarda olmayan, müddəti bitmiş tələbələrin «Məzun etmə» əmri (sintetik).

Sahib 2026-10-25: «bu ilin jurnalında adı yoxdursa — məzun et; kəsilib, bitirməyibsə — etmə». Yoxlanılır:
müddəti bitmiş + son kurs jurnalı olan → ``graduated`` (MZN-SINX-2026); yeni və ya köhnə sistemin cari jurnalında
olan, köhnə sistemdə azad edilmiş → toxunulmur; müddəti bitməyən, qəbul ili bilinməyən, son kursdan əvvəl
kəsilən → «yoxlanmalı»; dry-run heç nə yazmır; ikinci qaçış 0 yazı; faza default fazalara DAXİL DEYİL.
"""

import datetime as dt

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.legacy_import.services.delta.apply import DEFAULT_PHASES, PHASES, execute
from apps.legacy_import.services.delta.graduation import ORDER_DATE, ORDER_NUMBER, study_years
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import services
from apps.registrar.models import (
    Curriculum,
    EnrollmentKind,
    Program,
    StudentAcademicRecord,
    StudentMovement,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType
from core.rls import bypass_rls

User = get_user_model()


def _row(pk, fin, *, azad=0):
    return {
        "id": pk,
        "first_name": f"Ad{pk}",
        "last_name": f"Soyad{pk}",
        "father_name": "",
        "fincode": fin,
        "sex": 1,
        "gender": None,
        "birthday": "",
        "group_id": 900,
        "speciality_id": 5,
        "entry_year": "2022",
        "azadedildi": azad,
        "is_new": False,
    }


def _bundle():
    return {
        "snapshot": {"phases": ["graduation"], "full_semesters": [14]},
        "periods": [{"id": 14, "name": "2026/2027 Payız", "is_current": "1", "type": "autumn"}],
        "groups": [],
        "subjects": [],
        "workers": [],
        "journals": [{"id": 1, "semestr": "14", "students_id": '["3"]', "groups_id": '["900"]'}],
        "students": [_row(3, "FIN0003")],
        "expelled_students": [_row(7, "FIN0007", azad=1)],
    }


class GraduationPhaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = User.objects.create_superuser("grad_actor", "grad-actor@example.test", "x")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Grad Univ",
                slug="grad-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.actor,
                status="active",
                is_active=True,
            )
            group = OrgUnit.objects.create(organization=cls.org, name="222 A", slug="g-222a", unit_type="group")
            bachelor = Program.objects.create(organization=cls.org, code="BAK", name="Bakalavr", ects_total=240)
            master = Program.objects.create(
                organization=cls.org, code="MAG", name="Magistr", degree_level="master", ects_total=120
            )

            def period(name, year, start, current=False):
                return AcademicPeriod.objects.create(
                    organization=cls.org,
                    name=name,
                    academic_year=year,
                    period_type=AcademicPeriodType.SEMESTER,
                    start_date=start,
                    end_date=start + dt.timedelta(days=120),
                    is_current=current,
                )

            early = period("Payız", "2022/2023", dt.date(2022, 9, 15))
            final = period("Payız", "2025/2026", dt.date(2025, 9, 15))
            current = period("Payız", "2026/2027", dt.date(2026, 9, 15), current=True)
            subject = Subject.objects.create(organization=cls.org, code="S-1", name="Fənn")
            role = cls.org.roles.get(name="student")
            cls.records = {}
            plan = {
                1: (bachelor, 2022, final),  # məzun
                2: (bachelor, 2022, current),  # yeni sistemin cari jurnalında
                3: (bachelor, 2022, final),  # köhnə sistemin cari jurnalında
                4: (bachelor, 2024, final),  # müddəti bitməyib
                5: (bachelor, 1950, final),  # qəbul ili bilinmir
                6: (bachelor, 2022, early),  # son kursdan əvvəl kəsilib
                7: (bachelor, 2022, final),  # köhnə sistemdə azad edilib
                8: (master, 2024, final),  # magistr — məzun
            }
            for number, (program, year, last) in plan.items():
                user = User.objects.create_user(f"grad.s{number}", f"g{number}@example.test", "x")
                UserProfile.objects.filter(user=user).update(fin=f"FIN000{number}")
                Membership.objects.create(user=user, organization=cls.org, role=role, is_primary=True, is_active=True)
                curriculum, _ = Curriculum.objects.get_or_create(
                    organization=cls.org, program=program, admission_year=year
                )
                record = StudentAcademicRecord.objects.create(
                    organization=cls.org,
                    student=user,
                    program=program,
                    curriculum=curriculum,
                    group=group,
                    admission_year=year,
                    status="enrolled",
                    is_active=True,
                )
                services.enroll_student_in_subject(
                    record=record, subject=subject, period=last, kind=EnrollmentKind.MANDATORY
                )
                cls.records[number] = record

    def _run(self, *, apply):
        with bypass_rls():
            return execute(
                organization=self.org,
                actor=self.actor,
                bundle=_bundle(),
                apply=apply,
                until=dt.date(2026, 10, 25),
                tag="grad-test",
                phases=("graduation",),
            )

    def _status(self, number):
        with bypass_rls():
            return StudentAcademicRecord.objects.get(pk=self.records[number].pk).status

    def test_phase_is_opt_in(self):
        self.assertIn("graduation", PHASES)
        self.assertNotIn("graduation", DEFAULT_PHASES)

    def test_study_years_from_ects(self):
        self.assertEqual(study_years(Program(ects_total=240)), 4)
        self.assertEqual(study_years(Program(ects_total=120, degree_level="master")), 2)
        self.assertEqual(study_years(Program(ects_total=0, degree_level="master")), 2)

    def test_dry_run_writes_nothing(self):
        run = self._run(apply=False)
        self.assertEqual(run.counters["graduation.graduated"], 2)
        self.assertEqual(self._status(1), "enrolled")
        with bypass_rls():
            self.assertFalse(StudentMovement.objects.filter(organization=self.org).exists())

    def test_apply_graduates_only_finished_and_second_run_is_noop(self):
        counters = self._run(apply=True).counters
        self.assertEqual(counters["graduation.graduated"], 2)
        self.assertEqual(counters["graduation.untouched.in_journal"], 1)
        self.assertEqual(counters["graduation.untouched.in_legacy_journal"], 1)
        self.assertEqual(counters["graduation.untouched.legacy_expelled"], 1)
        self.assertEqual(counters["graduation.review.period_not_ended"], 1)
        self.assertEqual(counters["graduation.review.year_unknown"], 1)
        self.assertEqual(counters["graduation.review.left_before_final_year"], 1)
        expected = {1: "graduated", 2: "enrolled", 3: "enrolled", 4: "enrolled", 5: "enrolled"}
        expected.update({6: "enrolled", 7: "enrolled", 8: "graduated"})
        self.assertEqual({number: self._status(number) for number in self.records}, expected)
        with bypass_rls():
            movement = StudentMovement.objects.get(record=self.records[1])
            self.assertEqual(
                (movement.kind, movement.order_number, movement.order_date), ("graduation", ORDER_NUMBER, ORDER_DATE)
            )
        again = self._run(apply=True).counters
        self.assertEqual(again["graduation.graduated"], 0)
        self.assertEqual(again["written.student_movements"], 0)
        with bypass_rls():
            self.assertEqual(StudentMovement.objects.filter(organization=self.org).count(), 2)
