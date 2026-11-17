"""Tests for the journal xlsx export (U14)."""

import datetime
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import finals, gradebook, services
from apps.registrar.models import Curriculum, CurriculumSubject, LessonKind, Program, StudentAcademicRecord, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class JournalExportTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("je_owner", "je_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="JE Univ",
                slug="je-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org,
                name="Fakültə",
                slug="je-faculty",
                unit_type=OrgUnitType.FACULTY,
            )
            cls.chair_unit = OrgUnit.objects.create(
                organization=cls.org,
                name="Kafedra",
                slug="je-chair",
                unit_type=OrgUnitType.CHAIR,
                parent=cls.faculty,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org,
                name="G1",
                slug="je-g1",
                unit_type=OrgUnitType.GROUP,
                parent=cls.chair_unit,
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            cls.program = Program.objects.create(organization=cls.org, code="CS", name="Kompüter elmləri")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2024)
            cls.subject = Subject.objects.create(organization=cls.org, code="CS101", name="Proqramlaşdırma", ects=6)
            CurriculumSubject.objects.create(
                organization=cls.org, curriculum=cls.curriculum, subject=cls.subject, semester_number=1
            )
            cls.teacher = User.objects.create_user("je_teacher", "je_teacher@qku.edu.az", "pw")
            cls.chair = User.objects.create_user("je_chair", "je_chair@qku.edu.az", "pw")
            cls.student = User.objects.create_user(
                "je_student", "je_student@qku.edu.az", "pw", first_name="Əli", last_name="Vəliyev"
            )
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            Membership.objects.create(
                user=cls.chair,
                organization=cls.org,
                role=cls.org.roles.get(name="chair_head"),
                scope_unit=cls.chair_unit,
                is_primary=True,
                is_active=True,
            )
            Membership.objects.create(
                user=cls.student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            record = StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.student,
                program=cls.program,
                curriculum=cls.curriculum,
                group=cls.group,
                admission_year=2024,
            )
            services.enroll_mandatory_subjects(record=record, period=cls.period, semester_number=1)
            cls.offering = cls.student.enrollments.get().offering
            cls.offering.instructor = cls.teacher
            cls.offering.save(update_fields=["instructor"])
            cls.enrollment = cls.offering.enrollments.get()
            lesson = gradebook.create_lesson(
                allow_past=True, offering=cls.offering, date=datetime.date(2024, 10, 1), kind=LessonKind.SEMINAR
            )
            gradebook.save_marks(
                enforce_day=False,
                offering=cls.offering,
                entries=[
                    {"lesson_id": lesson.id, "enrollment_id": cls.enrollment.id, "status": "present", "score": 40}
                ],
                by_user=cls.teacher,
            )
            finals.set_exam_score(enrollment=cls.enrollment, score=45, by_user=cls.teacher)

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _url(self):
        return reverse("registrar:journal_xlsx", args=[self.offering.id])

    def test_teacher_downloads_xlsx_with_content(self):
        from openpyxl import load_workbook

        resp = self._client(self.teacher).get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])
        self.assertIn("jurnal-CS101.xlsx", resp["Content-Disposition"])
        workbook = load_workbook(BytesIO(resp.content))
        self.assertEqual(len(workbook.sheetnames), 2)
        texts = "\n".join(str(c.value) for ws in workbook.worksheets for row in ws.iter_rows() for c in row if c.value)
        self.assertIn("Vəliyev Əli", texts)
        self.assertIn("CS101", texts)

    def test_both_sheets_show_surname_name_patronymic(self):
        """Sahib 2026-10-10: ixracda da jurnaldakı kimi «Soyad Ad Ata adı» (adı-soyadı eyni olanlar ayrılsın)."""
        from openpyxl import load_workbook

        from apps.accounts.models import UserProfile

        UserProfile.objects.filter(user=self.student).update(patronymic="Həsən")
        resp = self._client(self.teacher).get(self._url())
        workbook = load_workbook(BytesIO(resp.content))
        for ws in workbook.worksheets:
            cells = [str(c.value) for row in ws.iter_rows() for c in row if c.value]
            self.assertIn("Vəliyev Əli Həsən", cells, ws.title)

    def test_export_only_shows_completed_resit_score(self):
        from openpyxl import load_workbook

        from apps.registrar.models import ResitRecord, ResitStatus

        for status, expected in ((ResitStatus.ELIGIBLE, None), (ResitStatus.COMPLETED, 49)):
            with self.subTest(status=status), bypass_rls():
                ResitRecord.objects.update_or_create(
                    organization=self.org,
                    enrollment=self.enrollment,
                    defaults={"reason": "exam", "status": status, "resit_score": 49},
                )
            response = self._client(self.teacher).get(self._url())
            self.assertEqual(response.status_code, 200)
            sheet = load_workbook(BytesIO(response.content)).worksheets[1]
            row = next(row for row in sheet.iter_rows() if row[0].value == "Vəliyev Əli")
            self.assertEqual(row[7].value, expected)

    def test_student_cannot_export(self):
        resp = self._client(self.student).get(self._url())
        self.assertEqual(resp.status_code, 404)

    def _timed_lesson(self):
        """Seminar dərsinə cədvəl saatı (10:10–11:40) — vaxt məlumatı testləri üçün."""
        from apps.registrar.models import Lesson

        lesson = Lesson.objects.get(offering=self.offering)
        Lesson.objects.filter(pk=lesson.pk).update(start_time=datetime.time(10, 10), end_time=datetime.time(11, 40))
        lesson.refresh_from_db()
        return lesson

    def test_chair_who_opens_journal_can_export_with_lesson_timing(self):
        """Sahib 2026-11-17: jurnalı açan əməkdaş (kafedra/dekanlıq/tədris) «Export»da 404 alırdı.

        İndi ixrac jurnal səhifəsi ilə EYNİ qapıdadır; əməkdaş faylında hər dərsin saat aralığı, saat sayı və
        başladılma vaxtı var («Dərslər» vərəqi + başlıq)."""
        from openpyxl import load_workbook

        from apps.registrar.journal_lesson_timing import started_at_text

        lesson = self._timed_lesson()
        client = self._client(self.chair)
        self.assertEqual(client.get(reverse("registrar:journal_detail", args=[self.offering.id])).status_code, 200)
        resp = client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        workbook = load_workbook(BytesIO(resp.content))
        self.assertEqual(workbook.sheetnames[-1], "Dərslər")
        head = [cell.value for cell in workbook.worksheets[0][4]]
        self.assertIn("10:10–11:40", head[1])
        self.assertIn("2 saat", head[1])
        lessons_sheet = workbook["Dərslər"]
        header = [cell.value for cell in lessons_sheet[1]]
        row = dict(zip(header, [cell.value for cell in lessons_sheet[2]]))
        self.assertEqual(row["Tarix"], "01.10.2024")
        self.assertEqual(row["Dərs saatı"], "10:10–11:40")
        self.assertEqual(row["Akademik saat"], 2)
        self.assertEqual(row["Dərs başladılıb"], started_at_text(lesson))
        self.assertTrue(row["Dərs başladılıb"])

    def test_teacher_export_has_no_lesson_timing(self):
        """Jurnalın öz müəllimi vaxt məlumatını görmür (sahib: «qarışıqdır») — faylda da yox."""
        from openpyxl import load_workbook

        self._timed_lesson()
        workbook = load_workbook(BytesIO(self._client(self.teacher).get(self._url()).content))
        self.assertNotIn("Dərslər", workbook.sheetnames)
        texts = "\n".join(str(c.value) for ws in workbook.worksheets for row in ws.iter_rows() for c in row if c.value)
        self.assertNotIn("10:10", texts)

    def test_grid_and_day_popover_show_timing_to_staff_only(self):
        """Sütun başlığında saat aralığı + saat sayı, gün özətində başladılma anı — əməkdaşa bəli, müəllimə yox."""
        from django.utils import timezone

        lesson = self._timed_lesson()
        started = timezone.localtime(lesson.created_at).strftime("%d.%m.%Y %H:%M")
        url = reverse("registrar:journal_detail", args=[self.offering.id])

        staff_html = self._client(self.chair).get(url).content.decode()
        self.assertIn("data-jd-lesson-timing", staff_html)
        self.assertIn("10:10–11:40", staff_html)
        self.assertIn(f'data-started="{started}"', staff_html)
        self.assertIn("data-jd-day-started", staff_html)
        self.assertIn("journal_lesson_timing.css", staff_html)

        teacher_html = self._client(self.teacher).get(url).content.decode()
        self.assertNotIn("data-jd-lesson-timing", teacher_html)
        self.assertNotIn("data-started=", teacher_html)
        self.assertNotIn("data-jd-day-started", teacher_html)
        self.assertNotIn("journal_lesson_timing.css", teacher_html)

    def test_lesson_teacher_counts_as_journal_teacher(self):
        """Bölünmüş fənnin dərsini keçən müəllim də «öz müəllim»dir; kafedra müdiri deyil."""
        from apps.registrar.journal_lesson_timing import is_journal_teacher, show_lesson_timing
        from apps.registrar.models import Lesson

        other = User.objects.create_user("je_other_teacher", "je_ot@qku.edu.az", "pw")
        with bypass_rls():
            Membership.objects.create(
                user=other, organization=self.org, role=self.org.roles.get(name="teacher"), is_active=True
            )
        self.assertTrue(is_journal_teacher(self.teacher, self.offering))
        self.assertFalse(is_journal_teacher(other, self.offering))
        Lesson.objects.filter(offering=self.offering).update(instructor=other)
        self.assertTrue(is_journal_teacher(other, self.offering))
        self.assertFalse(show_lesson_timing(other, self.offering))
        self.assertTrue(show_lesson_timing(self.chair, self.offering))

    def test_export_is_audited(self):
        from apps.audit.models import AuditLog

        self._client(self.teacher).get(self._url())
        with bypass_rls():
            self.assertTrue(
                AuditLog.objects.filter(
                    resource_type="registrar.journal_export", resource_id=str(self.offering.pk)
                ).exists()
            )


