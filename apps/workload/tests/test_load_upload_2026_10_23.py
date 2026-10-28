"""Sahib 2026-10-23: Tədris şöbəsinin «Dərs yükü faylı» — kafedra + Excel/Forma 1 → tapşırıq, bölgü, açılış, qeydiyyat.

* Önizləmə heç nə yazmır (bütün axın savepoint-də işləyib geri qayıdır), saylar isə real tətbiqlə eynidir.
* Tətbiq: tapşırıq yoxdursa yaradılır; fayldakı sətir tapşırıqda yoxdursa YENİ sətir (fənn kataloqda yoxdursa
  yaradılır); müəllim yazı səhvi ilə də tapılır; tapılmayan müəllimə FİN-siz, PAROLSUZ müəllim hesabı bu kafedrada;
  açılış (jurnal sahibi) + qrupun tələbəsinin qeydiyyatı.
* Eyni faylın təkrarı heç nə əlavə etmir (yeni sətir / hesab / bölgü yoxdur).
* Qapı: ``workload.load_import`` — yalnız ``workload.manage`` olan rol fayl yükləyə bilmir.
"""

from __future__ import annotations

import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from openpyxl import Workbook, load_workbook

from apps.accounts.models import UserProfile
from apps.organizations.models import Membership, OrgUnit
from apps.registrar.models import CourseOffering, Curriculum, Enrollment, Program, StudentAcademicRecord, Subject
from apps.workload.load_actions import LOAD_SESSION_KEY
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from apps.workload.services.load_upload_parsing import TEMPLATE_HEADERS, build_template, parse_workbook
from core.constants import OrgUnitType, RoleScopeType

from .factories import TEACHER_PERMS, activate_member, make_org

User = get_user_model()
YEAR = "2026/2027"
OFFICE_PERMS = ["workload.view", "workload.manage", "workload.submit", "workload.load_import"]


def _xlsx(rows) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Dərs yükü"
    sheet.append(list(TEMPLATE_HEADERS))
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


ROWS = [
    # mövcud müəllim (dərəcə + ata adı ilə), kataloqda olan fənn, I semestr
    ["b.ü.f.d. Həsənova Səkinə Ramiz qızı", "235 EKO", "Veb texnologiyalar", 5, 20, "", 30, 15, "", "", "", ""],
    # eyni müəllim — müəllim xanası boş (yuxarıdakı davam edir), kataloqda OLMAYAN fənn, II semestr
    ["", "235EKO", "Ekoloji modelləşdirmə", 4, 20, "", "", "", "", 30, "", 15],
    # yazı səhvi: «Həsənva Səkinə Ramiz» → eyni müəllim
    ["Həsənva Səkinə Ramiz", "235 EKO", "Alqoritmlər", 5, 20, "", "", 30, "", "", "", ""],
    # sistemdə olmayan müəllim → FİN-siz yeni hesab
    ["dos. Quliyev Tural Vaqif oğlu", "235 EKO", "Torpaqşünaslıq", 5, 20, "", 45, "", "", "", "", ""],
    ["", "", "CƏMİ", "", "", "", 105, 45, "", 30, "", 15],
]


class LoadParsingTests(SimpleTestCase):
    def test_template_has_headers_and_is_readable(self):
        book = load_workbook(io.BytesIO(build_template("Təbiət elmləri kafedrası")))
        self.assertEqual([cell.value for cell in book["Dərs yükü"][1]], list(TEMPLATE_HEADERS))
        self.assertIn("Təlimat", book.sheetnames)
        entries, skipped = parse_workbook(io.BytesIO(build_template()))
        self.assertEqual((entries, skipped), ([], []))

    def test_rows_teacher_carry_over_totals_and_semesters(self):
        entries, skipped = parse_workbook(io.BytesIO(_xlsx(ROWS)))
        self.assertEqual(len(entries), 4)
        self.assertEqual(skipped, [])
        second = entries[1]
        self.assertEqual(second.teacher_text, "b.ü.f.d. Həsənova Səkinə Ramiz qızı")
        self.assertEqual((second.season, second.hours), ("spring", {"lecture": 30, "lab": 15}))
        self.assertEqual((entries[0].credits, entries[0].students), ("5", "20"))
        self.assertEqual(entries[0].hours, {"lecture": 30, "seminar": 15})

    def test_block_subject_is_skipped_with_reason(self):
        rows = [
            [
                "Həsənova Səkinə",
                "235 EKO",
                "ATMF I blok:\n1. Alqoritmlər\n2. Qraflar",
                5,
                20,
                "",
                30,
                "",
                "",
                "",
                "",
                "",
            ]
        ]
        entries, skipped = parse_workbook(io.BytesIO(_xlsx(rows)))
        self.assertEqual(skipped[0]["reason"], "no_choice_marker")

    def test_subject_starting_with_cemi_is_not_a_total(self):
        rows = [
            ["Mirzəzadə Aydın Böyükkişi", "935 BM", "Cəmiyyət", 5, 20, "", "", "", "", 30, 30, ""],
            ["", "935 BM", "Cəmiyyət fəlsəfəsi", 5, 20, "", 15, 15, "", "", "", ""],
        ]
        entries, skipped = parse_workbook(io.BytesIO(_xlsx(rows)))
        self.assertEqual(skipped, [])
        self.assertEqual([entry.subject_text for entry in entries], ["Cəmiyyət", "Cəmiyyət fəlsəfəsi"])
        self.assertEqual(entries[0].season, "spring")
        self.assertEqual(entries[0].hours, {"lecture": 30, "seminar": 30})

    def test_total_labels_keep_word_boundaries_and_punctuation(self):
        for label in ("CƏMİ:", "Yekun cəmi", "Cəmi (payız)", "Universitet üzrə cəmi"):
            with self.subTest(label=label):
                rows = [["Müəllim Adı", "", label, "", "", "", 30, 30, "", "", "", ""]]
                self.assertEqual(parse_workbook(io.BytesIO(_xlsx(rows))), ([], []))


