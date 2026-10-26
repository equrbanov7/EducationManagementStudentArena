"""``fix_master_groups`` — magistr qrupu: dərəcə, ixtisas, tələbə proqramı (sahib 2026-10-26, 18:40/20:00 qaydası).

Dry-run yazmır; ``--apply`` qrupa ``degree_level=master`` yazır, qrupu magistr ixtisasına keçirir, bakalavr
proqramındakı qeydi magistr proqramı + planına bağlayır (audit); köhnəlmiş sətir atlanır; stdout yalnız saylar.
"""

from __future__ import annotations

import json
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.organizations.models import OrgUnit
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from apps.registrar.tests.subgroup_base import SubgroupFixture
from core.constants import OrgUnitType
from core.rls import bypass_rls


class FixMasterGroupsTest(SubgroupFixture, TestCase):
    PREFIX = "fmg"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()
        with bypass_rls():
            cls.owner.is_superuser = True
            cls.owner.save(update_fields=["is_superuser"])
            cls.master_spec = OrgUnit.objects.create(
                organization=cls.org,
                name="Magistr ixtisası",
                slug="fmg-ms",
                unit_type=OrgUnitType.SPECIALTY,
                parent=cls.chair,
            )
            cls.master_program = Program.objects.create(
                organization=cls.org,
                code="FMG-M",
                name="Magistr",
                degree_level="master",
                specialty_unit=cls.master_spec,
            )
            cls.master_plan = Curriculum.objects.create(
                organization=cls.org, program=cls.master_program, admission_year=2025
            )
            cls.record = StudentAcademicRecord.objects.get(student=cls.student)

    def _run(self, *extra):
        plan = {
            "format": "master-groups/1",
            "groups": [
                {
                    "group": str(self.group2.pk),
                    "degree": "master",
                    "specialty": str(self.master_spec.pk),
                    "records": [
                        {
                            "record": str(self.record.pk),
                            "program": str(self.master_program.pk),
                            "curriculum": str(self.master_plan.pk),
                            "substituted": True,
                        }
                    ],
                }
            ],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(plan, handle)
        out = StringIO()
        call_command(
            "fix_master_groups",
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

    def test_dry_run_then_apply(self):
        text = self._run()
        self.assertIn("records_switched=1", text)
        with bypass_rls():
            self.record.refresh_from_db()
            self.assertNotEqual(self.record.program_id, self.master_program.pk)
        text = self._run("--apply")
        self.assertIn("group_moved=1", text)
        self.assertNotIn(self.student.username, text)
        with bypass_rls():
            self.record.refresh_from_db()
            self.group2.refresh_from_db()
        self.assertEqual(self.record.program_id, self.master_program.pk)
        self.assertEqual(self.record.curriculum_id, self.master_plan.pk)
        self.assertEqual(self.record.group_id, self.group2.pk)
        self.assertEqual(self.group2.settings.get("degree_level"), "master")
        self.assertEqual(self.group2.parent_id, self.master_spec.pk)
        self.assertTrue(self.group2.path.startswith(self.master_spec.path))
        self.assertIn("record_already_master=1", self._run("--apply"))
