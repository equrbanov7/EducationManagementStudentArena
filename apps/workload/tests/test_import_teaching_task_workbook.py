"""Sahibin qərarı 2026-09-19: TAPŞIRIQ kitabçası → tapşırıq sətirləri, fənn/qrup yaradılması,
müəllim təyinatı, bölgü təsdiqi (offering) və tələbə qeydiyyatı — bir komandada."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from openpyxl import Workbook

from apps.organizations.models import AcademicPeriod, Membership, OrgUnit
from apps.registrar.models import CourseOffering, Curriculum, Enrollment, Program, StudentAcademicRecord, Subject
from apps.workload.models import TeacherAssignment, TeachingTask
from apps.workload.services.task_workbook_parsing import (
    block_chosen_subject,
    is_block,
    split_tokens,
)
from core.constants import OrgUnitType, RoleScopeType

from .factories import TEACHER_PERMS, activate_member, make_org

User = get_user_model()

_HEADER = ["Semestrlər", "Qruplar", "Fənlərin  adı", "İxtisas", "Tələbələrin  sayı", "Birləşmələrin sayı", "Qrup"]
_HEADER += [
    "Mühazirə",
    None,
    "Təcrübi",
    None,
    "Lab",
    None,
    "Məsləhət",
    "İmtahan",
    "Burax",
    "Dis",
    "Təc",
    None,
    "CƏMİ",
    "Kredit",
]


def _workbook(path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Ekologiya"
    for _ in range(8):
        ws.append([None])
    ws.append(_HEADER)
    ws.append([None] * 7 + ["Plan üzrə", "Cəmi", "Plan üzrə", "Cəmi", "Plan üzrə", "Cəmi"])
    ws.append([str(i) for i in range(1, 22)])
    ws.append(
        ["PAYIZ", "235 EKO", "Ümumi ekologiya", "Ekologiya", "23", "1", "1", "30", "30", "15", "15", None, None]
        + [None] * 6
        + ["45", "5"]
    )
    ws.append(
        ["PAYIZ", "236 EKO", "Torpaqşünaslığın əsasları", "Ekologiya", "30", "1", "1", "15", "15", "15", "15"]
        + [None] * 8
        + ["30", "3"]
    )
    ws.append(
        [
            "YAZ",
            "235 EKO",
            "ATMF I blok:\n1. Bitki ekologiyası +\n2. Fauna",
            "Ekologiya",
            "23",
            "1",
            "1",
            "30",
            "30",
            "15",
            "15",
        ]
        + [None] * 8
        + ["45", "4"]
    )
    ws.append(
        ["YAZ", "235 EKO", "Buraxılış işi", "Ekologiya", "23", "1", "1"]
        + [None] * 8
        + ["40"]
        + [None] * 3
        + ["40", None]
    )
    ws2 = wb.create_sheet("Proqramlaşdırma")
    for _ in range(8):
        ws2.append([None])
    ws2.append([None] * 5 + ["Cəmi", "Cəmi", "Cəmi"])
    ws2.append(["1", "2", "3", "4", "5", "9", "11", "13", "14", "20"])
    ws2.append(["PAYIZ", "235 EKO", "Ümumi ekologiya", "Ekologiya", "23", "30", "15", None, "SƏKİNƏ", "45"])
    ws2.append(["PAYIZ", "235 EKO", "Veb texnologiyalar", "Ekologiya", "23", "30", "30", None, "MİNAYƏ", "60"])
    ws2.append(["PAYIZ", "236 EKO", "Ümumi ekologiya", "Ekologiya", "30", "15", "15", None, "MURAD", "30"])
    wb.save(path)


class ImportTeachingTaskWorkbookTests(TestCase):
    def setUp(self):
        self.org = make_org("qku-tap")
        self.faculty = OrgUnit.objects.create(organization=self.org, name="YTİM", unit_type=OrgUnitType.FACULTY)
        self.chair_eko = OrgUnit.objects.create(
            organization=self.org, name="Ekologiya", unit_type=OrgUnitType.CHAIR, parent=self.faculty
        )
        self.chair_prog = OrgUnit.objects.create(
            organization=self.org,
            name="Proqramlaşdırma və informasiya təhlükəsizliyi",
            unit_type=OrgUnitType.CHAIR,
            parent=self.faculty,
        )
        self.specialty = OrgUnit.objects.create(
            organization=self.org,
            name="Ekologiya",
            slug="eko-spec",
            unit_type=OrgUnitType.SPECIALTY,
            parent=self.faculty,
        )
        self.group = OrgUnit.objects.create(
            organization=self.org, name="235 EKO", unit_type=OrgUnitType.GROUP, parent=self.specialty
        )
        Subject.objects.create(organization=self.org, code="QKU-10", name="Ümumi ekologiya", ects=5)
        Subject.objects.create(organization=self.org, code="QKU-11", name="Bitki ekologiyası", ects=4)
        self.admin = User.objects.create_superuser("superadmin", "sa@x.test", "pw")
        activate_member(self.org, self.admin, "rector", permissions=["*"], level=100)
        self.sekine = User.objects.create_user(
            "sekine.hesenova", "s@x.test", "pw", first_name="Səkinə", last_name="Həsənova"
        )
        for username, first, last in (("murad.a", "Murad", "Ələkbərli"), ("murad.s", "Murad", "Səftərli")):
            user = User.objects.create_user(username, f"{username}@x.test", "pw", first_name=first, last_name=last)
            activate_member(
                self.org,
                user,
                "teacher",
                permissions=TEACHER_PERMS,
                scope_unit=self.chair_prog,
                scope_type=RoleScopeType.COURSE,
            )
        activate_member(
            self.org,
            self.sekine,
            "teacher",
            permissions=TEACHER_PERMS,
            scope_unit=self.chair_prog,
            scope_type=RoleScopeType.COURSE,
        )
        program = Program.objects.create(
            organization=self.org, code="P-EKO", name="Ekologiya", specialty_unit=self.specialty
        )
        curriculum = Curriculum.objects.create(organization=self.org, program=program, admission_year=2025)
        self.student = User.objects.create_user("tel.eko", "t@x.test", "pw")
        activate_member(self.org, self.student, "student", permissions=["course.view"], level=10)
        StudentAcademicRecord.objects.create(
            organization=self.org,
            student=self.student,
            program=program,
            curriculum=curriculum,
            group=self.group,
            admission_year=2025,
        )
        self.tmp = TemporaryDirectory()
        self.path = Path(self.tmp.name) / "tapsiriq.xlsx"
        _workbook(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *extra):
        out = StringIO()
        call_command(
            "import_teaching_task_workbook", "--file", str(self.path), "--org", self.org.slug,
            "--year", "2026/2027", "--actor", "superadmin", "--report", self.tmp.name, *extra, stdout=out,
        )  # fmt: skip
        return out.getvalue()

    def test_helpers(self):
        self.assertEqual(split_tokens("036\n3/336 F"), ["036", "3/336 F"])
        self.assertEqual(split_tokens("235 K     235 İT"), ["235 K", "235 İT"])
        self.assertEqual(split_tokens("336 F1,2"), ["336 F1", "336 F2"])
        self.assertEqual(split_tokens("233 K ing 233 İT ing"), ["233 K ing", "233 İT ing"])
        self.assertEqual(split_tokens("233 BİO az, ing"), ["233 BİO az"])
        self.assertTrue(is_block("ATMF VII blok:\n1. A +\n2. B"))
        self.assertEqual(block_chosen_subject("ATMF VII blok:\n1. Kibertəhlükəsizlik +\n2. B"), "Kibertəhlükəsizlik")
        self.assertEqual(
            block_chosen_subject("ATMF: Su bioehtiyyatlarının qorunması"), "Su bioehtiyyatlarının qorunması"
        )
        self.assertEqual(block_chosen_subject("ATMF II blok:\n1. A\n2. B"), "")

    def test_dry_run_writes_nothing(self):
        out = self._run()
        self.assertIn("DRY-RUN", out)
        self.assertFalse(TeachingTask.objects.exists())
        self.assertFalse(AcademicPeriod.objects.filter(organization=self.org).exists())
        self.assertFalse(OrgUnit.objects.filter(organization=self.org, name="236 EKO").exists())
        self.assertFalse(User.objects.filter(username="minaye").exists())
        self.assertIn("group_created=1", out)

    def test_apply_end_to_end_and_idempotent(self):
        out = self._run("--apply")
        fall = AcademicPeriod.objects.get(organization=self.org, name="Payız", academic_year="2026/2027")
        self.assertTrue(fall.is_current)
        self.assertTrue(
            AcademicPeriod.objects.filter(organization=self.org, name="Yaz", academic_year="2026/2027").exists()
        )
        eko_task = TeachingTask.objects.get(organization=self.org, chair=self.chair_eko)
        prog_task = TeachingTask.objects.get(organization=self.org, chair=self.chair_prog)
        self.assertEqual(eko_task.rows.count(), 4)
        self.assertEqual(eko_task.status, "draft")  # müəllimsiz vərəq — bölgü kafedrada
        # Fənn: kataloqda olmayan yaradıldı, blok «+» ilə həll olundu, buraxılış işi fənn YARATMADI.
        self.assertTrue(
            Subject.objects.filter(organization=self.org, name="Torpaqşünaslığın əsasları", code="QKU-12").exists()
        )
        self.assertFalse(Subject.objects.filter(organization=self.org, name__icontains="Buraxılış").exists())
        self.assertEqual(eko_task.rows.get(subject_text__startswith="ATMF").subject.name, "Bitki ekologiyası")
        self.assertEqual(eko_task.rows.get(subject_text="Buraxılış işi").row_kind, "thesis")
        new_group = OrgUnit.objects.get(organization=self.org, name="236 EKO")
        self.assertEqual(new_group.parent_id, self.specialty.pk)
        # Müəllimlər: Səkinə tapıldı, Minayə yarım məlumatla yaradıldı, Murad qeyri-müəyyən → vakant.
        self.assertEqual(prog_task.status, "distributed")
        minaye = User.objects.get(username="minaye")
        self.assertTrue(minaye.profile.password_change_required)
        self.assertTrue(
            Membership.objects.filter(
                user=minaye, scope_unit=self.chair_prog, role__name="teacher", is_active=True
            ).exists()
        )
        assignments = TeacherAssignment.objects.filter(row__task=prog_task)
        self.assertEqual(assignments.filter(teacher=self.sekine).count(), 2)  # mühazirə + seminar
        self.assertEqual(assignments.filter(teacher=minaye).count(), 2)
        self.assertEqual(assignments.filter(teacher__isnull=True).count(), 2)  # MURAD → vakant
        offering = CourseOffering.objects.get(
            organization=self.org, subject__name="Ümumi ekologiya", period=fall, group=self.group
        )
        self.assertEqual(offering.instructor_id, self.sekine.pk)
        self.assertTrue(Enrollment.objects.filter(offering=offering, student=self.student).exists())
        self.assertEqual(CourseOffering.objects.filter(organization=self.org, group=new_group).count(), 1)
        self.assertIn("ambiguous", out)
        # Təkrar icra: heç nə ikiqat yaranmır.
        before = (
            TeachingTask.objects.count(),
            TeacherAssignment.objects.count(),
            CourseOffering.objects.count(),
            Subject.objects.count(),
            OrgUnit.objects.count(),
            User.objects.count(),
        )
        self._run("--apply")
        after = (
            TeachingTask.objects.count(),
            TeacherAssignment.objects.count(),
            CourseOffering.objects.count(),
            Subject.objects.count(),
            OrgUnit.objects.count(),
            User.objects.count(),
        )
        self.assertEqual(before, after)
