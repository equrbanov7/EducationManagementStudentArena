"""Müəllim nəticələri səhifəsi — cəhd büdcəsi və sorğu sayı (P1-9, 2026-09-12).

Audit tapıntısı: ``teacher_exam_results`` cəhd limiti olan imtahanlarda hər
sətir üçün ``exam.attempts_left_for(user)`` çağırırdı (cəhd başına 3 sorğu →
12-lik səhifədə ~36 əlavə sorğu), üstəlik eyni filtrlənmiş çoxluq üzərində
4 ayrı COUNT gedirdi (+ Paginator-un özününkü).

Bu testlər üç şeyi qoruyur:

1. **Toplu hesab modelin metodu ilə EYNİ nəticəni verir** — bitmiş statuslar,
   sınaq (trial) cəhdlərinin xaric edilməsi, fərdi əlavə cəhd qrantı, vaxtı
   keçmiş «davam edir» cəhdin bağlanıb sayılması, limitsiz imtahan (None).
2. **Sorğu sayı cəhd sayından asılı deyil** — 2 cəhd ilə 8 cəhd eyni büdcə.
3. **Render olunan məlumat dəyişməyib** — ``attempts_left`` və ``review_stats``
   birbaşa sorğularla üst-üstə düşür (test/yazılı, qrup filtri ilə də).
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAttempt, StudentExamAttemptGrant, StudentGroup
from apps.exams.services.attempt_budget import attempts_left_map
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


def _assign(user, organization, profile_role, role_name):
    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={"role": organization.roles.get(name=role_name), "is_primary": True, "is_active": True},
    )


class _ResultsBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user("rb_teacher", "rb_teacher@example.com", "pw")
        cls.org = Organization.objects.create(
            name="Results Budget Univ",
            slug="results-budget-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.teacher,
            status="active",
            is_active=True,
        )
        _assign(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")
        cls.students = []
        for index in range(1, 9):
            student = User.objects.create_user(
                f"rb_student{index}", f"rb_student{index}@example.com", "pw", first_name=f"Tələbə{index}"
            )
            _assign(student, cls.org, ProfileRole.STUDENT, "student")
            cls.students.append(student)
        cls.exam = Exam.objects.create(
            author=cls.teacher,
            title="Results Budget Exam",
            exam_type="test",
            is_active=True,
            max_attempts_per_user=3,
            total_duration_minutes=30,
        )

    def setUp(self):
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        self.url = reverse("exams:teacher_exam_results", args=[self.exam.slug])

    def _attempt(self, student, status="submitted", *, exam=None, is_trial=False, started_ago=None, **extra):
        exam = exam or self.exam
        attempt = ExamAttempt.objects.create(
            user=student,
            exam=exam,
            status=status,
            is_trial=is_trial,
            # (user, exam, attempt_number) unikaldır — növbəti nömrəni veririk.
            attempt_number=ExamAttempt.objects.filter(user=student, exam=exam).count() + 1,
            **extra,
        )
        if started_ago is not None:
            ExamAttempt.objects.filter(pk=attempt.pk).update(started_at=timezone.now() - started_ago)
            attempt.refresh_from_db()
        return attempt

    def _get(self, **params):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return response, ctx


class AttemptsLeftMapParityTest(_ResultsBase):
    """``attempts_left_map`` == hər istifadəçi üçün ``Exam.attempts_left_for``."""

    def test_matches_model_method_for_mixed_statuses(self):
        s = self.students
        self._attempt(s[0], "submitted")
        self._attempt(s[0], "submitted")
        self._attempt(s[1], "expired")
        self._attempt(s[2], "in_progress")  # bitməyib — sayılmır
        self._attempt(s[3], "draft")  # bitməyib — sayılmır
        self._attempt(s[4], "submitted", is_trial=True)  # sınaq — sayılmır
        self._attempt(s[5], "submitted")
        StudentExamAttemptGrant.objects.create(exam=self.exam, student=s[5], extra_attempts=2, granted_by=self.teacher)
        self._attempt(s[6], "submitted")
        self._attempt(s[6], "submitted")
        self._attempt(s[6], "expired")
        self._attempt(s[6], "submitted")  # limitdən çox — 0-da kəsilir
        # s[7]: heç bir cəhd yoxdur

        expected = {student.id: self.exam.attempts_left_for(student) for student in s}
        self.assertEqual(expected[s[0].id], 1)
        self.assertEqual(expected[s[5].id], 4)
        self.assertEqual(expected[s[6].id], 0)
        self.assertEqual(expected[s[7].id], 3)

        with CaptureQueriesContext(connection) as ctx:
            result = attempts_left_map(self.exam, [student.id for student in s])

        self.assertEqual(result, expected)
        # 1 köhnəlmiş-cəhd SELECT + 1 GROUP BY + 1 qrant SELECT — istifadəçi sayından asılı deyil.
        self.assertEqual(len(ctx), 3, [q["sql"] for q in ctx.captured_queries])

    def test_stale_in_progress_attempt_is_expired_and_counted_like_model_method(self):
        s = self.students
        # Vaxt limiti (30 dəq) çoxdan keçib, amma status hələ «davam edir».
        stale_a = self._attempt(s[0], "in_progress", started_ago=timedelta(hours=2))
        stale_b = self._attempt(s[1], "in_progress", started_ago=timedelta(hours=2))
        fresh = self._attempt(s[2], "in_progress", started_ago=timedelta(minutes=5))

        result = attempts_left_map(self.exam, [s[0].id, s[2].id])
        model_value = self.exam.attempts_left_for(s[1])

        stale_a.refresh_from_db()
        stale_b.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(stale_a.status, "expired")
        self.assertEqual(stale_b.status, "expired")
        self.assertEqual(fresh.status, "in_progress")
        self.assertEqual(result[s[0].id], 2)
        self.assertEqual(result[s[0].id], model_value)
        self.assertEqual(result[s[2].id], 3)

    def test_unlimited_exam_returns_none_without_queries(self):
        exam = Exam.objects.create(author=self.teacher, title="Limitsiz", exam_type="test", is_active=True)
        self._attempt(self.students[0], "submitted", exam=exam)

        with CaptureQueriesContext(connection) as ctx:
            result = attempts_left_map(exam, [self.students[0].id, self.students[1].id])

        self.assertEqual(result, {self.students[0].id: None, self.students[1].id: None})
        self.assertEqual(len(ctx), 0)
        self.assertIsNone(exam.attempts_left_for(self.students[0]))

    def test_duplicate_and_empty_user_ids_are_tolerated(self):
        self._attempt(self.students[0], "submitted")
        result = attempts_left_map(self.exam, [self.students[0].id, self.students[0].id, None])
        self.assertEqual(result, {self.students[0].id: 2})
        self.assertEqual(attempts_left_map(self.exam, []), {})


class TeacherResultsQueryBudgetTest(_ResultsBase):
    """Səhifə sorğu sayı cəhd sayından asılı deyil; render olunan rəqəmlər dəyişməyib."""

    # Cəhd/qrant cədvəllərini BİRBAŞA hədəfləyən sorğular (apellyasiya JOIN-i və
    # qrup alt-sorğusu kimi yan toxunuşlar, sessiya/RLS səs-küyü çıxılır).
    _ATTEMPT_QUERY_PREFIXES = (
        'UPDATE "exams_examattempt"',
        'SELECT COUNT("exams_examattempt"."id")',
        'SELECT COUNT(*) AS "__count" FROM "exams_examattempt"',
        'SELECT "exams_examattempt"."id"',
        'SELECT "exams_examattempt"."user_id" AS "user_id", COUNT',
        'SELECT "exams_studentexamattemptgrant"',
    )

    @classmethod
    def _attempt_queries(cls, ctx):
        return [q["sql"] for q in ctx.captured_queries if q["sql"].startswith(cls._ATTEMPT_QUERY_PREFIXES)]

    def test_query_count_is_independent_of_attempt_count(self):
        # İlk sorğu sessiya/profil isinməsi daşıyır — ölçmədən əvvəl bir dəfə açırıq.
        self.client.get(self.url)
        for student in self.students[:2]:
            self._attempt(student, "submitted")
        _, small = self._get()

        for student in self.students[2:8]:
            self._attempt(student, "submitted")
        response, large = self._get()

        self.assertEqual(
            len(small),
            len(large),
            f"2 cəhd: {len(small)} sorğu, 8 cəhd: {len(large)} sorğu",
        )
        # Cəhd cədvəlləri üzrə büdcə — 6 sorğu, sətir sayından asılı deyil:
        #   1 vaxtı keçmiş cəhdlərin toplu UPDATE-i (_expire_overdue_attempts)
        #   2 stat aqreqatı — total + graded (əvvəl 3-4 ayrı COUNT + Paginator COUNT idi)
        #   3 səhifə sətirləri (user/exam select_related)
        #   4 qalan cəhd: köhnəlmiş draft/in_progress SELECT (səhifənin tələbələri)
        #   5 qalan cəhd: bitmiş cəhdlər GROUP BY user_id
        #   6 qalan cəhd: fərdi qrantlar
        attempt_queries = self._attempt_queries(large)
        self.assertEqual(len(attempt_queries), 6, attempt_queries)
        self.assertEqual(sum(sql.startswith('SELECT "exams_studentexamattemptgrant"') for sql in attempt_queries), 1)
        self.assertEqual(sum(sql.startswith("SELECT COUNT(") for sql in attempt_queries), 1)
        # Paginator öz COUNT(*)-unu təkrar etmir — say aqreqatdan verilir.
        self.assertFalse([sql for sql in attempt_queries if sql.startswith('SELECT COUNT(*) AS "__count"')])
        self.assertEqual(len(response.context["attempts_data"]), 8)

    def test_rendered_attempts_left_and_stats_match_direct_computation(self):
        s = self.students
        self._attempt(s[0], "submitted")
        self._attempt(s[0], "expired")
        self._attempt(s[1], "submitted")
        StudentExamAttemptGrant.objects.create(exam=self.exam, student=s[1], extra_attempts=1, granted_by=self.teacher)
        self._attempt(s[2], "in_progress")
        self._attempt(s[3], "submitted", is_trial=True)  # siyahıda görünmür, limitə də sayılmır
        self._attempt(s[4], "submitted")
        self._attempt(s[4], "submitted")
        self._attempt(s[4], "submitted")

        response, _ = self._get()

        rows = {item["attempt"].id: item for item in response.context["attempts_data"]}
        visible = ExamAttempt.objects.filter(exam=self.exam, is_trial=False)
        self.assertEqual(set(rows), set(visible.values_list("id", flat=True)))
        for attempt in visible.select_related("user"):
            self.assertEqual(rows[attempt.id]["attempts_left"], self.exam.attempts_left_for(attempt.user), attempt)
        self.assertEqual(rows[ExamAttempt.objects.get(user=s[1]).id]["attempts_left"], 3)
        self.assertEqual(rows[ExamAttempt.objects.filter(user=s[4]).first().id]["attempts_left"], 0)

        stats = response.context["review_stats"]
        self.assertEqual(stats["total"], visible.count())
        self.assertEqual(stats["graded"], visible.count())
        self.assertEqual(stats["pending"], 0)
        self.assertEqual(stats["max_score"], 100)
        self.assertEqual(response.context["page_obj"].paginator.count, visible.count())

    def test_written_exam_stats_split_pending_and_graded(self):
        exam = Exam.objects.create(
            author=self.teacher, title="Yazılı", exam_type="written", is_active=True, max_attempts_per_user=2
        )
        s = self.students
        self._attempt(s[0], "submitted", exam=exam, checked_by_teacher=True)
        self._attempt(s[1], "submitted", exam=exam, checked_by_teacher=True)
        self._attempt(s[2], "submitted", exam=exam)
        self._attempt(s[3], "submitted", exam=exam, is_trial=True)
        url = reverse("exams:teacher_exam_results", args=[exam.slug])

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        stats = response.context["review_stats"]
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["graded"], 2)
        self.assertEqual(stats["pending"], 1)
        self.assertEqual(response.context["page_obj"].paginator.count, 3)

        response = self.client.get(url, {"checked": "unchecked"})
        stats = response.context["review_stats"]
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["graded"], 0)
        self.assertEqual(stats["pending"], 1)
        self.assertEqual(response.context["page_obj"].paginator.count, 1)

    def test_group_filter_distinct_queryset_keeps_stats_correct(self):
        s = self.students
        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="Büdcə qrupu")
        group.teachers.add(self.teacher)
        group.students.add(s[0], s[1])
        group.exams.add(self.exam)
        self._attempt(s[0], "submitted")
        self._attempt(s[1], "submitted")
        self._attempt(s[2], "submitted")

        response, _ = self._get(group=str(group.id))

        stats = response.context["review_stats"]
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["graded"], 2)
        self.assertEqual(response.context["page_obj"].paginator.count, 2)
        self.assertEqual(len(response.context["attempts_data"]), 2)
        for item in response.context["attempts_data"]:
            self.assertEqual(item["attempts_left"], 2)
