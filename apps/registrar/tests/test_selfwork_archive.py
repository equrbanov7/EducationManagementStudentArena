"""Köçürülmüş ("arxiv") sərbəst iş balının GÖRÜNMƏSİ — və giriş balının dəyişməzliyi.

Köhnə MyEdu sistemində sərbəst iş 0-10 arası TƏK BİR BAL idi (``si`` xanası);
köçürmə onu ``AssessmentComponent(kind=SELF_WORK)`` üzərində ``ComponentScore``
kimi saxlayır, amma hansı mövzuların təhvil verildiyi mənbədə olmadığı üçün
``SelfWorkMark`` çeklist sətirləri YARADILMIR. Nəticədə lövhə "0" göstərirdi.

Bu modul üç müqaviləni kilidləyir:

1. arxiv balı lövhədə GÖRÜNÜR (``archive_score`` + ``total``);
2. çeklist hələ də normal işləyir və arxiv balını ƏVƏZ EDİR (bloklanmır);
3. ⚠️ ƏN VACİBİ: ``entry_score_for`` (və analytics güzgüsü) DƏYİŞMİR — arxiv
   balı giriş balına ƏLAVƏ OLUNMUR, çünki o, köçürülmüş GENERIC qalığın içində
   artıq var (``girish + si`` = ikiqat sayma).

Əlavə: sorğu sayı tələbə sayı ilə ARTMIR (N+1 yoxdur).
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar import analytics, gradebook, journal_extras, selfwork_board, services
from apps.registrar.models import (
    AssessmentComponent,
    ComponentKind,
    ComponentScore,
    Curriculum,
    CurriculumSubject,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


def _activate_member(organization, user, role_name):
    """Aktiv üzvlük (PG ``registrar_guard_active_member`` tələbi)."""
    role, _created = Role.objects.get_or_create(
        organization=organization,
        name=role_name,
        defaults={"display_name": role_name.title(), "level": 50, "permissions": []},
    )
    Role.objects.filter(pk=role.pk).update(is_active=True)
    Membership.objects.get_or_create(organization=organization, user=user, role=role, defaults={"is_active": True})
    return role


class SelfWorkArchiveScoreTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("swa_owner", "swa_owner@qku.edu.az", "pw")
        self.teacher = User.objects.create_user("swa_teacher", "swa_teacher@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="SWA Univ",
                slug="swa-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            _activate_member(self.org, self.teacher, "teacher")
            self.group = OrgUnit.objects.create(
                organization=self.org, name="SWA-G1", slug="swa-g1", unit_type=OrgUnitType.GROUP
            )
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date="2025-09-01",
                end_date="2026-01-31",
                is_current=True,
            )
            self.program = Program.objects.create(organization=self.org, code="SWA", name="Sərbəst iş proqramı")
            self.curriculum = Curriculum.objects.create(
                organization=self.org, program=self.program, admission_year=2025
            )
            self.subject = Subject.objects.create(organization=self.org, code="SWA101", name="Fənn")
            CurriculumSubject.objects.create(
                organization=self.org, curriculum=self.curriculum, subject=self.subject, semester_number=1
            )
            self.student = self._add_student("swa_student")
            self.offering = self.student.enrollments.get().offering
            self.offering.instructor = self.teacher
            self.offering.save(update_fields=["instructor"])
            self.enrollment = self.offering.enrollments.get()

    # ── köməkçilər ───────────────────────────────────────────────────────
    def _add_student(self, username):
        student = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        # PostgreSQL-də `registrar_guard_active_member` trigger-i `Enrollment`-in
        # `student_id`-si üçün AKTİV üzvlük tələb edir (SQLite-da belə trigger
        # yoxdur — ona görə bu, yalnız PG-də üzə çıxır).
        _activate_member(self.org, student, "student")
        record = StudentAcademicRecord.objects.create(
            organization=self.org,
            student=student,
            program=self.program,
            curriculum=self.curriculum,
            group=self.group,
            admission_year=2025,
        )
        services.enroll_mandatory_subjects(record=record, period=self.period, semester_number=1)
        return student

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _write_archive(self, enrollment, value):
        """Köçürmənin (J5 ``journal_components``) yazdığı sətrin eynisi."""
        component = journal_extras.ensure_selfwork_component(self.offering)
        return ComponentScore.objects.create(
            organization=self.org,
            component=component,
            enrollment=enrollment,
            score=Decimal(value),
            entered_by=None,  # import xalis INSERT-dir, müəllif yoxdur
        )

    # ── 1. görünmə ───────────────────────────────────────────────────────
    def test_migrated_score_is_visible_when_checklist_is_empty(self):
        with bypass_rls():
            self._write_archive(self.enrollment, "7.00")
            board = journal_extras.get_selfwork_board(self.offering)

        self.assertTrue(board["has_archive"])
        row = board["rows"][0]
        self.assertEqual(row["archive_score"], 7)  # Decimal("7.00") → 7 (şablon üçün)
        self.assertEqual(row["checklist_total"], 0)
        self.assertEqual(row["total"], 7)  # ← sahibin gördüyü "0" burada idi

    def test_board_without_migrated_data_is_untouched(self):
        with bypass_rls():
            board = journal_extras.get_selfwork_board(self.offering)
        self.assertFalse(board["has_archive"])
        self.assertIsNone(board["rows"][0]["archive_score"])
        self.assertEqual(board["rows"][0]["total"], 0)

    def test_migrated_score_reaches_final_breakdown_column(self):
        with bypass_rls():
            self._write_archive(self.enrollment, "6")
            breakdown = journal_extras.get_final_breakdown(self.offering)
        self.assertEqual(breakdown["rows"][0]["selfwork"], 6)

    def test_no_selfwork_marks_are_invented(self):
        """si=7 görüb 7 mövzunu "təhvil verilib" işarələmək datanı uydurmaqdır."""
        from apps.registrar.models import SelfWorkMark

        with bypass_rls():
            self._write_archive(self.enrollment, "7")
            journal_extras.get_selfwork_board(self.offering)
            self.assertEqual(SelfWorkMark.objects.filter(enrollment=self.enrollment).count(), 0)

    def test_journal_page_renders_read_only_archive_column(self):
        with bypass_rls():
            self._write_archive(self.enrollment, "7")
        # QA 2026-09-05 (P1-8): tablar server tərəfdə ayrı-ayrı render olunur —
        # sərbəst iş paneli üçün `?jt=serbest` lazımdır.
        url = reverse("registrar:journal_detail", args=[self.offering.id]) + "?jt=serbest"
        resp = self._client(self.teacher).get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "jd-sw2-arch-val")  # oxu-only nişan (input DEYİL)
        self.assertContains(resp, 'data-jd-sw-archive="7"')
        self.assertContains(resp, "ARXİV")

    def test_journal_page_has_no_archive_column_without_migrated_data(self):
        url = reverse("registrar:journal_detail", args=[self.offering.id]) + "?jt=serbest"
        resp = self._client(self.teacher).get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "jd-sw2-arch-val")
        self.assertNotContains(resp, "data-jd-sw-archive")

    # ── 2. çeklist hələ də işləyir ───────────────────────────────────────
    def test_checklist_still_works_and_takes_over_from_archive(self):
        with bypass_rls():
            self._write_archive(self.enrollment, "7")
            topic = journal_extras.add_selfwork_topic(offering=self.offering, title="Mövzu 1")
            self.assertIsNotNone(topic, "arxiv balı yeni mövzu əlavə etməyi bloklamamalıdır")
            ok = journal_extras.set_selfwork_mark(
                offering=self.offering,
                topic_id=topic.id,
                enrollment_id=self.enrollment.id,
                done=True,
                by_user=self.teacher,
            )
            self.assertTrue(ok, "arxiv balı çeklist işarəsini bloklamamalıdır")
            board = journal_extras.get_selfwork_board(self.offering)

        row = board["rows"][0]
        self.assertEqual(row["checklist_total"], 1)
        self.assertEqual(row["total"], 1, "canlı çeklist arxiv balını əvəz edir")
        self.assertEqual(row["archive_score"], 7, "arxiv balı silinmir/pozulmur — yan-yana yaşayır")

    def test_effective_total_decision_table(self):
        # çeklist varsa çeklist; yoxdursa arxiv; ikisi də yoxdursa 0. CƏMLƏNMİR.
        self.assertEqual(selfwork_board.effective_total(3, 7), 3)
        self.assertEqual(selfwork_board.effective_total(0, 7), 7)
        self.assertEqual(selfwork_board.effective_total(0, None), 0)
        self.assertEqual(selfwork_board.effective_total(0, 0), 0)

    # ── 3. ⚠️ giriş balı DƏYİŞMİR (ikiqat saymanın qarşısı) ──────────────
    def test_entry_score_is_unchanged_by_archive_score(self):
        """Köçürülmüş ``si`` giriş balına ƏLAVƏ OLUNMUR — o, artıq qalığın içindədir."""
        with bypass_rls():
            # Köçürmənin (J5b) yazdığı mənzərə: GENERIC qalıq + kollokvium.
            generic = AssessmentComponent.objects.create(
                organization=self.org,
                offering=self.offering,
                name="Giriş qalığı",
                kind=ComponentKind.GENERIC,
                max_score=50,
                order=0,
            )
            kollokvium = journal_extras.ensure_kollokviums(self.offering)[0]
            ComponentScore.objects.create(
                organization=self.org, component=generic, enrollment=self.enrollment, score=Decimal("30")
            )
            ComponentScore.objects.create(
                organization=self.org, component=kollokvium, enrollment=self.enrollment, score=Decimal("8")
            )
            before = gradebook.entry_score_for(self.enrollment, 50)
            self.assertEqual(before, Decimal("38"))  # girish = qalıq + kollokvium

            self._write_archive(self.enrollment, "7")  # ← köçürülmüş si
            after = gradebook.entry_score_for(self.enrollment, 50)

        self.assertEqual(after, before, "arxiv balı giriş balına əlavə olunmamalıdır (girish + si = ikiqat sayma)")
        self.assertEqual(after, Decimal("38"))

    def test_entry_score_unchanged_without_generic_components(self):
        with bypass_rls():
            before = gradebook.entry_score_for(self.enrollment, 50)
            self._write_archive(self.enrollment, "9")
            after = gradebook.entry_score_for(self.enrollment, 50)
        self.assertEqual(after, before)

    def test_analytics_mirror_ignores_archive_score(self):
        """``analytics._selfwork_map`` ``entry_score_for``-un güzgüsüdür — o da oxumur."""
        with bypass_rls():
            self._write_archive(self.enrollment, "7")
            self.assertEqual(analytics._selfwork_map([self.enrollment.id]), {})

    # ── 4. performans: sorğu sayı sətir sayı ilə artmır ──────────────────
    def test_query_count_does_not_grow_with_students(self):
        with bypass_rls():
            self._write_archive(self.enrollment, "7")
            with CaptureQueriesContext(connection) as one_student:
                journal_extras.get_selfwork_board(self.offering)

            for i in range(4):
                student = self._add_student(f"swa_extra_{i}")
                self._write_archive(self.offering.enrollments.get(student=student), "5")
            self.assertEqual(self.offering.enrollments.count(), 5)

            with CaptureQueriesContext(connection) as five_students:
                board = journal_extras.get_selfwork_board(self.offering)

        self.assertEqual(len(board["rows"]), 5)
        self.assertEqual(
            len(five_students.captured_queries),
            len(one_student.captured_queries),
            "arxiv balları TƏK sorğu ilə çəkilməlidir — sətir-başına sorğu (N+1) yoxdur",
        )
