"""``reinstate_part_time_graduates_20261115`` (sahib 2026-11-15): səhvən məzun edilmiş qiyabilər bərpa olunur.

Yalnız köçürmənin toplu əmri (``MZN-SINX-2026``) ilə məzun edilmiş, qiyabi (qeydin forması və ya qrup adında 4 rəqəm),
2021+ qəbulu bakalavrlar: bərpa əmri + giriş + qrupun cari jurnalı. Əyani, köhnə qəbul, əl ilə verilmiş məzun
etməyə toxunulmur; dry-run heç nə yazmır; ``--undo`` geri qaytarır.
"""

from __future__ import annotations

import datetime as dt
import io

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import movements
from apps.registrar.models import CourseOffering, Curriculum, Enrollment, Program, StudentAcademicRecord, Subject
from core.constants import AcademicPeriodType, OrganizationType
from core.rls import bypass_rls

User = get_user_model()
CMD = "reinstate_part_time_graduates_20261115"


class ReinstatePartTimeGraduatesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("ptg_admin", "ptg_admin@example.test", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="PTG Univ",
                slug="ptg-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.admin,
                status="active",
                is_active=True,
            )
            qiyabi = OrgUnit.objects.create(organization=cls.org, name="2032P", slug="ptg-2032p", unit_type="group")
            eyani = OrgUnit.objects.create(organization=cls.org, name="232 P", slug="ptg-232p", unit_type="group")
            period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                academic_year="2026/2027",
                period_type=AcademicPeriodType.SEMESTER,
                start_date=dt.date(2026, 9, 15),
                end_date=dt.date(2027, 1, 31),
                is_current=True,
            )
            program = Program.objects.create(organization=cls.org, code="PSX", name="Psixologiya", ects_total=240)
            subject = Subject.objects.create(organization=cls.org, code="PSX-1", name="Ümumi psixologiya-6")
            cls.offering = CourseOffering.objects.create(
                organization=cls.org, group=qiyabi, subject=subject, period=period, lesson_hours=30
            )
            role = cls.org.roles.get(name="student")
            plan = {
                "target": (qiyabi, 2022, "full_time", "MZN-SINX-2026"),  # qrup adı qiyabi → bərpa
                "form": (eyani, 2021, "part_time", "MZN-SINX-2026"),  # qeydin forması qiyabi, 2021 → bərpa
                "full_time": (eyani, 2022, "full_time", "MZN-SINX-2026"),  # əyani → toxunulmur
                "old": (qiyabi, 2019, "part_time", "MZN-SINX-2026"),  # 2021-dən əvvəl → toxunulmur
                "manual": (qiyabi, 2022, "part_time", "MZN-77"),  # əl ilə məzun → toxunulmur
            }
            cls.records = {}
            for key, (group, year, form, order) in plan.items():
                user = User.objects.create_user(f"ptg.{key}", f"ptg.{key}@example.test", "pw")
                Membership.objects.create(user=user, organization=cls.org, role=role, is_primary=True, is_active=True)
                UserProfile.objects.update_or_create(user=user, defaults={"organization": cls.org})
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
                    education_form=form,
                    status="enrolled",
                    is_active=True,
                )
                movements.create_movement(
                    record=record,
                    kind="graduation",
                    order_number=order,
                    order_date=dt.date(2026, 7, 1),
                    reason="test",
                    actor=cls.admin,
                )
                cls.records[key] = record

    def run_cmd(self, *args):
        out = io.StringIO()
        call_command(CMD, "--org", "ptg-univ", "--actor", "ptg_admin", *args, stdout=out)
        return out.getvalue()

    def status(self, key):
        with bypass_rls():
            return StudentAcademicRecord.objects.get(pk=self.records[key].pk).status

    def statuses(self):
        return {key: self.status(key) for key in self.records}

    def test_dry_run_writes_nothing(self):
        output = self.run_cmd()
        self.assertIn("mode=dry_run", output)
        self.assertIn("reinstated=2", output)
        self.assertIn("skip_year_2019=1", output)
        self.assertEqual(set(self.statuses().values()), {"graduated"})

    def test_apply_reinstates_part_time_only_and_undo_regraduates(self):
        output = self.run_cmd("--apply")
        self.assertIn("reinstated=2", output)
        self.assertIn("groups=2032P:1,232 P:1", output)
        expected = {"target": "enrolled", "form": "enrolled", "full_time": "graduated", "old": "graduated"}
        expected["manual"] = "graduated"
        self.assertEqual(self.statuses(), expected)
        with bypass_rls():
            target = self.records["target"]
            self.assertTrue(
                Enrollment.objects.filter(offering=self.offering, student=target.student, status="enrolled").exists()
            )
            profile = UserProfile.objects.filter(user=target.student).first()
            if profile is not None:
                self.assertEqual(profile.access_state, UserProfile.AccessState.ACTIVE)

        again = self.run_cmd("--apply")
        self.assertIn("reinstated=0", again)

        batch = output.strip().splitlines()[-1].split("batch=")[1]
        undo = self.run_cmd("--undo", batch, "--apply")
        self.assertIn("regraduated=2", undo)
        self.assertEqual(set(self.statuses().values()), {"graduated"})
