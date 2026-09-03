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
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts import academic_records as records_overview
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.organizations.scoping import ORG_WIDE_SCOPE, get_unit_scope
from apps.registrar import finals, gradebook, services, transcript
from apps.registrar.models import (
    Curriculum,
    CurriculumSubject,
    LegacyGradeFact,
    LessonKind,
    Program,
    StudentAcademicRecord,
    Subject,
)
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
            # Adi müəllim — struktur scope-u yoxdur. Aşağıdakı _make_group()
            # çağırışları offering.instructor=cls.teacher təyin edir, ona görə
            # bu üzvlük qruplar yaradılmazdan ƏVVƏL mövcud olmalıdır (trigger
            # instructor referansının aktiv grade.input üzvlüyünü tələb edir).
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
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
            Membership.objects.create(
                user=student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
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

    def test_rows_sorted_by_fails_desc_when_requested(self):
        """``sort="fails"`` — kəsri olan tələbələr öndə (bahalı, tam keçidli yol)."""
        with bypass_rls():
            data = records_overview.build_records_page(
                organization=self.org,
                scope=ORG_WIDE_SCOPE,
                filters={},
                offset=0,
                limit=100,
                sort=records_overview.SORT_FAILS,
            )
        fails = [r["fails"] for r in data["results"]]
        self.assertEqual(fails[0], 1)  # kəsri olan öndə
        self.assertEqual(fails, sorted(fails, reverse=True))  # azalan sıra pozulmur

    def test_default_sort_is_name_and_paginates_in_db(self):
        """Standart sıralama AD üzrədir — yəni bazada səhifələnə bilir.

        Səhifə-səhifə yığılan siyahı tam siyahı ilə eyni olmalıdır (offset
        sürüşməsi/təkrar sətir olmamalıdır)."""
        with bypass_rls():
            full = records_overview.build_records_page(
                organization=self.org, scope=ORG_WIDE_SCOPE, filters={}, offset=0, limit=100
            )
            first = records_overview.build_records_page(
                organization=self.org, scope=ORG_WIDE_SCOPE, filters={}, offset=0, limit=2
            )
            second = records_overview.build_records_page(
                organization=self.org, scope=ORG_WIDE_SCOPE, filters={}, offset=2, limit=2
            )
        names = [r["name"] for r in full["results"]]
        self.assertEqual(names, sorted(names))
        self.assertEqual([r["name"] for r in first["results"] + second["results"]], names[:4])
        self.assertTrue(first["has_more"])

    def test_page_query_count_does_not_grow_with_scope(self):
        """PERFORMANS MÜQAVİLƏSİ: bir səhifənin sorğu sayı scope-un tələbə
        sayından ASILI DEYİL.

        Bu testin mənası: səhifə bazada kəsilir və yalnız görünən tələbələr
        qiymətləndirilir. Əks halda (köhnə davranış) bütün scope hər səhifə
        üçün yenidən hesablanırdı — 5 000 tələbəlik təşkilatda 13 saniyə."""
        with bypass_rls():
            with CaptureQueriesContext(connection) as one:
                records_overview.build_records_page(
                    organization=self.org, scope=ORG_WIDE_SCOPE, filters={}, offset=0, limit=1
                )
            with CaptureQueriesContext(connection) as many:
                records_overview.build_records_page(
                    organization=self.org, scope=ORG_WIDE_SCOPE, filters={}, offset=0, limit=100
                )
        # 1 tələbə və bütün tələbələr — EYNİ sorğu sayı: per-student N+1 yoxdur,
        # hər şey bulk map-lardan gəlir.
        self.assertEqual(len(one.captured_queries), len(many.captured_queries))

    def test_student_with_two_programs_appears_once(self):
        """Unikallıq ``(org, student, program)`` üzrədir — ikinci ixtisası olan
        tələbə cədvəldə İKİ dəfə görünməməlidir (sayım da təkrarsızdır)."""
        student = self.students_a[0]
        with bypass_rls():
            base = StudentAcademicRecord.objects.get(organization=self.org, student=student)
            second_program = Program.objects.create(
                organization=self.org, code="PDUAL", name="İkinci ixtisas", specialty_unit=self.chair_a
            )
            # PG ``registrar_guard_student_record_coherence``: kurikulum ÖZ proqramına
            # aid olmalıdır (sqlite-də belə trigger yoxdur) — ikinci ixtisas üçün
            # ayrıca kurikulum yaradılır.
            second_curriculum = Curriculum.objects.create(
                organization=self.org, program=second_program, admission_year=2024, is_active=True
            )
            StudentAcademicRecord.objects.create(
                organization=self.org,
                student=student,
                program=second_program,
                curriculum=second_curriculum,
                group=base.group,
                admission_year=2024,
            )
            data = records_overview.build_records_page(
                organization=self.org, scope=ORG_WIDE_SCOPE, filters={}, offset=0, limit=100
            )
            summary = records_overview.build_records_summary(organization=self.org, scope=ORG_WIDE_SCOPE, filters={})
        ids = [r["student_id"] for r in data["results"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(data["total"], 5)
        self.assertEqual(summary["summary"]["students"], 5)

    def test_page_and_summary_match_combined_overview(self):
        """Bölünmüş iki çağırış (səhifə + box) birləşmiş icmalla eyni nəticə verir."""
        with bypass_rls():
            combined = records_overview.build_records_overview(
                organization=self.org, scope=ORG_WIDE_SCOPE, filters={}, offset=0, limit=3
            )
            page = records_overview.build_records_page(
                organization=self.org, scope=ORG_WIDE_SCOPE, filters={}, offset=0, limit=3
            )
            summary = records_overview.build_records_summary(organization=self.org, scope=ORG_WIDE_SCOPE, filters={})
        self.assertEqual(combined["results"], page["results"])
        self.assertEqual(combined["total"], page["total"])
        self.assertEqual(combined["summary"], summary["summary"])
        self.assertEqual(combined["year_options"], summary["year_options"])

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
        # Mərkəzi rol (imtahan mərkəzi / İKT rəhbəri) → 200 + düzgün forma; adi müəllim → boş.
        resp = self._client(self.exam_center).get(reverse("accounts:journal_teacher_search"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("results", resp.json())
        resp2 = self._client(self.teacher).get(reverse("accounts:journal_teacher_search"))
        self.assertEqual(resp2.json()["results"], [])

    def test_journal_teacher_search_is_offering_instructor_based_org_wide(self):
        # B) Jurnal müəllim filtri OFFERING-INSTRUCTOR əsaslıdır (view-as rol-əsaslı
        # deyil): mərkəzi rol org-wide olaraq YALNIZ dərs açılışı (offering) olan
        # müəllim(lər)i görür. cls.teacher yeganə instructor-dur → tam o qayıdır.
        # Rol daşıyan, amma offering-i olmayan istifadəçilər (məs. dekan) çıxmır.
        resp = self._client(self.exam_center).get(reverse("accounts:journal_teacher_search"))
        ids = {r["id"] for r in resp.json()["results"]}
        self.assertEqual(ids, {str(self.teacher.id)})
        self.assertNotIn(str(self.dean.id), ids)

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

    def test_student_detail_json_preserves_legacy_provenance_and_warning(self):
        """AJAX serializer ``row.legacy``-ni atmamalıdır.

        UI markeri bu lüğəti oxuyur; açar itməsinə görə əvvəllər serverdə fakt
        olsa da akademik-qeyd modalında mənşə və qırmızı warning görünmürdü.

        ``warning`` review statusundan asılı olmayan daimi legacy-bal
        bildirişidir; fakt sonradan VERIFIED olsa da itməməlidir.
        """
        student = self.students_a[1]
        enrollment = student.enrollments.get()
        with bypass_rls():
            LegacyGradeFact.objects.create(
                organization=self.org,
                enrollment=enrollment,
                source_system="myedu_mariadb",
                source_table="yekun",
                source_pk=88001,
                source_snapshot_sha256="a" * 64,
                source_row_hash="b" * 64,
                materialization_digest="c" * 64,
                transform_version="rehearsal-v1",
                evidence_kind="summary",
                score_code="yekun",
                mapping_status="linked",
                source_enrollment_ref="records-json:student-a1",
                entry_score_text="49",
                exam_score_text="45",
                resit_score_text="37",
                final_score_text="94",
            )

        response = self._client(self.dean).get(
            reverse("accounts:records_student_detail"),
            {"student": str(student.pk)},
        )

        self.assertEqual(response.status_code, 200)
        rows = [row for semester in response.json()["semesters"] for row in semester["rows"]]
        self.assertEqual(len(rows), 1)
        legacy = rows[0]["legacy"]
        self.assertEqual(
            (legacy["raw_entry"], legacy["raw_exam"], legacy["raw_final"], legacy["raw_resit"]),
            ("49", "45", "94", "37"),
        )
        self.assertEqual(legacy["warning"], "İmtahan Mərkəzi ilə dəqiqləşdirilsin")

        # Eyni təşkilatdakı qonşu tələbəyə fakt sızmır.
        neighbour = self._client(self.dean).get(
            reverse("accounts:records_student_detail"),
            {"student": str(self.students_a[2].pk)},
        )
        neighbour_rows = [row for semester in neighbour.json()["semesters"] for row in semester["rows"]]
        self.assertTrue(neighbour_rows)
        self.assertTrue(all(row["legacy"] is None for row in neighbour_rows))

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


class RecordsRoleGateTest(_RecordsBase):
    """Endpoint-lər rol qapısından keçməlidir — scope tək başına hüquq deyil.

    2026-07-31 auditi: `_scope()` yalnız `scope.has_structure_access` yoxlayırdı,
    `_resolve_unit_scope` isə rolun adına baxmadan HƏR üzvlüyün `scope_unit`-ini
    scope-a əlavə edir. «Müəllimi kafedraya təyin et» əməliyyatı məhz onu
    doldurur — yəni adi müəllim öz kafedra alt-ağacındakı bütün tələbələrin GPA
    və transkriptini oxuya bilirdi. Sidebar ona bu bölməni vermir, yəni endpoint
    UI-dan geniş idi.
    """

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _assign_teacher_to_chair(self):
        membership = Membership.objects.get(user=self.teacher, organization=self.org)
        membership.scope_unit = self.chair_a
        membership.save(update_fields=["scope_unit"])
        return membership

    def test_teacher_with_unit_scope_still_has_no_records_access(self):
        self._assign_teacher_to_chair()

        resp = self._client(self.teacher).get(reverse("accounts:records_overview_data"))

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["has_access"])

    def test_teacher_with_unit_scope_cannot_read_a_student_transcript(self):
        """Ən həssas endpoint: bir tələbənin semestr detalı + transkripti."""
        self._assign_teacher_to_chair()
        student = self.students_a[0]

        resp = self._client(self.teacher).get(
            reverse("accounts:records_student_detail"),
            {"student": student.id},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json().get("has_access", False))

    def test_teacher_with_unit_scope_cannot_enumerate_structure(self):
        """Axtarış seçiciləri də struktur/PII sızdırır — eyni qapıdan keçir."""
        self._assign_teacher_to_chair()
        client = self._client(self.teacher)

        for route in ("accounts:records_faculty_search", "accounts:records_department_search"):
            with self.subTest(route=route):
                resp = client.get(reverse(route))
                self.assertEqual(resp.status_code, 200)
                self.assertFalse(resp.json().get("has_access", True) and resp.json().get("results"))

    def test_dean_with_unit_scope_keeps_access(self):
        """Qapı idarəetmə rollarını kəsmir — dekan öz alt-ağacını görməyə davam edir."""
        resp = self._client(self.dean).get(reverse("accounts:records_overview_data"))

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload["has_access"])
        self.assertEqual(payload["total"], 3)  # yalnız fakültə A

    def test_role_gate_matches_the_sidebar_section_grant(self):
        """Endpoint UI-dan geniş olmamalıdır.

        Sidebar `academic-records` bölməsini superadmin / org_admin /
        unit_manager (dekan, kafedra müdiri) / imtahan mərkəzinə verir — rol
        qapısı da eyni dəsti tanımalıdır.
        """
        from apps.accounts.views.academic_records import ACADEMIC_RECORDS_ROLES

        self.assertIn("dean", ACADEMIC_RECORDS_ROLES)
        self.assertIn("department_head", ACADEMIC_RECORDS_ROLES)
        self.assertIn("exam_center", ACADEMIC_RECORDS_ROLES)
        self.assertIn("ikt_rehber", ACADEMIC_RECORDS_ROLES)
        self.assertNotIn("teacher", ACADEMIC_RECORDS_ROLES)
        self.assertNotIn("assistant_teacher", ACADEMIC_RECORDS_ROLES)
        self.assertNotIn("student", ACADEMIC_RECORDS_ROLES)
        self.assertNotIn("tutor", ACADEMIC_RECORDS_ROLES)


class UngradedEnrollmentTest(_RecordsBase):
    """«Qiymətləndirilməyib» (2026-08): nə keçən, nə kəsilən yazılış GÖRÜNÜR.

    Legacy köçürmədə 106 870 yazılışın 23 382-sinin (21.9 %) imtahan çıxış balı
    yoxdur — nə ``FinalGrade.exam_score``, nə ``ResitRecord.resit_score``. Belə
    sətir əvvəllər heç bir qutuya düşmürdü: krediti sayılmır, kəsrə də girmir,
    yəni ekranda sadəcə YOX idi. İndi öz qutusu və öz sütunu var.
    """

    def _drop_exam_score(self, student):
        from apps.registrar.models import FinalGrade

        with bypass_rls():
            FinalGrade.objects.filter(enrollment__student=student).delete()

    def test_an_enrollment_without_an_exam_score_is_counted_separately(self):
        # students_a[1] normalda KEÇİR (45 bal) — imtahan nəticəsini silirik.
        student = self.students_a[1]
        self._drop_exam_score(student)

        with bypass_rls():
            data = records_overview.build_records_overview(
                organization=self.org, scope=ORG_WIDE_SCOPE, filters={}, offset=0, limit=100
            )

        summary = data["summary"]
        self.assertEqual(summary["ungraded"], 1)
        # Kəsrə QARIŞMIR: cəm əvvəlki kimi 2-dir və q/b + 25% ilə tam örtülür.
        self.assertEqual(summary["fails"], 2)
        self.assertEqual(summary["qb"] + summary["exam25"], summary["fails"])
        row = next(r for r in data["results"] if r["username"] == student.username)
        self.assertEqual(row["ungraded"], 1)
        self.assertEqual(row["credits_earned"], 0)  # krediti də sayılmır

    def test_every_enrollment_lands_in_exactly_one_bucket(self):
        """Rəqəmlər məntiqli cəmlənir: keçən + kəsr + qiymətləndirilməyib = hamısı."""
        self._drop_exam_score(self.students_b[1])

        with bypass_rls():
            data = records_overview.build_records_overview(
                organization=self.org, scope=ORG_WIDE_SCOPE, filters={}, offset=0, limit=100
            )
            enrollments = sum(s.enrollments.count() for s in self.students_a + self.students_b)
            passed = sum(
                1
                for s in self.students_a + self.students_b
                for sem in transcript.build_student_overall_record(student=s, organization=self.org)["semesters"]
                for row in sem["rows"]
                if row["result"]["passed"]
            )

        summary = data["summary"]
        self.assertEqual(summary["ungraded"], 1)
        self.assertEqual(passed + summary["fails"] + summary["ungraded"], enrollments)

    def test_the_ungraded_counter_adds_no_query(self):
        """PERFORMANS MÜQAVİLƏSİ: sayğac mövcud keçidin İÇİNDƏdir, yeni sorğu yox."""
        with bypass_rls():
            with CaptureQueriesContext(connection) as before:
                records_overview.build_records_page(
                    organization=self.org, scope=ORG_WIDE_SCOPE, filters={}, offset=0, limit=100
                )
            self._drop_exam_score(self.students_a[1])
            with CaptureQueriesContext(connection) as after:
                records_overview.build_records_page(
                    organization=self.org, scope=ORG_WIDE_SCOPE, filters={}, offset=0, limit=100
                )

        self.assertEqual(len(before.captured_queries), len(after.captured_queries))


@override_settings(UNIVERSITY_MODE=True)
class UngradedDetailEndpointTest(_RecordsBase):
    """Drill-down: tələbənin fənn sətri «qiymətləndirilməyib» bayrağı daşıyır."""

    def test_the_student_detail_row_is_flagged_ungraded(self):
        from apps.registrar.models import FinalGrade

        student = self.students_a[1]
        with bypass_rls():
            FinalGrade.objects.filter(enrollment__student=student).delete()
        client = Client()
        client.force_login(self.exam_center)

        response = client.get(reverse("accounts:records_student_detail"), {"student": str(student.id)})

        self.assertEqual(response.status_code, 200)
        rows = [row for sem in response.json()["semesters"] for row in sem["rows"]]
        flagged = [row for row in rows if row["ungraded"]]
        self.assertEqual(len(flagged), 1)
        self.assertFalse(flagged[0]["passed"] or flagged[0]["failed"])
        self.assertIsNone(flagged[0]["total"])
