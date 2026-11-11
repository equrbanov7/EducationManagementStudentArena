"""Sahib 2026-11-12: ``move_groups_to_program_specialty`` — qrup tələbələrinin proqram ixtisasının altına.

* bütün tələbələr başqa məktəbin ixtisasındadır → qrup köçür, path nəsillərə ötürülür, dekanlıq marşrutu
  (``resolve_scope_unit`` faculty) yeni məktəbi qaytarır; dry-run heç nə yazmır;
* tələbələr iki ixtisasa bölünüb → atlanır (``split_specialties``);
* ``--undo --batch`` qrupu köhnə valideynə qaytarır; xəta → ``CommandError`` kodu.
"""

import io
import pathlib
import re
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from apps.applications.constants import ResolveBy
from apps.applications.services.routing import resolve_scope_unit
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, Organization, OrgUnit
from apps.registrar import group_specialty_move_2026_11_12 as move
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
GREP = re.compile(r"grep -E '(\^group_move: [^']+)'")


def _grep():
    return GREP.search(WORKFLOW.read_text(encoding="utf-8")).group(1)


class WiringTest(SimpleTestCase):
    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - move_groups_to_program_specialty\n", text)
        self.assertIn("            move_groups_to_program_specialty)\n", text)
        self.assertIn('[ "$COMMAND" = "move_groups_to_program_specialty" ]', text)
        pattern = _grep()
        self.assertRegex("group_move: mode=dry_run already_ok=3 candidates=1 moved=0 skipped=2 batch=", pattern)
        self.assertRegex("group_move: skipped group=136_t_ing reason=split_specialties", pattern)
        self.assertNotRegex("group_move: group=Ə ı", pattern)

    def test_fold(self):
        self.assertEqual(move.slug("Tarix (Tədris İngilis Dilində)"), "tarix_tedris_ingilis_dilinde")
        self.assertEqual(move.slug("Siyasi və ictimai elmlər məktəbi"), "siyasi_ve_ictimai_elmler_mektebi")


class GroupSpecialtyMoveTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.actor = User.objects.create_user("gm_admin", "gm_admin@x.test", "pw", is_superuser=True)
            cls.org = Organization.objects.create(
                name="GM Univ", slug="gm-univ", org_type=OrganizationType.UNIVERSITY, owner=cls.actor,
                status="active", is_active=True,
            )  # fmt: skip
            unit = cls._unit
            cls.master = unit("Magistratura və doktorantura", OrgUnitType.FACULTY)
            cls.politics = unit("Siyasi və ictimai elmlər məktəbi", OrgUnitType.FACULTY)
            cls.tourism = unit("Turizm işi", OrgUnitType.SPECIALTY, cls.master)
            cls.history = unit("Tarix (Tədris Ingilis Dilində)", OrgUnitType.SPECIALTY, cls.politics)
            cls.law = unit("Hüquqşünaslıq", OrgUnitType.SPECIALTY, cls.politics)
            cls.group = unit("136 T ing", OrgUnitType.GROUP, cls.tourism)
            cls.subgroup = unit("136 T ing-1", OrgUnitType.GROUP, cls.group)
            cls.split = unit("137 T ing", OrgUnitType.GROUP, cls.tourism)
            cls.p_history = cls._program("GM-1", cls.history)
            cls.p_law = cls._program("GM-2", cls.law)
            for index in range(4):
                cls._record(f"gm_a{index}", cls.p_history, cls.group)
            for index, program in enumerate((cls.p_history, cls.p_history, cls.p_law, cls.p_law)):
                cls._record(f"gm_b{index}", program, cls.split)

    @classmethod
    def _unit(cls, name, unit_type, parent=None):
        return OrgUnit.objects.create(organization=cls.org, name=name, unit_type=unit_type, parent=parent)

    @classmethod
    def _program(cls, code, specialty):
        program = Program.objects.create(organization=cls.org, code=code, name=specialty.name, specialty_unit=specialty)
        Curriculum.objects.create(organization=cls.org, program=program, admission_year=2023)
        return program

    @classmethod
    def _record(cls, username, program, group):
        student = User.objects.create_user(username, f"{username}@x.test", "pw")
        Membership.objects.create(
            user=student, organization=cls.org, role=cls.org.roles.get(name="student"), is_primary=True, is_active=True
        )
        StudentAcademicRecord.objects.create(
            organization=cls.org, student=student, program=program,
            curriculum=Curriculum.objects.filter(program=program).first(), group=group, admission_year=2023,
        )  # fmt: skip

    def _call(self, *extra):
        out = io.StringIO()
        call_command(
            "move_groups_to_program_specialty", "--org", self.org.slug, "--actor", self.actor.username, *extra,
            stdout=out,
        )  # fmt: skip
        lines = out.getvalue().splitlines()
        pattern = _grep()
        for line in lines:
            self.assertRegex(line, pattern)
        summary = dict(pair.split("=", 1) for pair in lines[-1][len(move.PREFIX) + 1 :].split())
        return lines, summary

    def _fresh(self, unit):
        with bypass_rls():
            return OrgUnit.objects.get(pk=unit.pk)

    def _school(self, group):
        return resolve_scope_unit(SimpleNamespace(resolve_by=ResolveBy.FACULTY.value), self._fresh(group))

    def test_dry_run_reports_and_writes_nothing(self):
        lines, summary = self._call()
        self.assertEqual(summary["mode"], "dry_run")
        self.assertEqual((summary["candidates"], summary["moved"], summary["batch"]), ("1", "0", ""))
        self.assertIn(
            "group_move: group=136_t_ing to=tarix_tedris_ingilis_dilinde students=4 from=turizm_isi "
            "from_school=magistratura_ve_doktorantura to_school=siyasi_ve_ictimai_elmler_mektebi",
            lines,
        )
        self.assertIn("group_move: skipped group=137_t_ing reason=split_specialties", lines)
        self.assertEqual(self._fresh(self.group).parent_id, self.tourism.pk)
        self.assertEqual(self._school(self.group).pk, self.master.pk)

    def test_apply_moves_cascades_path_routes_to_new_school_and_undo(self):
        _lines, summary = self._call("--apply")
        self.assertEqual((summary["mode"], summary["moved"]), ("apply", "1"))
        batch = summary["batch"]
        self.assertRegex(batch, move.BATCH_RE)
        group, subgroup = self._fresh(self.group), self._fresh(self.subgroup)
        self.assertEqual(group.parent_id, self.history.pk)
        self.assertEqual(group.path, f"{self._fresh(self.history).path}/{group.pk}")
        self.assertEqual(subgroup.path, f"{group.path}/{subgroup.pk}")
        self.assertEqual(self._school(self.group).pk, self.politics.pk)
        self.assertEqual(self._school(self.subgroup).pk, self.politics.pk)
        entry = group.settings["history"][-1]
        self.assertEqual((entry["parent_id"], entry["batch"]), (str(self.tourism.pk), batch))
        self.assertEqual(self._fresh(self.split).parent_id, self.tourism.pk)
        with bypass_rls():
            self.assertTrue(AuditLog.objects.filter(resource_type=move.RESOURCE, resource_id=batch).exists())

        _lines, again = self._call("--apply")
        self.assertEqual((again["moved"], again["already_ok"]), ("0", "1"))

        _lines, preview = self._call("--undo", "--batch", batch)
        self.assertEqual((preview["mode"], preview["candidates"]), ("undo_dry_run", "1"))
        self.assertEqual(self._fresh(self.group).parent_id, self.history.pk)
        _lines, undone = self._call("--undo", "--batch", batch, "--apply")
        self.assertEqual((undone["mode"], undone["moved"]), ("undo_apply", "1"))
        group, subgroup = self._fresh(self.group), self._fresh(self.subgroup)
        self.assertEqual(group.parent_id, self.tourism.pk)
        self.assertEqual(subgroup.path, f"{group.path}/{subgroup.pk}")
        self.assertEqual(self._school(self.group).pk, self.master.pk)
        _lines, twice = self._call("--undo", "--batch", batch, "--apply")
        self.assertEqual((twice["moved"], twice["skipped"]), ("0", "1"))

    def test_group_filter_and_errors(self):
        lines, summary = self._call("--group", "137 t ING")
        self.assertEqual((summary["candidates"], summary["skipped"]), ("0", "1"))
        self.assertIn("group_move: skipped group=137_t_ing reason=split_specialties", lines)
        with self.assertRaisesMessage(CommandError, "group_move_group_unknown"):
            self._call("--group", "999 YOX")
        with self.assertRaisesMessage(CommandError, "group_move_undo_needs_batch"):
            self._call("--undo")
        with self.assertRaisesMessage(CommandError, "group_move_batch_invalid"):
            self._call("--undo", "--batch", "x")
