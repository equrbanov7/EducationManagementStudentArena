"""Sahib 2026-10-12: paylanmış oktyabr TAPŞIRIQ kitabçası — seçmə blokunda QALIN seçim,
«C++» işarə deyil, «+»/tək bənd ehtiyatı, işarəsiz blok ötürülür (və ya ``--choice``),
dəyişmiş xana mövcud sətrə tutuşur (dublikat yox), ``--reassign`` müəllimi və açılışın
müəllimini dəyişir, bloklanan dəyişiklik hesabatda, ``--no-create-teachers`` hesab yaratmır."""

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase

from openpyxl import Workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont

from apps.organizations.models import OrgUnit
from apps.registrar.models import CourseOffering, Subject
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow, WorkloadAmendment
from apps.workload.services.task_workbook_choice import ChoiceError, choose_block_subject, parse_choice_overrides
from core.constants import OrgUnitType, RoleScopeType

from .factories import TEACHER_PERMS, activate_member, make_org

User = get_user_model()
BOLD, PLAIN = InlineFont(b=True), InlineFont(b=False)


def _rich(*parts):
    return CellRichText(*[TextBlock(BOLD if bold else PLAIN, text) for text, bold in parts])


class ChoiceTests(SimpleTestCase):
    def test_bold_wins_and_cpp_is_not_a_marker(self):
        cell = _rich(
            ("ATMF I blok:", True),
            ("\n", False),
            ("1. Proqramlaşdırma dilləri və informatika", True),
            ("\n2. Obyektyönümlü C++ proqramlaşdırma +", False),
        )
        self.assertEqual(choose_block_subject(cell), ("Proqramlaşdırma dilləri və informatika", "bold"))
        plain = "ATMF I blok:\n1. Alqoritmlər\n2. Texnika və C++ proqramlaşdırma dilləri"
        self.assertEqual(choose_block_subject(plain), ("", "none"))

    def test_bold_split_number_still_counts(self):
        cell = _rich(("ATMF VIII blok:\n1.Qraflar nəzəriyyəsi\n2", False), (". Mobil təhlükəsizlik +", True))
        self.assertEqual(choose_block_subject(cell), ("Mobil təhlükəsizlik", "bold"))

    def test_plus_single_header_and_none(self):
        self.assertEqual(choose_block_subject("ATMF II blok:\n1. A +\n2. B"), ("A", "plus"))
        self.assertEqual(choose_block_subject("ATMF II blok:\n1. Qraflar\n2."), ("Qraflar", "single"))
        self.assertEqual(choose_block_subject("ATMF: Su ehtiyatları"), ("Su ehtiyatları", "single"))
        self.assertEqual(choose_block_subject("ATMF X blok:\n1. A\n2. B"), ("", "none"))

    def test_override_only_validated_options(self):
        cell = "ATMF X blok:\n1.Tətbiqi statistika \n2. Paralel hesablamalar"
        self.assertEqual(choose_block_subject(cell, "1"), ("Tətbiqi statistika", "override"))
        self.assertEqual(choose_block_subject(cell, "Paralel hesablamalar"), ("Paralel hesablamalar", "override"))
        with self.assertRaises(ChoiceError):
            choose_block_subject(cell, "3")
        with self.assertRaises(ChoiceError):
            choose_block_subject(cell, "Başqa fənn")
        # İşarəli xanada override nəzərə alınmır (komanda bunu xəta sayır).
        self.assertEqual(choose_block_subject("ATMF:\n1. A +\n2. B", "2"), ("A", "plus"))
        self.assertEqual(
            parse_choice_overrides(["144=1,145=1", "20=Sistem analizi"]), {144: "1", 145: "1", 20: "Sistem analizi"}
        )
        with self.assertRaises(ChoiceError):
            parse_choice_overrides(["144"])