class LoadUploadFlowTests(TestCase):
    def setUp(self):
        self.org = make_org("qku-load")
        faculty = OrgUnit.objects.create(organization=self.org, name="Ekologiya məktəbi", unit_type=OrgUnitType.FACULTY)
        self.chair = OrgUnit.objects.create(
            organization=self.org, name="Ekologiya kafedrası", unit_type=OrgUnitType.CHAIR, parent=faculty
        )
        specialty = OrgUnit.objects.create(
            organization=self.org, name="Ekologiya", slug="eko", unit_type=OrgUnitType.SPECIALTY, parent=faculty
        )
        self.group = OrgUnit.objects.create(
            organization=self.org, name="235 EKO", unit_type=OrgUnitType.GROUP, parent=specialty
        )
        for code, name in (("QKU-1", "Veb texnologiyalar"), ("QKU-2", "Alqoritmlər")):
            Subject.objects.create(organization=self.org, code=code, name=name, ects=5)
        self.office = User.objects.create_user("tedris.sobesi", "ts@x.test", "pw")
        activate_member(self.org, self.office, "teaching_office_head", permissions=OFFICE_PERMS, level=70)
        self.sekine = User.objects.create_user(
            "sekine.h", "sekine@x.test", "pw", first_name="Səkinə", last_name="Həsənova"
        )
        UserProfile.objects.filter(user=self.sekine).update(patronymic="Ramiz")
        activate_member(
            self.org, self.sekine, "teacher", permissions=TEACHER_PERMS, scope_unit=self.chair,
            scope_type=RoleScopeType.COURSE,
        )  # fmt: skip
        program = Program.objects.create(
            organization=self.org, code="P-EKO", name="Ekologiya", specialty_unit=specialty
        )
        curriculum = Curriculum.objects.create(organization=self.org, program=program, admission_year=2025)
        self.student = User.objects.create_user("tel.eko", "t@x.test", "pw")
        activate_member(self.org, self.student, "student", permissions=["course.view"], level=10)
        StudentAcademicRecord.objects.create(
            organization=self.org, student=self.student, program=program, curriculum=curriculum,
            group=self.group, admission_year=2025,
        )  # fmt: skip

    def _upload(self, content: bytes, *, user=None):
        self.client.force_login(user or self.office)
        upload = SimpleUploadedFile("ders_yuku.xlsx", content)
        return self.client.post(
            reverse("workload:action"),
            {"action": "load_upload", "chair": str(self.chair.pk), "academic_year": YEAR, "file": upload},
        )

    def _apply(self):
        return self.client.post(reverse("workload:action"), {"action": "load_apply"})

    def test_preview_writes_nothing_then_apply_builds_everything(self):
        response = self._upload(_xlsx(ROWS))
        self.assertEqual(response.status_code, 200, response.content)
        counters = response.json()["counters"]
        self.assertEqual(counters.get("row_created"), 4)
        self.assertEqual(counters.get("teacher_created"), 1)
        self.assertEqual(counters.get("students_enrolled"), 4)  # 1 tələbə × 4 fənn
        # önizləmə: heç nə qalmayıb
        self.assertFalse(TeachingTask.objects.filter(organization=self.org).exists())
        self.assertFalse(User.objects.filter(last_name="Quliyev").exists())
        self.assertFalse(Subject.objects.filter(organization=self.org, name="Ekoloji modelləşdirmə").exists())
        stored = self.client.session[LOAD_SESSION_KEY]
        statuses = {line["subject"]: line["teacher_status"] for line in stored["report"]["lines"]}
        self.assertEqual(statuses["Alqoritmlər"], "fuzzy")
        self.assertEqual(statuses["Veb texnologiyalar"], "matched")

        response = self._apply()
        self.assertEqual(response.status_code, 200, response.content)
        task = TeachingTask.objects.get(organization=self.org, chair=self.chair, academic_year=YEAR)
        self.assertEqual(TeachingTaskRow.objects.filter(task=task).count(), 4)
        self.assertTrue(Subject.objects.filter(organization=self.org, name="Ekoloji modelləşdirmə", ects=4).exists())

        tural = User.objects.get(last_name="Quliyev", first_name="Tural")
        self.assertFalse(tural.has_usable_password())
        self.assertIsNone(tural.profile.fin)
        self.assertEqual(tural.profile.patronymic, "Vaqif")
        self.assertTrue(tural.profile.password_change_required)
        self.assertTrue(
            Membership.objects.filter(user=tural, organization=self.org, scope_unit=self.chair, is_active=True).exists()
        )

        veb = CourseOffering.objects.get(subject__name="Veb texnologiyalar", group=self.group)
        self.assertEqual(veb.instructor_id, self.sekine.pk)
        self.assertTrue(Enrollment.objects.filter(offering=veb, student=self.student).exists())
        torpaq = CourseOffering.objects.get(subject__name="Torpaqşünaslıq", group=self.group)
        self.assertEqual(torpaq.instructor_id, tural.pk)
        self.assertTrue(TeacherAssignment.objects.filter(row__task=task, teacher=self.sekine).exists())

        # Eyni fayl təkrar: heç nə əlavə olunmur.
        users_before = User.objects.count()
        assignments_before = TeacherAssignment.objects.filter(row__task=task).count()
        response = self._upload(_xlsx(ROWS))
        counters = response.json()["counters"]
        self.assertEqual(counters.get("row_created", 0), 0)
        self.assertEqual(counters.get("teacher_created", 0), 0)
        self._apply()
        self.assertEqual(TeachingTaskRow.objects.filter(task=task).count(), 4)
        self.assertEqual(User.objects.count(), users_before)
        self.assertEqual(TeacherAssignment.objects.filter(row__task=task).count(), assignments_before)

    def test_manage_without_load_import_is_denied(self):
        clerk = User.objects.create_user("katib", "k@x.test", "pw")
        activate_member(self.org, clerk, "teaching_office_staff", permissions=["workload.view", "workload.manage"])
        response = self._upload(_xlsx(ROWS), user=clerk)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "workload.load_chair_denied")
        self.assertFalse(TeachingTask.objects.filter(organization=self.org).exists())

    def test_template_download_is_gated(self):
        self.client.force_login(self.office)
        response = self.client.get(reverse("workload:load_template"), {"chair": str(self.chair.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertIn("ders-yuku-ekologiya", response["Content-Disposition"])
        load_workbook(io.BytesIO(response.content))
        self.client.force_login(self.sekine)
        self.assertEqual(self.client.get(reverse("workload:load_template")).status_code, 403)

    def test_unknown_group_is_reported_not_created(self):
        rows = [["Həsənova Səkinə Ramiz", "999 YOX", "Veb texnologiyalar", 5, 20, "", 30, "", "", "", "", ""]]
        response = self._upload(_xlsx(rows))
        line = self.client.session[LOAD_SESSION_KEY]["report"]["lines"][0]
        self.assertTrue(line["row"].startswith("group_not_found"), line)
        self.assertEqual(response.json()["counters"].get("row_created", 0), 0)
        self.assertFalse(OrgUnit.objects.filter(organization=self.org, name="999 YOX").exists())

    def test_section_renders_preview(self):
        self._upload(_xlsx(ROWS))
        response = self.client.get(
            reverse("accounts:profile_section_fragment", kwargs={"section": "workload-center"}), {"wc_view": "load"}
        )
        html = response.json()["html"]
        self.assertIn("Önizləmə", html)
        self.assertIn("load_apply", html)
        self.assertIn("Quliyev", html)

    def test_reupload_does_not_refill_language_level_journal(self):
        """2026-10-27 (İngilis dili kafedrası): yenidən yükləmə səviyyə jurnalına qrupun HAMISINI yazmır."""
        level = "Xarici dildə işgüzar və akademik kommunikasiya-1(elementary)"
        other = User.objects.create_user("tel.eko2", "t2@x.test", "pw")
        activate_member(self.org, other, "student", permissions=["course.view"], level=10)
        record = StudentAcademicRecord.objects.get(student=self.student)
        StudentAcademicRecord.objects.create(
            organization=self.org, student=other, program=record.program, curriculum=record.curriculum,
            group=self.group, admission_year=2025,
        )  # fmt: skip
        first = [["Həsənova Səkinə Ramiz", "235 EKO", level, 5, 20, "", "", 60, "", "", "", ""]]
        self._upload(_xlsx(first))
        self._apply()
        offering = CourseOffering.objects.get(subject__name=level, group=self.group)
        # Səviyyə yerləşdirməsi: tələbə başqa səviyyədədir — bu jurnaldan çıxarılıb, qrup yoldaşı qalır.
        Enrollment.objects.filter(offering=offering, student=self.student).delete()
        second = first + [["Həsənova Səkinə Ramiz", "235 EKO", "Veb texnologiyalar", 5, 20, "", 30, "", "", "", "", ""]]
        response = self._upload(_xlsx(second))
        self.assertEqual(response.status_code, 200, response.content)
        self._apply()
        self.assertTrue(CourseOffering.objects.filter(subject__name="Veb texnologiyalar", group=self.group).exists())
        self.assertFalse(Enrollment.objects.filter(offering=offering, student=self.student).exists())
        self.assertTrue(Enrollment.objects.filter(offering=offering, student=other).exists())
