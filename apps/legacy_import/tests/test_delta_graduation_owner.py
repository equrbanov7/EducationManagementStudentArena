"""DELTA ``graduation`` fazasının sahib bayraqları (2026-10-25) — sintetik.

``graduate_year_unknown`` → qəbul ili bilinməyən «yoxlanmalı» tələbə məzun (``MZN-SINX-2026``);
``leave_unfinished`` → bitirməyən / son kursdan əvvəl kəsilən / tarixçəsiz tələbə akademik məzuniyyətə
(``AM-SINX-2026``); ``deactivate_emptied_groups`` → boşalan qrup arxivlənir (audit + iz), aktiv qeydi / açıq dövr
açılışı olan qrup qalır; «silinməli» qabı toxunulmur; bayraqsız paket köhnə davranışdadır; dry-run heç nə yazmır;
ikinci qaçış 0 yazı.
"""

import datetime as dt

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.legacy_import.services.delta.apply import execute
from apps.legacy_import.services.delta.graduation_owner import LEAVE_ORDER_NUMBER, LEAVE_UNTIL
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import services
from apps.registrar.models import (
    CourseOffering,
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
FLAGS = {"graduate_year_unknown": True, "leave_unfinished": True, "deactivate_emptied_groups": True}


def _bundle(**flags):
    return {
        "snapshot": {"phases": ["graduation"], "full_semesters": [14], **flags},
        "periods": [{"id": 14, "name": "2026/2027 Payız", "is_current": "1", "type": "autumn"}],
        "groups": [],
        "subjects": [],
        "workers": [],
        "journals": [],
        "students": [],
        "expelled_students": [],
    }


class GraduationOwnerFlagTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = User.objects.create_superuser("own_actor", "own-actor@example.test", "x")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Owner Univ",
                slug="owner-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.actor,
                status="active",
                is_active=True,
            )
            cls.groups = {
                key: OrgUnit.objects.create(organization=cls.org, name=name, slug=f"g-{key}", unit_type="group")
                for key, name in (
                    ("empty", "0000 A"),
                    ("mixed", "0000 B"),
                    ("open", "0000 C"),
                    ("junk", "Silinməlidir"),
                )
            }
            bachelor = Program.objects.create(organization=cls.org, code="BAK", name="Bakalavr", ects_total=240)

            def period(year, start, current=False):
                return AcademicPeriod.objects.create(
                    organization=cls.org,
                    name="Payız",
                    academic_year=year,
                    period_type=AcademicPeriodType.SEMESTER,
                    start_date=start,
                    end_date=start + dt.timedelta(days=120),
                    is_current=current,
                )

            early = period("2022/2023", dt.date(2022, 9, 15))
            final = period("2025/2026", dt.date(2025, 9, 15))
            current = period("2026/2027", dt.date(2026, 9, 15), current=True)
            subject = Subject.objects.create(organization=cls.org, code="S-1", name="Fənn")
            CourseOffering.objects.create(
                organization=cls.org, subject=subject, period=current, group=cls.groups["open"]
            )
            role = cls.org.roles.get(name="student")
            cls.records = {}
            plan = {
                1: (1950, "empty", final),  # qəbul ili bilinmir → məzun; qrup boşalır
                2: (1950, "empty", None),  # qəbul ili bilinmir, jurnalsız → məzun
                3: (1950, "mixed", final),  # məzun, amma qrupda aktiv (məzuniyyət) qalır
                4: (2024, "mixed", final),  # müddəti bitməyib → akademik məzuniyyət
                5: (2022, "mixed", early),  # son kursdan əvvəl kəsilib → akademik məzuniyyət
                6: (2022, "mixed", None),  # jurnal tarixçəsi yoxdur → akademik məzuniyyət
                7: (1950, "open", final),  # məzun; qrupun cari dövr açılışı var → qrup qalır
                8: (1950, "junk", final),  # «Silinməlidir» qabı → toxunulmur
            }
            for number, (year, group_key, last) in plan.items():
                user = User.objects.create_user(f"own.s{number}", f"o{number}@example.test", "x")
                Membership.objects.create(user=user, organization=cls.org, role=role, is_primary=True, is_active=True)
                curriculum, _ = Curriculum.objects.get_or_create(
                    organization=cls.org, program=bachelor, admission_year=year
                )
                record = StudentAcademicRecord.objects.create(
                    organization=cls.org,
                    student=user,
                    program=bachelor,
                    curriculum=curriculum,
                    group=cls.groups[group_key],
                    admission_year=year,
                    status="enrolled",
                    is_active=True,
                )
                if last is not None:
                    services.enroll_student_in_subject(
                        record=record, subject=subject, period=last, kind=EnrollmentKind.MANDATORY
                    )
                cls.records[number] = record

    def _run(self, *, apply, **flags):
        with bypass_rls():
            return execute(
                organization=self.org,
                actor=self.actor,
                bundle=_bundle(**flags),
                apply=apply,
                until=dt.date(2026, 10, 25),
                tag="own-test",
                phases=("graduation",),
            )

    def _statuses(self):
        with bypass_rls():
            return {
                number: StudentAcademicRecord.objects.get(pk=record.pk).status
                for number, record in self.records.items()
            }

    def _active_groups(self):
        with bypass_rls():
            return {key: OrgUnit.objects.get(pk=unit.pk).is_active for key, unit in self.groups.items()}

    def test_without_flags_everything_stays_for_review(self):
        counters = self._run(apply=True).counters
        self.assertEqual(counters["graduation.review.year_unknown"], 4)
        self.assertEqual(counters["graduation.graduated"], 0)
        self.assertEqual(set(self._statuses().values()), {"enrolled"})

    def test_dry_run_writes_nothing(self):
        counters = self._run(apply=False, **FLAGS).counters
        self.assertEqual(counters["graduation.graduated_year_unknown"], 4)
        self.assertEqual(counters["graduation.leave"], 3)
        self.assertEqual(counters["graduation.groups.deactivated"], 1)
        self.assertEqual(set(self._statuses().values()), {"enrolled"})
        self.assertTrue(all(self._active_groups().values()))
        with bypass_rls():
            self.assertFalse(StudentMovement.objects.filter(organization=self.org).exists())

    def test_apply_graduates_leaves_archives_and_second_run_is_noop(self):
        counters = self._run(apply=True, **FLAGS).counters
        self.assertEqual(counters["graduation.graduated_year_unknown"], 4)
        self.assertEqual(counters["graduation.leave.period_not_ended"], 1)
        self.assertEqual(counters["graduation.leave.left_before_final_year"], 1)
        self.assertEqual(counters["graduation.leave.no_journal_history"], 1)
        self.assertEqual(counters["graduation.review.junk_group"], 1)
        self.assertEqual(counters["graduation.groups.deactivated"], 1)
        self.assertEqual(counters["graduation.groups.kept.active_records"], 1)
        self.assertEqual(counters["graduation.groups.kept.open_period"], 1)
        expected = {1: "graduated", 2: "graduated", 3: "graduated", 4: "academic_leave"}
        expected.update({5: "academic_leave", 6: "academic_leave", 7: "graduated", 8: "enrolled"})
        self.assertEqual(self._statuses(), expected)
        self.assertEqual(self._active_groups(), {"empty": False, "mixed": True, "open": True, "junk": True})
        with bypass_rls():
            leave = StudentMovement.objects.get(record=self.records[4])
            self.assertEqual(
                (leave.kind, leave.order_number, leave.effective_until),
                ("academic_leave", LEAVE_ORDER_NUMBER, LEAVE_UNTIL),
            )
            unit = OrgUnit.objects.get(pk=self.groups["empty"].pk)
            self.assertEqual(unit.settings["graduation_archived"]["tag"], "own-test")
            self.assertTrue(
                AuditLog.objects.filter(object_id=str(unit.pk), reason__startswith="groups: archived").exists()
            )
        again = self._run(apply=True, **FLAGS).counters
        self.assertEqual(again["written.student_movements"], 0)
        self.assertEqual(again["written.groups_archived"], 0)
        with bypass_rls():
            self.assertEqual(StudentMovement.objects.filter(organization=self.org).count(), 7)