class OctoberWorkbookTests(TestCase):
    def setUp(self):
        self.org = make_org("qku-okt")
        faculty = OrgUnit.objects.create(organization=self.org, name="YTİM", unit_type=OrgUnitType.FACULTY)
        self.chair = OrgUnit.objects.create(
            organization=self.org,
            name="Proqramlaşdırma və informasiya təhlükəsizliyi",
            unit_type=OrgUnitType.CHAIR,
            parent=faculty,
        )
        specialty = OrgUnit.objects.create(
            organization=self.org, name="Ekologiya", slug="eko", unit_type=OrgUnitType.SPECIALTY, parent=faculty
        )
        self.group = OrgUnit.objects.create(
            organization=self.org, name="235 EKO", unit_type=OrgUnitType.GROUP, parent=specialty
        )
        for code, name in (("QKU-1", "Veb texnologiyalar"), ("QKU-2", "Alqoritmlər"), ("QKU-3", "Qraflar")):
            Subject.objects.create(organization=self.org, code=code, name=name, ects=5)
        self.admin = User.objects.create_superuser("superadmin", "sa@x.test", "pw")
        activate_member(self.org, self.admin, "rector", permissions=["*"], level=100)
        self.teachers = {}
        for username, first, last in (
            ("sekine.h", "Səkinə", "Həsənova"),
            ("minaye.a", "Minayə", "Əliyeva"),
            ("vefa.q", "Vəfa", "Quliyeva"),
        ):
            user = User.objects.create_user(username, f"{username}@x.test", "pw", first_name=first, last_name=last)
            activate_member(
                self.org, user, "teacher", permissions=TEACHER_PERMS, scope_unit=self.chair,
                scope_type=RoleScopeType.COURSE,
            )  # fmt: skip
            self.teachers[username] = user
        self.tmp = TemporaryDirectory()
        self.path = Path(self.tmp.name) / "okt.xlsx"

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, rows):
        wb = Workbook()
        ws = wb.active
        ws.title = "Proqramlaşdırma"
        for _ in range(10):
            ws.append([None])
        for index, (season, subject, teacher) in enumerate(rows, 11):
            ws.append([season, "235 EKO", None, "Ekologiya", "20", "30", "30", None, teacher, "60"])
            ws.cell(index, 3).value = subject
        wb.save(self.path)

    def _run(self, *extra):
        out = StringIO()
        call_command(
            "import_teaching_task_workbook", "--file", str(self.path), "--org", self.org.slug, "--year",
            "2026/2027", "--actor", "superadmin", "--report", self.tmp.name, "--sheet", "Proqramlaşdırma",
            *extra, stdout=out,
        )  # fmt: skip
        return out.getvalue()

    def _report(self):
        with (Path(self.tmp.name) / "tapsiriq_import.csv").open(encoding="utf-8") as handle:
            return {row["line"]: row for row in csv.DictReader(handle) if row["line"]}

    def _bold_block(self, chosen_first=True):
        return _rich(
            ("ATMF I blok:", True),
            ("\n1. Alqoritmlər", chosen_first),
            ("\n2. Qraflar", not chosen_first),
        )

    def test_bold_choice_and_unmarked_block_skipped_then_override(self):
        unmarked = "ATMF X blok:\n1. Alqoritmlər\n2. Qraflar"
        self._write([("PAYIZ", self._bold_block(False), "SƏKİNƏ"), ("YAZ", unmarked, "VƏFA")])
        out = self._run("--apply", "--no-create-teachers")
        task = TeachingTask.objects.get(organization=self.org, chair=self.chair)
        self.assertEqual(task.rows.count(), 1)
        self.assertEqual(task.rows.get().subject.name, "Qraflar")
        report = self._report()
        self.assertEqual(report["11"]["chosen_by"], "bold")
        self.assertEqual(report["12"]["row"], "no_choice_marker:new")
        self.assertIn("row_no_choice_marker=1", out)
        self.assertNotIn("Səkinə", out)  # loga şəxs adı düşmür
        # Operatorun seçimi yalnız işarəsiz xanaya və yalnız mövcud bəndə.
        with self.assertRaises(CommandError):
            self._run("--choice", "12=3")
        with self.assertRaises(CommandError):
            self._run("--choice", "11=1")
        self._run("--apply", "--no-create-teachers", "--choice", "12=1")
        self.assertEqual(task.rows.count(), 2)
        spring = task.rows.get(season="spring")
        self.assertEqual(spring.subject.name, "Alqoritmlər")
        self.assertEqual(self._report()["12"]["chosen_by"], "override")
        self.assertTrue(TeacherAssignment.objects.filter(row=spring, teacher=self.teachers["vefa.q"]).exists())

    def test_chair_name_with_kafedrasi_suffix_is_found(self):
        """Prod 2026-10-12: kafedra adı «… kafedrası» sonluğu ilə — vərəq ötürülməməlidir."""
        OrgUnit.objects.filter(pk=self.chair.pk).update(name="Proqramlaşdırma və informasiya təhlükəsizliyi kafedrası")
        self._write([("PAYIZ", "Veb texnologiyalar", "SƏKİNƏ")])
        out = self._run("--apply", "--no-create-teachers")
        self.assertNotIn("sheet_skipped", out)
        self.assertEqual(TeachingTask.objects.get(organization=self.org, chair=self.chair).rows.count(), 1)

    def test_changed_cell_matches_existing_row_and_reassign(self):
        self._write(
            [
                ("PAYIZ", "Veb  texnologiyalar", "SƏKİNƏ"),
                ("PAYIZ", "ATMF I blok:\n1. Alqoritmlər +\n2. Qraflar", "SƏKİNƏ"),
            ]
        )
        self._run("--apply", "--no-create-teachers")
        task = TeachingTask.objects.get(organization=self.org, chair=self.chair)
        self.assertEqual(task.status, "distributed")
        self.assertEqual(task.rows.count(), 2)
        offering = CourseOffering.objects.get(organization=self.org, subject__name="Alqoritmlər", group=self.group)
        self.assertEqual(offering.instructor, self.teachers["sekine.h"])
        # Oktyabr: xana mətni dəyişib («+» yox, qalın), müəllim dəyişib.
        self._write([("PAYIZ", "Veb texnologiyalar", "SƏKİNƏ"), ("PAYIZ", self._bold_block(True), "MİNAYƏ")])
        out = self._run("--apply", "--no-create-teachers")  # --reassign olmadan: yalnız hesabat
        self.assertEqual(task.rows.count(), 2)
        self.assertIn("teacher_differs=1", out)
        self.assertTrue(self._report()["12"]["row"].startswith("matched:"))
        offering.refresh_from_db()
        self.assertEqual(offering.instructor, self.teachers["sekine.h"])
        out = self._run("--apply", "--no-create-teachers", "--reassign")
        self.assertIn("reassigned=1", out)
        self.assertEqual(task.rows.count(), 2)
        row = task.rows.get(subject__name="Alqoritmlər")
        self.assertEqual(
            set(TeacherAssignment.objects.filter(row=row).values_list("teacher__username", flat=True)), {"minaye.a"}
        )
        offering.refresh_from_db()
        self.assertEqual(offering.instructor, self.teachers["minaye.a"])
        task.refresh_from_db()
        self.assertEqual(task.status, "distributed")
        self.assertTrue(WorkloadAmendment.objects.filter(task=task, target_id=row.pk).exists())

    def test_two_empty_block_subjects_are_filled_in_a_distributed_task(self):
        """Prod 2026-10-12: birinci sətrin düzəlişi tapşırığı «amended» edir — İKİNCİ sətrin fənni də yazılmalıdır."""
        self._write([("PAYIZ", "Veb texnologiyalar", "SƏKİNƏ"), ("YAZ", "Qraflar", "SƏKİNƏ")])
        self._run("--apply", "--no-create-teachers")
        task = TeachingTask.objects.get(organization=self.org, chair=self.chair)
        self.assertEqual(task.status, "distributed")
        # Sentyabr vəziyyəti: hər iki sətir işarəsiz blok idi → fənn boş.
        block = "ATMF I blok:\n1. Alqoritmlər\n2. Qraflar"
        task.rows.update(subject=None, subject_text=block)
        self._write([("PAYIZ", self._bold_block(True), "SƏKİNƏ"), ("YAZ", self._bold_block(False), "SƏKİNƏ")])
        out = self._run("--apply", "--no-create-teachers")
        self.assertIn("subject_filled=2", out)
        self.assertNotIn("subject_fill_blocked", out)
        self.assertEqual(sorted(task.rows.values_list("subject__name", flat=True)), ["Alqoritmlər", "Qraflar"])

    def test_reassign_blocked_when_journal_was_handed_to_someone_else(self):
        self._write([("PAYIZ", "Veb texnologiyalar", "SƏKİNƏ")])
        self._run("--apply", "--no-create-teachers")
        offering = CourseOffering.objects.get(organization=self.org, subject__name="Veb texnologiyalar")
        CourseOffering.objects.filter(pk=offering.pk).update(instructor=self.teachers["vefa.q"])
        self._write([("PAYIZ", "Veb texnologiyalar", "MİNAYƏ")])
        out = self._run("--apply", "--no-create-teachers", "--reassign")
        self.assertIn("blocked=1", out)
        self.assertEqual(self._report()["11"]["assignment"], "blocked:offering_owner_differs")
        row = TeachingTaskRow.objects.get(task__chair=self.chair)
        self.assertFalse(TeacherAssignment.objects.filter(row=row, teacher=self.teachers["minaye.a"]).exists())
        offering.refresh_from_db()
        self.assertEqual(offering.instructor, self.teachers["vefa.q"])

    def test_no_create_teachers_creates_no_users(self):
        self._write([("PAYIZ", "Veb texnologiyalar", "QORXMAZ"), ("PAYIZ", "Alqoritmlər", "SƏKİNƏ-NAMƏLUM")])
        users_before = User.objects.count()
        out = self._run("--apply", "--no-create-teachers")
        self.assertEqual(User.objects.count(), users_before)
        self.assertIn("teacher_not_found=2", out)
        report = self._report()
        self.assertIn("QORXMAZ:not_found:", report["11"]["teachers"])
        row = TeachingTaskRow.objects.get(task__chair=self.chair, subject__name="Alqoritmlər")
        lecture = TeacherAssignment.objects.get(row=row, activity="lecture")
        self.assertEqual(lecture.teacher, self.teachers["sekine.h"])  # A-B: mühazirə A-ya, seminar vakant
        self.assertIsNone(TeacherAssignment.objects.get(row=row, activity="seminar").teacher)
        # Operatorun açıq həlli (--teacher AD=istifadəçi) vakant seminarı doldurur — yalnız --reassign ilə.
        self._run("--apply", "--no-create-teachers", "--reassign", "--teacher", "NAMƏLUM=minaye.a")
        self.assertEqual(TeacherAssignment.objects.get(row=row, activity="seminar").teacher, self.teachers["minaye.a"])
        self.assertEqual(User.objects.count(), users_before)


class RenamedChairSheetTest(SimpleTestCase):
    """2026-10-15: «Ekologiya» vərəqi struktur planından sonrakı «Yer kadastrı və meşəçilik kafedrası»na düşür."""

    def test_old_sheet_name_maps_to_renamed_chair(self):
        from apps.workload.services.task_workbook_import import Importer, normalize

        chair = object()
        importer = Importer.__new__(Importer)
        importer.chairs = {normalize("Yer kadastrı və meşəçilik kafedrası"): chair}
        self.assertIs(importer.chair_for_sheet("Ekologiya"), chair)
        self.assertIsNone(importer.chair_for_sheet("Mexanika və riyaziyyat"))
