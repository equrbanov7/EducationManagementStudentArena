"""«Nəticələrim» səthində akademik (registrar/jurnal) fənn nəticələri.

Köçürülmüş (legacy) tələbədə ``ExamAttempt``/``Submission`` sətri yoxdur — bütün
tarixçə registrar tərəfindədir. Bu testlər həmin sətirlərin «Nəticələrim»-də
göründüyünü, il/semestr süzgəcinin işlədiyini və rəqəmlərin «Ümumi tədris
məlumatı» bölməsini qidalandıran EYNİ qurucudan (``transcript``) gəldiyini —
yəni drift olmadığını — yoxlayır.
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.views._dashboard_helpers.academic_results import count_academic_items
from apps.accounts.views._dashboard_helpers.cheap_counts import count_my_results
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import finals, gradebook
from apps.registrar import public as registrar_public
from apps.registrar import services, transcript
from apps.registrar.models import Curriculum, CurriculumSubject, LessonKind, Program, StudentAcademicRecord, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


@override_settings(UNIVERSITY_MODE=True)
class MyResultsAcademicTest(TestCase):
    """İki semestrli (iki tədris ili) tələbə — süzgəc açılışları da dolur."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("mra_owner", "mra_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="MRA Univ",
                slug="mra-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.period_old = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2023/2024 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2023/2024",
                start_date="2023-09-01",
                end_date="2024-01-31",
            )
            cls.period_new = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2024/2025 Yaz",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2025-02-01",
                end_date="2025-06-30",
                is_current=True,
            )
            cls.chair = OrgUnit.objects.create(
                organization=cls.org, name="Kafedra", slug="mra-chair", unit_type=OrgUnitType.CHAIR
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="MRA-1", slug="mra-g1", unit_type=OrgUnitType.GROUP, parent=cls.chair
            )

            cls.teacher = User.objects.create_user("mra_teacher", "mra_teacher@qku.edu.az", "pw")
            cls.student = User.objects.create_user("mra_student", "mra_student@qku.edu.az", "pw")
            # Akademik qeydi OLMAYAN tələbə — boş vəziyyət mətnini yoxlamaq üçün.
            cls.blank_student = User.objects.create_user("mra_blank", "mra_blank@qku.edu.az", "pw")
            for user, role in (
                (cls.teacher, "teacher"),
                (cls.student, "student"),
                (cls.blank_student, "student"),
            ):
                # AKTİV membership şərtdir: offering instruktoru üçün PG trigger-i
                # (registrar_guard_active_member) insert-i əks halda rədd edir.
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    is_primary=True,
                    is_active=True,
                )

            cls.subject_old = Subject.objects.create(organization=cls.org, code="MRA101", name="Riyaziyyat", ects=6)
            cls.subject_new = Subject.objects.create(organization=cls.org, code="MRA102", name="Fizika", ects=5)

            program = Program.objects.create(
                organization=cls.org, code="MRAP", name="İxtisas", specialty_unit=cls.chair
            )
            curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2023)
            CurriculumSubject.objects.create(
                organization=cls.org, curriculum=curriculum, subject=cls.subject_old, semester_number=1
            )
            CurriculumSubject.objects.create(
                organization=cls.org, curriculum=curriculum, subject=cls.subject_new, semester_number=2
            )
            record = StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.student,
                program=program,
                curriculum=curriculum,
                group=cls.group,
                admission_year=2023,
            )
            services.enroll_mandatory_subjects(record=record, period=cls.period_old, semester_number=1)
            services.enroll_mandatory_subjects(record=record, period=cls.period_new, semester_number=2)

            # Köhnə semestr → keçir; yeni semestr → imtahandan kəsilir.
            cls._grade(cls.subject_old, datetime.date(2023, 10, 2), exam_score=45)
            cls._grade(cls.subject_new, datetime.date(2025, 3, 3), exam_score=5)

    @classmethod
    def _grade(cls, subject, first_lesson_day, *, exam_score):
        enrollment = cls.student.enrollments.get(offering__subject=subject)
        offering = enrollment.offering
        offering.instructor = cls.teacher
        offering.save(update_fields=["instructor"])
        for offset in range(4):
            lesson = gradebook.create_lesson(
                allow_past=True,
                offering=offering,
                date=first_lesson_day + datetime.timedelta(days=offset),
                kind=LessonKind.SEMINAR,
            )
            gradebook.save_marks(
                enforce_day=False,
                offering=offering,
                entries=[{"lesson_id": lesson.id, "enrollment_id": enrollment.id, "status": "present", "score": 10}],
                by_user=cls.teacher,
            )
        finals.set_exam_score(enrollment=enrollment, score=exam_score, by_user=cls.teacher)

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _results(self, user, **params):
        params.setdefault("section", "my-results")
        return self._client(user).get(reverse("accounts:profile"), params)

    # ── Sətirlər görünür ────────────────────────────────────────────────────
    def test_academic_rows_appear_in_my_results(self):
        resp = self._results(self.student)
        self.assertEqual(resp.status_code, 200)
        counts = resp.context["my_result_counts"]
        self.assertEqual(counts["academic"], 2)
        self.assertEqual(counts["all"], 2)  # yeni sistemdə heç bir cəhd/təhvil yoxdur
        self.assertContains(resp, "Riyaziyyat")
        self.assertContains(resp, "Fizika")
        self.assertContains(resp, 'data-profile-section-panel="my-results"')

    def test_rows_match_the_overall_record_builder(self):
        """Drift qapısı: hər bal «Ümumi tədris məlumatı» qurucusundan gəlməlidir."""
        resp = self._results(self.student)
        items = {item["title"]: item for item in resp.context["my_result_items"] if item["category"] == "academic"}
        with bypass_rls():
            record = transcript.build_student_overall_record(student=self.student, organization=self.org)
        expected = {row["subject"].name: row for semester in record["semesters"] for row in semester["rows"]}
        self.assertEqual(set(items), set(expected))
        for name, row in expected.items():
            academic = items[name]["academic"]
            self.assertEqual(academic["credit"], row["credit"])
            self.assertEqual(academic["entry_score"], row["result"]["entry_score"])
            self.assertEqual(academic["total"], row["result"]["total"])
            self.assertEqual(academic["letter"], row["result"]["letter"] if row["in_gpa"] else "")
            self.assertEqual(academic["fail_reason"], row["fail_reason"])

    def test_pass_and_fail_outcomes_are_labelled(self):
        resp = self._results(self.student)
        outcomes = {
            item["title"]: item["academic"]["outcome"]
            for item in resp.context["my_result_items"]
            if item["category"] == "academic"
        }
        self.assertEqual(outcomes["Riyaziyyat"], "pass")
        self.assertEqual(outcomes["Fizika"], "fail")

    # ── İl / semestr süzgəci ────────────────────────────────────────────────
    def test_filter_options_come_from_the_builder(self):
        resp = self._results(self.student)
        with bypass_rls():
            record = transcript.build_student_overall_record(student=self.student, organization=self.org)
        self.assertEqual(resp.context["my_results_year_options"], record["year_options"])
        self.assertEqual(resp.context["my_results_season_options"], record["season_options"])
        self.assertEqual(set(resp.context["my_results_year_options"]), {"2023/2024", "2024/2025"})

    def test_year_filter_narrows_the_list(self):
        resp = self._results(self.student, results_year="2023/2024")
        titles = [item["title"] for item in resp.context["my_result_items"]]
        self.assertEqual(titles, ["Riyaziyyat"])
        # Tab sayğacı süzgəcdən ASILI DEYİL — istifadəçi digər tabın boş olmadığını görsün.
        self.assertEqual(resp.context["my_result_counts"]["academic"], 2)

    def test_season_filter_narrows_the_list(self):
        resp = self._results(self.student, results_season="Yaz")
        titles = [item["title"] for item in resp.context["my_result_items"]]
        self.assertEqual(titles, ["Fizika"])

    def test_stray_year_param_does_not_blank_a_non_academic_tab(self):
        """URL-də ilişib qalmış ?results_year= "İmtahanlar" tabını boşaltmamalıdır —
        il/semestr anlayışı o tabda yoxdur, ona görə nəzərə alınmır."""
        resp = self._results(self.student, results_type="exams", results_year="2023/2024")
        self.assertEqual(resp.context["my_results_active_filter"], "exams")
        self.assertEqual(resp.context["my_result_counts"]["academic"], 2)

    def test_academic_tab_shows_only_academic_rows(self):
        resp = self._results(self.student, results_type="academic")
        self.assertEqual(resp.context["my_results_active_filter"], "academic")
        categories = {item["category"] for item in resp.context["my_result_items"]}
        self.assertEqual(categories, {"academic"})

    def test_newest_semester_first(self):
        resp = self._results(self.student)
        titles = [item["title"] for item in resp.context["my_result_items"]]
        self.assertEqual(titles, ["Fizika", "Riyaziyyat"])

    # ── Sayğaclar güzgülənir ────────────────────────────────────────────────
    def test_cheap_badge_count_mirrors_the_tab_count(self):
        client = self._client(self.student)
        resp = client.get(reverse("accounts:profile"), {"section": "my-results"})
        request = resp.wsgi_request
        with bypass_rls():
            cheap = count_my_results(request, self.student)
            rows = registrar_public.count_student_academic_record_rows(request, organization=self.org)
        self.assertEqual(rows, 2)
        self.assertEqual(cheap, resp.context["my_result_counts"]["all"])

    # ── Transkript AÇILMIR ──────────────────────────────────────────────────
    def test_no_transcript_link_or_download_offered(self):
        resp = self._results(self.student, results_type="academic")
        panel = resp.content.decode()
        panel = panel[panel.index('data-profile-section-panel="my-results"') :]
        panel = panel[: panel.index("</section>")]
        # Rəsmi transkriptə keçid və PDF/yükləmə düyməsi QƏSDƏN yoxdur — bu bölmə
        # sənəd deyil, sadəcə ekranda nəticə görüntüsüdür.
        self.assertNotIn("my-transcript", panel)
        self.assertNotIn("download", panel.lower())
        self.assertNotIn(".pdf", panel.lower())

    # ── CSP: inline CSS/JS QADAĞANDIR ───────────────────────────────────────
    def test_panel_has_no_inline_style_or_script(self):
        """CSP ``script-src``/``style-src`` üçün 'unsafe-inline' vermir — bölmə
        yalnız xarici fayl yükləməlidir (bax CLAUDE.md)."""
        import re

        resp = self._results(self.student)
        panel = resp.content.decode()
        panel = panel[panel.index('data-profile-section-panel="my-results"') :]
        panel = panel[: panel.index("</section>")]
        self.assertNotIn("<style", panel)
        self.assertIsNone(re.search(r"<script(?![^>]*\ssrc=)", panel), "inline <script> tapıldı")
        self.assertIn("accounts/js/profile/my_results_filters.js", panel)

    # ── Performans qapıları ─────────────────────────────────────────────────
    def test_badge_path_stays_cheap(self):
        """Sidebar badge-i HƏR profil açılışında hesablanır — o yol ağır qurucunu
        işə salmamalıdır. Akademik hədd yalnız TƏK ``COUNT(*)`` əlavə edir, yəni
        sorğu sayı qeydiyyat sayı ilə BÖYÜMÜR."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client = self._client(self.student)
        request = client.get(reverse("accounts:profile"), {"section": "profile-info"}).wsgi_request
        with bypass_rls():
            with CaptureQueriesContext(connection) as captured:
                count_my_results(request, self.student)
        # 4 mövcud sayğac + 1 akademik COUNT (+ scoping). Sabit üst hədd.
        self.assertLessEqual(len(captured), 8, [q["sql"] for q in captured])

    def test_heavy_builder_is_memoised_per_request(self):
        """``_collect_my_results`` və badge sayğacı eyni sorğuda ikinci dəfə
        aqreqasiya etməməlidir (qurucu bahalıdır: ~7 sorğu/qeydiyyat)."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from apps.accounts.views._dashboard_helpers.academic_results import collect_academic_items

        client = self._client(self.student)
        request = client.get(reverse("accounts:profile"), {"section": "profile-info"}).wsgi_request
        with bypass_rls():
            collect_academic_items(request)  # keşi doldurur
            with CaptureQueriesContext(connection) as second:
                collect_academic_items(request)
                count_academic_items(request)
        self.assertEqual(len(second), 0, [q["sql"] for q in second])

    # ── Boş vəziyyət izah edir ──────────────────────────────────────────────
    def test_empty_state_explains_why_it_is_empty(self):
        resp = self._results(self.blank_student)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["my_result_counts"]["all"], 0)
        self.assertContains(resp, "tədris hissəsi ilə əlaqə saxla")
