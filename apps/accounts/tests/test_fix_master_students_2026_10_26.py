"""``fix_master_students`` — bakalavrdan magistraturaya keçən tələbə (sahib 2026-10-26).

Bakalavr qeydi «məzun» + qeyri-aktiv (hərəkətsiz — magistr qeydiyyatları dondurulmur), magistr qrupunda yeni qeyd;
arxivlənmiş hesabın girişi açılır; təkrar qaçış heç nə yazmır; stdout yalnız saylar.
"""

from __future__ import annotations

import json
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.registrar.models import Curriculum, Enrollment, Program, StudentAcademicRecord
from apps.registrar.tests.subgroup_base import SubgroupFixture
from core.rls import bypass_rls


class FixMasterStudentsTest(SubgroupFixture, TestCase):
    PREFIX = "fms"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()
        with bypass_rls():
            cls.owner.is_superuser = True
            cls.owner.save(update_fields=["is_superuser"])
            cls.master_program = Program.objects.create(
                organization=cls.org, code="FMS-M", name="Magistr", degree_level="master"
            )
            cls.master_plan = Curriculum.objects.create(
                organization=cls.org, program=cls.master_program, admission_year=2026
            )
            cls.bachelor = StudentAcademicRecord.objects.get(student=cls.student)
            UserProfile.objects.filter(user=cls.student).update(
                access_state=UserProfile.AccessState.ARCHIVED, organization=cls.org
            )

    def _run(self, *extra):
        plan = {
            "format": "master-students/1",
            "records": [
                {
                    "user": self.student.pk,
                    "bachelor_record": str(self.bachelor.pk),
                    "group": str(self.group1.pk),
                    "program": str(self.master_program.pk),
                    "curriculum": str(self.master_plan.pk),
                    "admission_year": 2026,
                    "substituted": False,
                }
            ],
            "transfers": [],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(plan, handle)
        out = StringIO()
        call_command(
            "fix_master_students",
            "--org",
            self.org.slug,
            "--actor",
            self.owner.username,
            "--file",
            handle.name,
            *extra,
            stdout=out,
        )
        return out.getvalue()

    def test_dry_run_apply_idempotent(self):
        with bypass_rls():
            enrolled_before = Enrollment.objects.filter(student=self.student, status="enrolled").count()
        self.assertIn("records_created=1", self._run())
        with bypass_rls():
            self.assertFalse(
                StudentAcademicRecord.objects.filter(student=self.student, program=self.master_program).exists()
            )
        text = self._run("--apply")
        self.assertIn("records_created=1", text)
        self.assertNotIn(self.student.username, text)
        with bypass_rls():
            self.bachelor.refresh_from_db()
            master = StudentAcademicRecord.objects.get(student=self.student, program=self.master_program)
            profile = UserProfile.objects.get(user=self.student)
            enrolled_after = Enrollment.objects.filter(student=self.student, status="enrolled").count()
        self.assertEqual((self.bachelor.status, self.bachelor.is_active), ("graduated", False))
        self.assertEqual((master.group_id, master.status, master.is_active), (self.group1.pk, "enrolled", True))
        self.assertEqual(enrolled_after, enrolled_before)  # magistr dərsləri dondurulmur
        self.assertEqual(profile.access_state, UserProfile.AccessState.ACTIVE, text)
        self.assertIn("bachelor_record_stale=1", self._run("--apply"))
