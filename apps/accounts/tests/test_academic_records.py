"""Staff hierarchical academic-records — aggregation + scoping + endpoint tests.

İki fakültəli (A/B) bir təşkilat qurur: hər fakültədə bir kafedra + qrup +
tələbələr. Yoxlanılır:
* aqreqasiya (kredit/kəsr/qb/exam25) per-student ``build_student_overall_record``
  ilə uzlaşır;
* iyerarxiya scoping — dekan (scope_unit = fakültə A) yalnız A-nı görür, B-ni yox;
* endpoint mühafizəsi — struktur icazəsi olmayan (adi müəllim) has_access=False;
* lookup scoping — dekanın fakültə axtarışı yalnız A-nı qaytarır;
* drill-down (student detail) yalnız scope daxilində.
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts import academic_records as records_overview
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.organizations.scoping import ORG_WIDE_SCOPE, get_unit_scope
from apps.registrar import finals, gradebook, services, transcript
from apps.registrar.models import Curriculum, CurriculumSubject, LessonKind, Program, StudentAcademicRecord, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class _RecordsBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("rec_owner", "rec_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="REC Univ",
                slug="rec-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
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
            cls.teacher = User.objects.create_user("rec_teacher", "rec_teacher@qku.edu.az", "pw")
            # İki fakültə → hər birində kafedra → ixtisas OrgUnit → qrup.
            cls.fac_a = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə A", slug="rec-fa", unit_type=OrgUnitType.FACULTY
            )
            cls.fac_b = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə B", slug="rec-fb", unit_type=OrgUnitType.FACULTY
            )
            cls.chair_a = OrgUnit.objects.create(
                organization=cls.org, name="Kafedra A", slug="rec-ka", unit_type=OrgUnitType.CHAIR, parent=cls.fac_a
            )
            cls.chair_b = OrgUnit.objects.create(
                organization=cls.org, name="Kafedra B", slug="rec-kb", unit_type=OrgUnitType.CHAIR, parent=cls.fac_b
            )
            cls.group_a = OrgUnit.objects.create(
                organization=cls.org, name="QRUP-A", slug="rec-ga", unit_type=OrgUnitType.GROUP, parent=cls.chair_a
            )
            cls.group_b = OrgUnit.objects.create(
                organization=cls.org, name="QRUP-B", slug="rec-gb", unit_type=OrgUnitType.GROUP, parent=cls.chair_b
            )
            cls.subject = Subject.objects.create(organization=cls.org, code="REC101", name="Fənn", ects=6)

            cls.students_a = cls._make_group(cls.fac_a, cls.chair_a, cls.group_a, "a", n=3)
            cls.students_b = cls._make_group(cls.fac_b, cls.chair_b, cls.group_b, "b", n=2)

            # Dekan — fakültə A-ya scope-lu.
            cls.dean = User.objects.create_user("rec_dean", "rec_dean@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.dean,
                organization=cls.org,
                role=cls.org.roles.get(name="dean"),
                scope_unit=cls.fac_a,
                is_primary=True,
                is_active=True,
            )
            # Adi müəllim — struktur scope-u yoxdur.
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            # İmtahan mərkəzi — MƏRKƏZİ rol, unit scope-u yoxdur (org-wide görməlidir).
            cls.exam_center = User.objects.create_user("rec_exam", "rec_exam@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.exam_center,
                organization=cls.org,
                role=cls.org.roles.get(name="exam_center"),
                is_primary=True,
                is_active=True,
            )

    @classmethod
    def _make_group(cls, faculty, chair, group, tag, *, n):
        program = Program.objects.create(
            organization=cls.org, code=f"P{tag.upper()}", name=f"İxtisas {tag}", specialty_unit=chair
        )
        curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2024)
        CurriculumSubject.objects.create(
            organization=cls.org, curriculum=curriculum, subject=cls.subject, semester_number=1
        )
        students = []
        for i in range(n):
            student = User.objects.create_user(f"rec_s_{tag}{i}", f"rec_s_{tag}{i}@qku.edu.az", "pw")
            record = StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=student,
                program=program,
                curriculum=curriculum,
                group=group,
                admission_year=2024,
            )
            services.enroll_mandatory_subjects(record=record, period=cls.period, semester_number=1)
            students.append(student)
        # Bal ver: hər qrupun ilk tələbəsi kəsilir (imtahandan), qalanları keçir.
        offering = students[0].enrollments.get().offering
        offering.instructor = cls.teacher
        offering.save(update_fields=["instructor"])
        for day in range(1, 5):
            lesson = gradebook.create_lesson(
                allow_past=True, offering=offering, date=datetime.date(2024, 10, day), kind=LessonKind.SEMINAR
            )
            entries = [
                {"lesson_id": lesson.id, "enrollment_id": e.enrollments.get().id, "status": "present", "score": 10}
                for e in students
            ]
            gradebook.save_marks(enforce_day=False, offering=offering, entries=entries, by_user=cls.teacher)
        for idx, student in enumerate(students):
            enrollment = student.enrollments.get()
            # student0 → imtahandan kəsilir (aşağı bal); qalanları keçir.
            finals.set_exam_score(enrollment=enrollment, score=(5 if idx == 0 else 45), by_user=cls.teacher)
        return students


class RecordsAggregationTest(_RecordsBase):
    def test_org_wide_summary_matches_per_student(self):
        with bypass_rls():
            data = records_overview.build_records_overview(
                organization=self.org, scope=ORG_WIDE_SCOPE, filters={}, offset=0, limit=100
            )
            # Manual per-student aggregation via the canonical overall-record.
            expected_credits = expected_fails = 0
            for student in self.students_a + self.students_b:
                rec = transcript.build_student_overall_record(student=student, organization=self.org)
                for sem in rec["semesters"]:
                    expected_credits += sem["credits_earned"]
                    expected_fails += sum(1 for r in sem["rows"] if r["result"]["failed"])
        self.assertTrue(data["has_access"])
        self.assertEqual(data["summary"]["students"], 5)
        self.assertEqual(data["total"], 5)
        self.assertEqual(data["summary"]["credits_earned"], expected_credits)
        self.assertEqual(data["summary"]["fails"], expected_fails)
        # Hər qrupda 1 imtahandan-kəsilən (exam25) var → cəmi 2; qb yoxdur.
        self.assertEqual(data["summary"]["exam25"], 2)
        self.assertEqual(data["summary"]["qb"], 0)
        self.assertEqual(data["summary"]["fails"], 2)

    def test_rows_sorted_by_fails_desc(self):
        with bypass_rls():
            data = records_overview.build_records_overview(
                organization=self.org, scope=ORG_WIDE_SCOPE, filters={}, offset=0, limit=100
            )
        self.assertEqual(data["results"][0]["fails"], 1)  # kəsri olan öndə

    def test_faculty_filter_narrows(self):
        with bypass_rls():
            data = records_overview.build_records_overview(
                organization=self.org,
                scope=ORG_WIDE_SCOPE,
                filters={"faculty": str(self.fac_a.id)},
                offset=0,
                limit=100,
            )
        self.assertEqual(data["total"], 3)  # yalnız fakültə A

    def test_year_and_season_filter(self):
        with bypass_rls():
            data = records_overview.build_records_overview(
                organization=self.org, scope=ORG_WIDE_SCOPE, filters={}, offset=0, limit=100
            )
            self.assertEqual(data["year_options"], ["2024/2025"])  # fixture-də tək dövr
            same = records_overview.build_records_overview(
                organization=self.org,
                scope=ORG_WIDE_SCOPE,
                filters={"year": "2024/2025", "season": "Payız"},
                offset=0,
                limit=100,
            )
            none_year = records_overview.build_records_overview(
                organization=self.org, scope=ORG_WIDE_SCOPE, filters={"year": "2099/2100"}, offset=0, limit=100
            )
        self.assertEqual(same["summary"]["credits_earned"], data["summary"]["credits_earned"])
        self.assertEqual(same["summary"]["fails"], data["summary"]["fails"])
        self.assertEqual(none_year["summary"]["credits_earned"], 0)
        self.assertEqual(none_year["summary"]["fails"], 0)


class RecordsScopingTest(_RecordsBase):
    def test_dean_sees_only_own_faculty(self):
        with bypass_rls():
            scope = get_unit_scope(self.dean, self.org)
            data = records_overview.build_records_overview(
                organization=self.org, scope=scope, filters={}, offset=0, limit=100
            )
        self.assertTrue(scope.is_unit_scoped)
        self.assertTrue(data["has_access"])
        self.assertEqual(data["total"], 3)  # yalnız fakültə A-nın 3 tələbəsi

    def test_teacher_has_no_structure_access(self):
        with bypass_rls():
            scope = get_unit_scope(self.teacher, self.org)
            data = records_overview.build_records_overview(
                organization=self.org, scope=scope, filters={}, offset=0, limit=100
            )
        self.assertFalse(scope.has_structure_access)
        self.assertFalse(data["has_access"])
        self.assertEqual(data["total"], 0)

    def test_student_in_scope_respects_boundary(self):
        with bypass_rls():
            scope = get_unit_scope(self.dean, self.org)
            in_a = records_overview.student_is_in_scope(
                organization=self.org, scope=scope, student_id=self.students_a[0].id
            )
            in_b = records_overview.student_is_in_scope(
                organization=self.org, scope=scope, student_id=self.students_b[0].id
            )
        self.assertTrue(in_a)
        self.assertFalse(in_b)  # dekan B fakültəsinin tələbəsini görə bilməz


@override_settings(UNIVERSITY_MODE=True)
class RecordsEndpointTest(_RecordsBase):
    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_owner_data_endpoint(self):
        resp = self._client(self.owner).get(reverse("accounts:records_overview_data"))
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload["has_access"])
        self.assertEqual(payload["total"], 5)

    def test_teacher_data_endpoint_no_access(self):
        resp = self._client(self.teacher).get(reverse("accounts:records_overview_data"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["has_access"])

    def test_exam_center_sees_all_students_org_wide(self):
        """İmtahan mərkəzi mərkəzi rol → unit scope-u olmasa da bütün tələbələri görür."""
        resp = self._client(self.exam_center).get(reverse("accounts:records_overview_data"))
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload["has_access"])
        self.assertEqual(payload["total"], 5)

    def test_journal_teacher_search_endpoint(self):
        # Mərkəzi rol (imtahan mərkəzi) → 200 + düzgün forma; adi müəllim → boş.
        resp = self._client(self.exam_center).get(reverse("accounts:journal_teacher_search"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("results", resp.json())
        resp2 = self._client(self.teacher).get(reverse("accounts:journal_teacher_search"))
        self.assertEqual(resp2.json()["results"], [])

    def test_exam_center_profile_page_renders_section(self):
        resp = self._client(self.exam_center).get(reverse("accounts:profile"), {"section": "academic-records"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("profile-section--academic-records", resp.content.decode())

    def test_dean_faculty_lookup_scoped(self):
        resp = self._client(self.dean).get(reverse("accounts:records_faculty_search"))
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertEqual({r["text"] for r in results}, {"Fakültə A"})

    def test_student_detail_out_of_scope_blocked(self):
        resp = self._client(self.dean).get(
            reverse("accounts:records_student_detail"), {"student": str(self.students_b[0].id)}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["has_access"])

    def test_student_detail_in_scope_returns_record(self):
        resp = self._client(self.dean).get(
            reverse("accounts:records_student_detail"), {"student": str(self.students_a[0].id)}
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload["has_access"])
        self.assertTrue(len(payload["semesters"]) >= 1)

    def test_dean_profile_page_renders_section(self):
        """Dekan üçün tam profil səhifəsi academic-records bölməsini render edir."""
        resp = self._client(self.dean).get(reverse("accounts:profile"), {"section": "academic-records"})
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("profile-section--academic-records", html)
        self.assertIn("data-data-url", html)
        self.assertIn("js-acr-cards", html)

    def test_teacher_profile_page_hides_section(self):
        """Adi müəllim academic-records bölməsini görməməlidir (menyu + məzmun)."""
        resp = self._client(self.teacher).get(reverse("accounts:profile"), {"section": "academic-records"})
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertNotIn("profile-section--academic-records", html)
