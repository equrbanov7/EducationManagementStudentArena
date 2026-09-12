"""P1-3 (2026-09-10 auditi, düzəliş 2026-09-12): tələbə imtahan siyahısının sorğu büdcəsi.

Əvvəl ``_build_exam_items`` dövründə hər kart üçün ``can_user_see`` /
``attempts_left_for`` / ``can_user_start`` / ``registrar_block_reason`` /
``available_language_options`` ayrı-ayrı DB-yə gedirdi — 9 kartlıq səhifə
üçün ~130–180 sorğu. İndi bütün yoxlamalar səhifə üzrə TOPLU hesablanır
(``apps.exams.services.student_list_batch``) və sorğu sayı kart sayından
asılı deyil.

Bu modul üç şeyi kilidləyir:

* sorğu sayı 1 imtahan ilə 9 imtahan üçün EYNİDİR (sabit) və sərt büdcə daxilindədir;
* toplu nəticə hər imtahan üçün model metodlarının (tək-tək) nəticəsi ilə eynidir —
  görünən VƏ gizli (istisna, limiti bitmiş, qeyri-aktiv) imtahanlar daxil;
* render olunan kart məlumatı (cəhd qalığı, kod tələbi, jurnal blok səbəbi, dil
  modalı) köhnə per-imtahan hesabla eynidir.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.courses.models import Course, CourseMembership
from apps.exams.models import Exam, ExamAttempt, ExamQuestion, StudentExamAttemptGrant, StudentGroup
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import CourseOffering, Curriculum, Enrollment, Program, StudentAcademicRecord, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

# Sərt büdcə — 2026-09-12 ölçüsü (9 kart): 45 sorğu; təyinatlı siyahı (7 kart): 46.
# Tərkibi (hər biri kart sayından ASILI DEYİL):
#   middleware/auth/tenant: sessiya, user, 3× profil access_state, RLS
#     current_setting/set_config (bypass on/off + tenant GUC), üzvlük, profil → 11
#   siyahı: tab sayları aqreqatı (1) + canlı say (1) + Paginator COUNT (1)
#     + səhifə SELECT (1) + canlı sessiya xəritəsi (1)                         → 5
#   toplu qat (student_list_batch):
#     allowed_users, excluded_users, allowed_groups, kurs üzvlüyü             → 4
#     istifadəçinin aktiv cəhdləri (1), bitmiş cəhd sayı (1), qrantlar (1)     → 3
#     eyni-gün rəsmi imtahan (yalnız final/midterm olan səhifədə)             → 0–1
#     dil variantları (1), dil üzrə sual sayı (1), parity cəmi (0–1)          → 2–3
#     jurnal qapısı: dövr (1), yazılışlar (1), qayıb həddi (1),
#                    idmançı istisnası (1), donma (1)                         → 5
#   layout (base.html): üzvlük, profil, 2× bildiriş sayı, RLS on/off, təmizləmə → 14
# Əvvəl (eyni fikstura): 1 kart → 59, 9 kart → 143; təyinatlı: 1 → 60, 7 → 128.
# Ehtiyat 2 sorğu: dövr fallback-i / dərs-saatı fallback-i kimi məlumatdan asılı
# +1-lər üçün; middleware/layout-a yeni sorğu əlavə edən bu büdcəni ŞÜURLU qaldırır.
QUERY_BUDGET = 48


def _assign_user_to_org(user, organization, profile_role, *, membership_role_name):
    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={
            "role": organization.roles.get(name=membership_role_name),
            "is_primary": True,
            "is_active": True,
        },
    )


def _login_with_org(client, user, organization):
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()


class _StudentListFixture(TestCase):
    """Tələbə + müəllim + org + jurnal (qayıb qapısı) + kurs + qrup fiksturası."""

    def setUp(self):
        self.now = timezone.now()
        self.teacher = User.objects.create_user(
            username="p13_teacher", email="p13_teacher@example.com", password="StrongPass123!"
        )
        self.student = User.objects.create_user(
            username="p13_student", email="p13_student@example.com", password="StrongPass123!"
        )
        self.org = Organization.objects.create(
            name="P1-3 Universiteti",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.org, ProfileRole.TEACHER, membership_role_name="teacher")
        _assign_user_to_org(self.student, self.org, ProfileRole.STUDENT, membership_role_name="student")

        # Elektron jurnal: iki fənn — birində qayıb limiti keçilib (barred),
        # digərində keçilməyib.  lesson_hours=60, limit 25% → 15 saat icazəli.
        with bypass_rls():
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="2025/2026 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date="2025-09-15",
                end_date="2026-01-31",
                is_current=True,
            )
            self.program = Program.objects.create(
                organization=self.org, code="CS", name="Kompüter elmləri", absence_limit_percent=25
            )
            self.curriculum = Curriculum.objects.create(
                organization=self.org, program=self.program, admission_year=2025
            )
            self.group_unit = OrgUnit.objects.create(
                organization=self.org, name="P13-G1", slug="p13-g1", unit_type=OrgUnitType.GROUP
            )
            self.subject_barred = Subject.objects.create(organization=self.org, code="CS101", name="Proqramlaşdırma")
            self.subject_ok = Subject.objects.create(organization=self.org, code="CS102", name="Alqoritmlər")
            StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.student,
                program=self.program,
                curriculum=self.curriculum,
                group=self.group_unit,
                admission_year=2025,
            )
            self.offering_barred = CourseOffering.objects.create(
                organization=self.org,
                subject=self.subject_barred,
                period=self.period,
                group=self.group_unit,
                lesson_hours=60,
            )
            Enrollment.objects.create(
                organization=self.org, student=self.student, offering=self.offering_barred, absence_hours=20
            )
            self.offering_ok = CourseOffering.objects.create(
                organization=self.org,
                subject=self.subject_ok,
                period=self.period,
                group=self.group_unit,
                lesson_hours=60,
            )
            Enrollment.objects.create(
                organization=self.org, student=self.student, offering=self.offering_ok, absence_hours=5
            )

        self.course = Course.objects.create(owner=self.teacher, title="P1-3 Kursu", status="published")
        CourseMembership.objects.create(course=self.course, user=self.student, role="student")

        self.student_group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="P13-Q")
        self.student_group.students.add(self.student)

        _login_with_org(self.client, self.student, self.org)

    # ── köməkçilər ──────────────────────────────────────────────────────────
    def _exam(self, title, **kwargs):
        kwargs.setdefault("author", self.teacher)
        kwargs.setdefault("organization", self.org)
        kwargs.setdefault("is_active", True)
        return Exam.objects.create(title=title, **kwargs)

    def _question(self, exam, *, order=1, language="az", variant=None, points=1):
        return ExamQuestion.objects.create(
            exam=exam,
            text=f"{exam.title} — sual {order}",
            order=order,
            points=points,
            language=language,
            language_variant=variant,
        )

    def _submitted_attempt(self, exam, *, number=1, finished_at=None):
        return ExamAttempt.objects.create(
            user=self.student,
            exam=exam,
            status="submitted",
            attempt_number=number,
            finished_at=finished_at or self.now,
        )

    def _stale_attempt(self, exam, *, number=1):
        """Deadline-ı keçmiş in_progress cəhd (siyahı onu lazy expire edir)."""
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress", attempt_number=number)
        # started_at auto_now_add-dır → keçmiş dəyəri UPDATE ilə yaz.
        ExamAttempt.objects.filter(pk=attempt.pk).update(started_at=self.now - timedelta(hours=3))
        return attempt

    def _two_variants(self, exam, *, az_questions=1, en_questions=1):
        az = exam.language_variants.create(language="az", display_name="Azərbaycan dili")
        en = exam.language_variants.create(language="en", display_name="English")
        order = 1
        for _ in range(az_questions):
            self._question(exam, order=order, language="az", variant=az)
            order += 1
        for _ in range(en_questions):
            self._question(exam, order=order, language="en", variant=en)
            order += 1
        return az, en

    def _rich_public_exam(self):
        """Bütün toplu sorğu qollarını TƏK BAŞINA işə salan imtahan.

        public + kurs + jurnal fənni (barred) + cəhd limiti (1 bitmiş + qrant)
        + iki dil variantı.  «1 imtahan» ssenarisi məhz bundan ibarətdir ki,
        sorğu dəsti 9 imtahanlıq səhifə ilə eyni olsun.
        """
        exam = self._exam(
            "P13 Zəngin açıq",
            is_public=True,
            course=self.course,
            subject=self.subject_barred,
            max_attempts_per_user=3,
            total_duration_minutes=45,
        )
        self._two_variants(exam)
        self._submitted_attempt(exam)
        StudentExamAttemptGrant.objects.create(
            exam=exam, student=self.student, extra_attempts=1, granted_by=self.teacher
        )
        return exam

    def _mixed_public_exams(self):
        """Açıq siyahı üçün qarışıq giriş rejimləri (görünən 8 + zəngin = 9 kart)
        və SQL filtri ilə gizlədilən imtahanlar (yalnız müqayisə testində)."""
        exams = {}

        exam = self._exam("P13 Təyinatlı (allowed_users)", is_public=False)
        exam.allowed_users.add(self.student)
        self._question(exam)
        exams["allowed"] = exam

        exam = self._exam("P13 Qrup (allowed_groups)", is_public=False)
        exam.allowed_groups.add(self.student_group)
        self._question(exam)
        exams["group"] = exam

        exam = self._exam("P13 Kodlu təyinatlı", is_public=False, access_code="123456")
        exam.allowed_users.add(self.student)
        self._question(exam)
        exams["code"] = exam

        exam = self._exam("P13 Kurs üzvlüyü", is_public=False, course=self.course, subject=self.subject_ok)
        self._question(exam)
        exams["course"] = exam

        exam = self._exam("P13 Parity pozulub", is_public=True)
        self._two_variants(exam, az_questions=2, en_questions=1)
        exams["parity"] = exam

        exams["not_started"] = self._exam(
            "P13 Hələ başlamayıb",
            is_public=True,
            start_datetime=self.now + timedelta(days=1),
            end_datetime=self.now + timedelta(days=2),
        )

        exam = self._exam("P13 Tərk edilmiş cəhd", is_public=True, total_duration_minutes=30, max_attempts_per_user=2)
        self._question(exam)
        exams["stale"] = exam
        self.stale_attempt = self._stale_attempt(exam)

        exams["own"] = self._exam("P13 Tələbənin öz imtahanı", author=self.student, is_public=True)

        # ── SQL filtrinin gizlətdikləri (siyahıda görünmür) ──
        exam = self._exam("P13 İstisna edilmiş açıq", is_public=True)
        exam.excluded_users.add(self.student)
        exams["excluded"] = exam

        exam = self._exam("P13 Limiti bitmiş", is_public=True, max_attempts_per_user=1)
        self._submitted_attempt(exam)
        exams["exhausted"] = exam

        exams["inactive"] = self._exam("P13 Qeyri-aktiv", is_public=True, is_active=False)
        exams["unassigned"] = self._exam("P13 Təyinatsız qapalı", is_public=False)
        return exams

    def _rich_final_exam(self):
        """Təyinatlı siyahının «1 imtahan» ssenarisi: final + fənn + limit + dillər.

        Bugün bitmiş cəhdi var — digər final/midterm üçün «eyni gündə bir rəsmi
        imtahan» qaydasını da işə salır.
        """
        exam = self._exam(
            "P13 Final (təyinatlı)",
            is_public=False,
            exam_type_extended="final",
            subject=self.subject_ok,
            max_attempts_per_user=2,
        )
        exam.allowed_users.add(self.student)
        self._two_variants(exam)
        self._submitted_attempt(exam)
        return exam

    def _mixed_assigned_exams(self):
        exams = {}
        exam = self._exam("P13 Təyinatlı A", is_public=False)
        exam.allowed_users.add(self.student)
        self._question(exam)
        exams["allowed"] = exam

        exam = self._exam("P13 Qrup A", is_public=False)
        exam.allowed_groups.add(self.student_group)
        exams["group"] = exam

        exam = self._exam("P13 Kodlu A", is_public=False, access_code="654321")
        exam.allowed_users.add(self.student)
        exams["code"] = exam

        exam = self._exam("P13 Kurs A", is_public=False, course=self.course, subject=self.subject_barred)
        exams["course"] = exam

        exam = self._exam("P13 Kollokvium (gün qaydası)", is_public=False, exam_type_extended="midterm")
        exam.allowed_users.add(self.student)
        exams["midterm_blocked"] = exam

        exam = self._exam("P13 Kollokvium (qrantlı)", is_public=False, exam_type_extended="midterm")
        exam.allowed_users.add(self.student)
        StudentExamAttemptGrant.objects.create(
            exam=exam, student=self.student, extra_attempts=1, granted_by=self.teacher
        )
        exams["midterm_granted"] = exam
        return exams

    def _measure(self, url_name):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(reverse(url_name))
        self.assertEqual(response.status_code, 200)
        return response, ctx.captured_queries


class StudentListQueryBudgetTests(_StudentListFixture):
    """Sorğu sayı kart sayından asılı deyil və büdcə daxilindədir."""

    def test_available_list_query_count_is_independent_of_exam_count(self):
        self._rich_public_exam()
        # İsti-tur: ilk giriş sonrası sessiya sətri bir dəfəlik UPDATE olunur —
        # ölçüyə aidiyyatı olmayan «gizli» fərqi ölçümdən əvvəl sabitləşdiririk.
        self.client.get(reverse("exams:student_exam_list"))
        response, small = self._measure("exams:student_exam_list")
        self.assertEqual(len(response.context["page_obj"].object_list), 1)

        self._mixed_public_exams()
        self.client.get(reverse("exams:student_exam_list"))  # tərk edilmiş cəhdin expire yazısını udur
        response, large = self._measure("exams:student_exam_list")
        self.assertEqual(len(response.context["page_obj"].object_list), 9)

        print(f"\n[P1-3] student_exam_list: 1 imtahan → {len(small)} sorğu, 9 imtahan → {len(large)} sorğu")
        self.assertEqual(
            len(small),
            len(large),
            "Açıq imtahan siyahısının sorğu sayı kart sayı ilə artmamalıdır:\n"
            + "\n".join(q["sql"][:160] for q in large),
        )
        self.assertLessEqual(len(large), QUERY_BUDGET, [q["sql"][:160] for q in large])

    def test_assigned_list_query_count_is_independent_of_exam_count(self):
        self._rich_final_exam()
        self.client.get(reverse("exams:assigned_exam_list"))
        response, small = self._measure("exams:assigned_exam_list")
        self.assertEqual(len(response.context["page_obj"].object_list), 1)

        self._mixed_assigned_exams()
        response, large = self._measure("exams:assigned_exam_list")
        self.assertEqual(len(response.context["page_obj"].object_list), 7)

        print(f"\n[P1-3] assigned_exam_list: 1 imtahan → {len(small)} sorğu, 7 imtahan → {len(large)} sorğu")
        self.assertEqual(
            len(small),
            len(large),
            "Təyinatlı imtahan siyahısının sorğu sayı kart sayı ilə artmamalıdır:\n"
            + "\n".join(q["sql"][:160] for q in large),
        )
        self.assertLessEqual(len(large), QUERY_BUDGET, [q["sql"][:160] for q in large])


class StudentListBatchParityTests(_StudentListFixture):
    """Toplu qat hər imtahan üçün model metodları ilə EYNİ cavabı verir.

    Görünən və gizli imtahanların hamısı (istisna, limiti bitmiş, qeyri-aktiv,
    təyinatsız, rəsmi/gün qaydası, parity pozuntusu, tərk edilmiş cəhd) daxil.
    """

    def _all_exams(self):
        exams = [self._rich_public_exam(), self._rich_final_exam()]
        exams += list(self._mixed_public_exams().values())
        exams += list(self._mixed_assigned_exams().values())
        return exams

    def _page_exams(self, exams):
        """View-in istifadə etdiyi annotasiyalı/select_related formada yüklə."""
        from apps.exams.views.student.lists import _annotate_exam_list_base

        queryset = _annotate_exam_list_base(Exam.objects.filter(id__in=[exam.id for exam in exams]), self.student)
        return list(queryset.order_by("id"))

    def _request(self):
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.user = self.student
        return request

    def _model_snapshot(self, exam, request):
        from apps.exams.services.journal_sync import registrar_block_reason
        from apps.exams.services.language_parity import language_parity_error_message
        from apps.exams.services.language_variants import available_language_options

        return {
            "see": exam.can_user_see(self.student),
            "left": exam.attempts_left_for(self.student),
            "start": exam.can_user_start(self.student, code=None),
            "block": registrar_block_reason(request, exam),
            "options": available_language_options(exam),
            "parity": language_parity_error_message(exam),
        }

    def _batch_snapshot(self, batch, exam):
        return {
            "see": batch.can_user_see(exam),
            "left": batch.attempts_left_for(exam),
            "start": batch.can_user_start(exam, code=None),
            "block": batch.journal_block_reason(exam),
            "options": batch.available_language_options(exam),
            "parity": batch.language_parity_error_message(exam),
        }

    def _assert_fixture_exercises_branches(self, snapshot):
        """Fikstura həqiqətən bütün qolları işə salır — «hamısı None» ilə keçməsin."""
        from django.utils.translation import pgettext

        code_required = pgettext("exams.model.access", "access_code_required")
        self.assertIn("%", snapshot["P13 Zəngin açıq"]["block"])
        self.assertEqual(snapshot["P13 Zəngin açıq"]["left"], 3)  # 3 + 1 qrant − 1 bitmiş
        self.assertEqual([o["language"] for o in snapshot["P13 Zəngin açıq"]["options"]], ["az", "en"])
        self.assertEqual(snapshot["P13 Zəngin açıq"]["start"], (True, None))
        self.assertIsNone(snapshot["P13 Kurs üzvlüyü"]["block"])
        self.assertEqual(snapshot["P13 Kodlu təyinatlı"]["start"], (False, code_required))
        self.assertFalse(snapshot["P13 Parity pozulub"]["start"][0])
        self.assertTrue(snapshot["P13 Parity pozulub"]["parity"])
        self.assertEqual(snapshot["P13 Parity pozulub"]["start"][1], snapshot["P13 Parity pozulub"]["parity"])
        self.assertFalse(snapshot["P13 Hələ başlamayıb"]["start"][0])
        self.assertEqual(snapshot["P13 Tərk edilmiş cəhd"]["left"], 1)  # lazy expire → 1 istifadə olunub
        self.assertEqual(snapshot["P13 Tələbənin öz imtahanı"]["start"], (True, None))
        self.assertFalse(snapshot["P13 İstisna edilmiş açıq"]["see"])
        self.assertEqual(snapshot["P13 Limiti bitmiş"]["left"], 0)
        self.assertEqual(
            snapshot["P13 Limiti bitmiş"]["start"], (False, pgettext("exams.model.access", "attempt_limit_reached"))
        )
        self.assertFalse(snapshot["P13 Qeyri-aktiv"]["see"])
        self.assertFalse(snapshot["P13 Təyinatsız qapalı"]["see"])
        self.assertEqual(
            snapshot["P13 Kollokvium (gün qaydası)"]["start"],
            (False, pgettext("exams.model.access", "already_examined_today")),
        )
        self.assertEqual(snapshot["P13 Kollokvium (qrantlı)"]["start"], (False, code_required))
        self.assertEqual(snapshot["P13 Final (təyinatlı)"]["start"], (False, code_required))
        self.assertTrue(snapshot["P13 Qrup (allowed_groups)"]["see"])
        self.assertTrue(snapshot["P13 Kurs üzvlüyü"]["see"])

    def test_batch_matches_model_methods_when_batch_runs_first(self):
        from apps.exams.services.student_list_batch import StudentExamListBatch

        exams = self._page_exams(self._all_exams())
        request = self._request()
        with bypass_rls():
            batch = StudentExamListBatch(exams, self.student, request=request)
            got = {exam.title: self._batch_snapshot(batch, exam) for exam in exams}
            # Yan təsir də güzgülənir: tərk edilmiş cəhd toplu qatda expire olunub.
            self.stale_attempt.refresh_from_db()
            self.assertEqual(self.stale_attempt.status, "expired")
            expected = {exam.title: self._model_snapshot(exam, request) for exam in exams}

        self.assertEqual(got, expected)
        self._assert_fixture_exercises_branches(got)

    def test_batch_matches_model_methods_when_model_runs_first(self):
        from apps.exams.services.student_list_batch import StudentExamListBatch

        exams = self._page_exams(self._all_exams())
        request = self._request()
        with bypass_rls():
            expected = {exam.title: self._model_snapshot(exam, request) for exam in exams}
            batch = StudentExamListBatch(exams, self.student, request=request)
            got = {exam.title: self._batch_snapshot(batch, exam) for exam in exams}

        self.assertEqual(got, expected)
        self._assert_fixture_exercises_branches(got)

    def test_batch_matches_model_with_active_attempt_elsewhere_and_trial_attempt(self):
        """«Eyni anda bir imtahan»: başqa imtahanda HƏQİQƏTƏN aktiv cəhd hamısını
        bloklayır (öz imtahanı davam edir, müəllif azaddır); sınaq cəhdi limitə
        və blok qaydasına sayılmır."""
        from django.utils.translation import pgettext

        from apps.exams.services.student_list_batch import StudentExamListBatch

        exams = self._all_exams()
        running = self._exam("P13 Davam edən quiz", is_public=True, total_duration_minutes=60)
        ExamAttempt.objects.create(user=self.student, exam=running, status="in_progress")
        # Tələbənin öz imtahanında bitmiş SINAQ cəhdi: limitə sayılmır.
        own = next(exam for exam in exams if exam.title == "P13 Tələbənin öz imtahanı")
        own.max_attempts_per_user = 1
        own.save(update_fields=["max_attempts_per_user"])
        ExamAttempt.objects.create(user=self.student, exam=own, status="submitted", is_trial=True, finished_at=self.now)
        page = self._page_exams(exams + [running])
        request = self._request()
        with bypass_rls():
            batch = StudentExamListBatch(page, self.student, request=request)
            got = {exam.title: self._batch_snapshot(batch, exam) for exam in page}
            expected = {exam.title: self._model_snapshot(exam, request) for exam in page}

        self.assertEqual(got, expected)
        blocked = (False, pgettext("exams.model.access", "other_exam_in_progress"))
        self.assertEqual(got["P13 Davam edən quiz"]["start"], (True, None))
        self.assertEqual(got["P13 Zəngin açıq"]["start"], blocked)
        self.assertEqual(got["P13 Kodlu təyinatlı"]["start"], blocked)
        self.assertEqual(got["P13 Final (təyinatlı)"]["start"], blocked)
        self.assertEqual(got["P13 Tələbənin öz imtahanı"]["start"], (True, None))
        self.assertEqual(got["P13 Tələbənin öz imtahanı"]["left"], 1)

    def test_batch_with_empty_page_issues_no_queries(self):
        from apps.exams.services.student_list_batch import StudentExamListBatch

        with self.assertNumQueries(0):
            batch = StudentExamListBatch([], self.student, request=self._request())
        self.assertEqual(batch.exam_ids, [])


class StudentListRenderedItemsTests(_StudentListFixture):
    """Render olunan kart məlumatı köhnə per-imtahan hesabla eynidir."""

    def test_rendered_items_match_per_exam_computation(self):
        from django.test import RequestFactory

        from apps.exams.services.journal_sync import registrar_block_reason
        from apps.exams.services.language_variants import available_language_options

        self._rich_public_exam()
        self._mixed_public_exams()
        response = self.client.get(reverse("exams:student_exam_list"))
        self.assertEqual(response.status_code, 200)
        items = list(response.context["page_obj"].object_list)
        self.assertEqual(len(items), 9)

        request = RequestFactory().get("/")
        request.user = self.student
        with bypass_rls():
            for item in items:
                exam = item["exam"]
                self.assertEqual(item["left"], exam.attempts_left_for(self.student), exam.title)
                can_without_code, _ = exam.can_user_start(self.student, code=None)
                self.assertEqual(item["requires_code"], bool(exam.access_code and not can_without_code), exam.title)
                self.assertEqual(item["journal_block_reason"], registrar_block_reason(request, exam), exam.title)
                self.assertEqual(
                    item["language_options"],
                    [
                        {"language": option["language"], "display_name": option["display_name"]}
                        for option in available_language_options(exam)
                    ],
                    exam.title,
                )
                self.assertEqual(item["attempt_count"], exam.user_attempt_count or 0, exam.title)
                self.assertEqual(item["language_options_id"], f"exam-language-options-{exam.id}")

        by_title = {item["exam"].title: item for item in items}
        rich = by_title["P13 Zəngin açıq"]
        self.assertEqual(rich["left"], 3)
        self.assertIn("%", rich["journal_block_reason"])
        self.assertEqual([o["language"] for o in rich["language_options"]], ["az", "en"])
        self.assertEqual(rich["default_language"], "az")
        self.assertFalse(rich["requires_code"])
        self.assertEqual(rich["attempt_count"], 1)
        self.assertTrue(by_title["P13 Kodlu təyinatlı"]["requires_code"])
        self.assertEqual(by_title["P13 Tərk edilmiş cəhd"]["left"], 1)
        self.assertIsNone(by_title["P13 Kurs üzvlüyü"]["journal_block_reason"])
        # Parity pozuntusu start-ı bloklayır, amma dil seçimlərini gizlətmir (model ilə eyni).
        self.assertEqual([o["language"] for o in by_title["P13 Parity pozulub"]["language_options"]], ["az", "en"])
        self.assertIsNone(by_title["P13 Təyinatlı (allowed_users)"]["left"])
        self.assertContains(response, "P13 Zəngin açıq")
        self.assertNotContains(response, "P13 İstisna edilmiş açıq")
        self.assertNotContains(response, "P13 Limiti bitmiş")