class JournalTenantIsolationTest(JournalExportTest):
    """P0 reqressiya: jurnal səthləri AKTİV TƏŞKİLATA bağlı olmalıdır.

    Əvvəl ``get_object_or_404(CourseOffering, pk=...)`` org filtri OLMADAN
    işləyirdi — tenant sərhədi tamamilə RLS-ə qalırdı (non-Postgres backend-də
    no-op, ``rolbypassrls`` daşıyan DB rolunda isə mühərrik səviyyəsində keçilir).
    """

    def _foreign_actor_client(self):
        """Başqa təşkilatın sahibi + öz org kontekstində sessiya."""
        with bypass_rls():
            other_owner = User.objects.create_user("je_other_owner", "je_other@qku.edu.az", "pw")
            other_org = Organization.objects.create(
                name="Other Univ",
                slug="je-other-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=other_owner,
                status="active",
                is_active=True,
            )
            Membership.objects.create(
                user=other_owner,
                organization=other_org,
                role=other_org.roles.order_by("-level").first(),
                is_primary=True,
                is_active=True,
            )

        client = Client()
        client.force_login(other_owner)
        session = client.session
        session["active_organization"] = other_org.slug
        session.save()
        return client

    def test_foreign_org_cannot_open_journal_detail(self):
        response = self._foreign_actor_client().get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertEqual(response.status_code, 404)

    def test_foreign_org_cannot_export_journal_xlsx(self):
        response = self._foreign_actor_client().get(self._url())
        self.assertEqual(response.status_code, 404)
