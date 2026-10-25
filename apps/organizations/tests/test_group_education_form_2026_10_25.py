"""Qrup kodundan təhsil forması — sahibin qaydası (2026-10-25).

«Qrup nömrəsində 4 rəqəm varsa («2232 K») — QİYABİ; 3 rəqəm varsa («234 KE») — ƏYANİ.»

Kilidlənən davranış:

* ``education_form_from_group_name`` yalnız birmənalı bakalavr kodunu tanıyır; magistr («409/6MBA»), kollec
  «<kurs><il>» («1025»), «3/336 F», «1225(A)», «0055 / 1 (az)» qaydadan kənardır (``None``).
* ``rule_form_for`` magistr (``degree_level``) və kollec (legacy bayrağı / əcdad adı) qruplarını istisna edir.
* ``fix_group_education_form``: defolt dry-run heç nə yazmır; ``--apply`` qrupu düzəldir/doldurur, qiyabi
  qrupun «əyani» qeydlərini qiyabi edir, əyani qrupdakı «qiyabi» qeydi YALNIZ ``--align-part-to-full`` ilə
  dəyişir; dərs yükü sətri yalnız ``--task-rows`` ilə; audit yazılır; təkrar qaçış 0 yazır; stdout yalnız saylar.
* Qrup reyestrində yadda saxlama: birmənalı kodda forma addan gəlir (seçimdən üstün), qeyri-standartda seçim qalır.
"""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.accounts.tests.test_groups_registry_add_students import _AddStudentsBase
from apps.audit.models import AuditLog
from apps.organizations.group_education_form import education_form_from_group_name, rule_form_for
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class GroupNameRuleTest(SimpleTestCase):
    def test_three_digits_full_time_four_digits_part_time(self):
        cases = {
            "234 KE": "full_time",
            "234KE": "full_time",
            "536 TB1": "full_time",
            "036 ing": "full_time",
            "028": "full_time",
            "229 BİO (Rafia)": "full_time",
            "234 K-1": "full_time",
            "235 İ-1 az": "full_time",
            "2233 K-2": "part_time",
            "2232 K": "part_time",
            "2232K": "part_time",
            "2233İT": "part_time",
            "2231M RUS": "part_time",
            "2533 Bi rus": "part_time",
        }
        for name, expected in cases.items():
            self.assertEqual(education_form_from_group_name(name), expected, name)

    def test_nonstandard_names_are_outside_the_rule(self):
        for name in (
            "409/6MBA",
            "510/6BİEO",
            "10/6 X",
            "3/336 F",
            "1025",
            "2026",
            "1225(A)",
            "2029A-(qrupBMU)",
            "630-İ",
            "0055 / 1 (az)",
            "0055 A",
            "22(UNEC)",
            "Level - Group 3",
            "12345 K",
            "",
            None,
        ):
            self.assertIsNone(education_form_from_group_name(name), name)

    def test_master_and_college_context_are_exempt(self):
        self.assertEqual(rule_form_for("505 GE", settings={"degree_level": "master"}), (None, "master"))
        self.assertEqual(rule_form_for("1226 A", names=["Kollec", "Kollec"]), (None, "college"))
        self.assertEqual(rule_form_for("1226 A", settings={"legacy": {"kollec_or_uni": "Kollec"}}), (None, "college"))
        self.assertEqual(rule_form_for("2232 K", settings={"degree_level": "bachelor"}), ("part_time", ""))


class FixGroupEducationFormCommandTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("gef_owner", "gef_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="GEF Univ",
                slug="gef-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            faculty = cls._unit("Rəqəmsal", OrgUnitType.FACULTY, None)
            cls.specialty = cls._unit("Kompüter Mühəndisliyi", OrgUnitType.SPECIALTY, faculty)
            college = cls._unit("Kollec", OrgUnitType.FACULTY, None)
            college_spec = cls._unit("Kollec", OrgUnitType.SPECIALTY, college)
            cls.extramural = cls._unit("2232 K", OrgUnitType.GROUP, cls.specialty, {"education_form": "full_time"})
            cls.fulltime = cls._unit("234 KE", OrgUnitType.GROUP, cls.specialty, {"education_form": "part_time"})
            cls.empty = cls._unit("236 K", OrgUnitType.GROUP, cls.specialty, {})
            cls.ok = cls._unit("2233 K", OrgUnitType.GROUP, cls.specialty, {"education_form": "part_time"})
            cls.master = cls._unit(
                "409/6MBA", OrgUnitType.GROUP, cls.specialty, {"education_form": "full_time", "degree_level": "master"}
            )
            cls.bare = cls._unit("1025", OrgUnitType.GROUP, cls.specialty, {"education_form": "full_time"})
            cls.college_group = cls._unit("1226 A", OrgUnitType.GROUP, college_spec, {"education_form": "full_time"})
            program = Program.objects.create(
                organization=cls.org, code="GEF-KM", official_code="050629", name="GEF KM", specialty_unit=cls.specialty
            )
            plan = Curriculum.objects.create(
                organization=cls.org, program=program, admission_year=2024, name="GEF plan", version=1
            )
            student_role = Role.objects.get(organization=cls.org, name="student")
            cls.records = {}
            for key, group, form in (
                ("ext_full", cls.extramural, "full_time"),
                ("ext_part", cls.extramural, "part_time"),
                ("ft_part", cls.fulltime, "part_time"),
                ("ft_full", cls.fulltime, "full_time"),
                ("bare_full", cls.bare, "full_time"),
                ("college_full", cls.college_group, "full_time"),
            ):
                user = User.objects.create_user(f"gef_{key}", f"gef_{key}@qku.edu.az", "pw")
                Membership.objects.create(
                    user=user, organization=cls.org, role=student_role, is_primary=True, is_active=True
                )
                cls.records[key] = StudentAcademicRecord.objects.create(
                    organization=cls.org,
                    student=user,
                    program=program,
                    curriculum=plan,
                    group=group,
                    admission_year=2024,
                    education_form=form,
                )
            from apps.workload.models import TeachingTask, TeachingTaskRow

            task = TeachingTask.objects.create(
                organization=cls.org, academic_year="2026/2027", chair=faculty, status="distributed"
            )
            cls.row_part = TeachingTaskRow.objects.create(organization=cls.org, task=task, education_form="eyani")
            cls.row_part.groups.set([cls.extramural, cls.ok])
            cls.row_mixed = TeachingTaskRow.objects.create(organization=cls.org, task=task, education_form="eyani")
            cls.row_mixed.groups.set([cls.extramural, cls.fulltime])
            cls.row_bare = TeachingTaskRow.objects.create(organization=cls.org, task=task, education_form="eyani")
            cls.row_bare.groups.set([cls.bare])

    _seq = 0

    @classmethod
    def _unit(cls, name, unit_type, parent, settings=None):
        cls._seq += 1
        return OrgUnit.objects.create(
            organization=cls.org,
            name=name,
            slug=f"gef-{cls._seq}",
            unit_type=unit_type,
            parent=parent,
            settings=dict(settings or {}),
            is_active=True,
        )

    def _run(self, *extra):
        out = StringIO()
        call_command("fix_group_education_form", "--org", self.org.slug, *extra, stdout=out)
        lines = out.getvalue().strip().splitlines()
        counts = dict(pair.split("=", 1) for pair in lines[1].split(" ")[1:])
        return lines, {key: int(value) if value.isdigit() else value for key, value in counts.items()}

    def _form(self, unit):
        with bypass_rls():
            return OrgUnit.objects.get(pk=unit.pk).settings.get("education_form", "")

    def _record_form(self, key):
        with bypass_rls():
            return StudentAcademicRecord.objects.get(pk=self.records[key].pk).education_form

    def _row_form(self, row):
        from apps.workload.models import TeachingTaskRow

        with bypass_rls():
            return TeachingTaskRow.objects.get(pk=row.pk).education_form

    def test_dry_run_counts_without_writing(self):
        lines, counts = self._run()
        self.assertEqual(lines[0], "group_education_form: mode=dry_run")
        self.assertTrue(all(line.startswith("group_education_form: ") for line in lines))
        self.assertEqual(counts["groups_full_to_part"], 1)
        self.assertEqual(counts["groups_part_to_full"], 1)
        self.assertEqual(counts["groups_filled"], 1)
        self.assertEqual(counts["groups_ok"], 1)
        self.assertEqual(counts["skipped_nonstandard_name"], 1)
        self.assertEqual(counts["skipped_bare_four_digits"], 1)
        self.assertEqual(counts["skipped_college"], 1)
        self.assertEqual(counts["records_to_part"], 1)
        self.assertEqual(counts["records_part_in_full_group"], 1)
        self.assertEqual(counts["task_rows_to_qiyabi"], 1)
        self.assertEqual(counts["task_rows_undetermined"], 2)
        self.assertEqual((counts["written_groups"], counts["written_records"], counts["task_rows_written"]), (0, 0, 0))
        self.assertEqual(self._form(self.extramural), "full_time")
        self.assertEqual(self._record_form("ext_full"), "full_time")
        self.assertEqual(self._row_form(self.row_part), "eyani")

    def test_apply_fixes_groups_and_records_and_is_idempotent(self):
        _lines, counts = self._run("--apply")
        self.assertEqual(counts["written_groups"], 3)
        self.assertEqual(counts["written_records"], 1)
        self.assertEqual(counts["task_rows_written"], 0)  # --task-rows olmadan sətirlər yazılmır
        self.assertEqual(self._form(self.extramural), "part_time")
        self.assertEqual(self._form(self.fulltime), "full_time")
        self.assertEqual(self._form(self.empty), "full_time")
        # Qaydadan kənar qruplar toxunulmur.
        self.assertEqual(self._form(self.master), "full_time")
        self.assertEqual(self._form(self.bare), "full_time")
        self.assertEqual(self._form(self.college_group), "full_time")
        self.assertEqual(self._record_form("ext_full"), "part_time")
        self.assertEqual(self._record_form("ft_part"), "part_time")  # yerləşdirmə sualı — dəyişmir
        self.assertEqual(self._record_form("bare_full"), "full_time")
        self.assertEqual(self._record_form("college_full"), "full_time")
        self.assertEqual(self._row_form(self.row_part), "eyani")
        with bypass_rls():
            audit = AuditLog.objects.filter(organization=self.org, reason__contains="education form from group code")
            self.assertEqual(audit.count(), 3)
        _lines, again = self._run("--apply")
        self.assertEqual((again["written_groups"], again["written_records"]), (0, 0))

    def test_opt_in_flags_align_part_records_and_task_rows(self):
        _lines, counts = self._run("--apply", "--align-part-to-full", "--task-rows")
        self.assertEqual(counts["written_records"], 2)
        self.assertEqual(counts["task_rows_written"], 1)
        self.assertEqual(self._record_form("ft_part"), "full_time")
        self.assertEqual(self._row_form(self.row_part), "qiyabi")
        self.assertEqual(self._row_form(self.row_mixed), "eyani")
        self.assertEqual(self._row_form(self.row_bare), "eyani")
        _lines, again = self._run("--apply", "--align-part-to-full", "--task-rows")
        self.assertEqual((again["written_records"], again["task_rows_written"]), (0, 0))


class _CountingRun:
    def __init__(self):
        self.counts = {}

    def count(self, key, amount=1):
        self.counts[key] = self.counts.get(key, 0) + amount


class LegacyDeltaFormRuleTest(TestCase):
    """Legacy delta: qayda legacy ``eyani_qiyabi`` / ``education_type``-dan üstündür və sayılır."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("gef_legacy_owner", "gef_legacy_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="GEF Legacy",
                slug="gef-legacy",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            faculty = OrgUnit.objects.create(
                organization=cls.org, name="İqtisadiyyat", slug="gefl-1", unit_type=OrgUnitType.FACULTY
            )
            cls.specialty = OrgUnit.objects.create(
                organization=cls.org, name="Maliyyə", slug="gefl-2", unit_type=OrgUnitType.SPECIALTY, parent=faculty
            )
            college = OrgUnit.objects.create(
                organization=cls.org, name="Kollec", slug="gefl-3", unit_type=OrgUnitType.FACULTY
            )
            cls.college_spec = OrgUnit.objects.create(
                organization=cls.org, name="Kollec", slug="gefl-4", unit_type=OrgUnitType.SPECIALTY, parent=college
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org,
                name="2534 ML",
                slug="gefl-5",
                unit_type=OrgUnitType.GROUP,
                parent=cls.specialty,
                settings={"education_form": "full_time", "degree_level": "bachelor"},
            )

    def test_new_group_takes_the_form_from_its_code(self):
        from apps.legacy_import.services.delta.structure import _apply_form_rule

        run = _CountingRun()
        settings = {"education_form": "full_time", "degree_level": "bachelor", "legacy": {"kollec_or_uni": ""}}
        with bypass_rls():
            _apply_form_rule(run, "2534 ML", self.specialty, settings)
        self.assertEqual(settings["education_form"], "part_time")
        self.assertEqual(run.counts, {"group.form_rule_override": 1})

        college = {"education_form": "full_time", "degree_level": "bachelor", "legacy": {}}
        with bypass_rls():
            _apply_form_rule(run, "1226 A", self.college_spec, college)
        self.assertEqual(college["education_form"], "full_time")
        self.assertEqual(run.counts, {"group.form_rule_override": 1})

    def test_new_student_takes_the_form_from_the_group_code(self):
        from apps.legacy_import.services.delta.people import StudentMapper

        mapper = StudentMapper.__new__(StudentMapper)
        mapper.run = _CountingRun()
        with bypass_rls():
            self.assertEqual(mapper._education_form({"education_type": "Əyani"}, self.group), "part_time")
            self.assertEqual(mapper._education_form({"education_type": "Qiyabi"}, self.group), "part_time")
        self.assertEqual(mapper.run.counts, {"student.form_rule_override": 1})


class ProdDataOpsWhitelistTest(SimpleTestCase):
    def test_command_is_whitelisted_with_counts_only_log(self):
        import pathlib
        import re

        text = (pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("          - fix_group_education_form\n", text)
        self.assertIn("            fix_group_education_form)\n", text)
        self.assertIn('args=(--org "$ORG" --task-rows)', text)
        block = text.split("            fix_group_education_form)\n")[1].split(";;")[0]
        self.assertNotIn("--align-part-to-full", block.split("args=")[1])
        pattern = re.compile(
            r"^(syllabus_week_link|group_education_form|chair_merge): [a-z_]+=[0-9a-z_]+( [a-z_]+=[0-9a-z_]+)*$"
        )
        self.assertIn(pattern.pattern, text.replace("'", ""))
        for line in (
            "group_education_form: mode=dry_run",
            "group_education_form: groups=3 groups_ok=1 skipped_nonstandard_name=2 task_rows_written=0",
        ):
            self.assertRegex(line, pattern)


class GroupSaveRuleTest(_AddStudentsBase):
    """Qrup reyestrində yadda saxlama — birmənalı kodda forma addan gəlir (yeni qrup da, ad dəyişməsi də)."""

    def _save(self, **fields):
        payload = {"action": "save_group", "specialty": str(self.specialty.id), **fields}
        return self._action("teaching_office_head", payload)

    def test_new_four_digit_group_is_part_time_even_if_full_time_was_chosen(self):
        response = self._save(name="2236 KE", education_form="full_time")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            OrgUnit.objects.get(organization=self.org, name="2236 KE").settings["education_form"], "part_time"
        )

    def test_renaming_to_a_three_digit_code_makes_it_full_time(self):
        response = self._save(id=str(self.group.id), name="236 KE", code=self.group.code, education_form="part_time")
        self.assertEqual(response.status_code, 200, response.content)
        self.group.refresh_from_db()
        self.assertEqual(self.group.settings["education_form"], "full_time")

    def test_nonstandard_name_keeps_the_chosen_form(self):
        response = self._save(name="409/6MBA", education_form="part_time")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            OrgUnit.objects.get(organization=self.org, name="409/6MBA").settings["education_form"], "part_time"
        )
