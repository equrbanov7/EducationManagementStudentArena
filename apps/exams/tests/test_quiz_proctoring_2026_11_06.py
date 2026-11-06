"""Sahib 2026-11-06: adi quiz + nəzarət (proctoring) — «Nəzarət otağı», «Bərpa et», dil seçimi.

Problemlər (sahibin mətni, qısa):
1. Dil seçimi gözə çarpmalıdır — tələbə «görmədim» deməsin.
2. Adi quiz-də nəzarət yanılı olanda: (a) UI sınır, xəta çıxır; (b) midterm/final-dakı kimi «Nəzarət otağı»
   yoxdur; (c) bloklanan tələbə üçün «Bərpa et» yoxdur; (d) quiz-də dil seçimi yoxdur, sonra «dil seç»
   xətası çıxır, amma tələbə seçə bilmir — imtahan başlamır.

Kök səbəblər:
* Canlı nəzarət yalnız İmtahan Mərkəzinin zal oturumu monitorunda idi (bilet/oturum üzərində). Zal axınında
  olmayan imtahanların (quiz, yazılı, praktiki) cəhdlərinə baxmaq və kilidli cəhdi açmaq üçün HEÇ BİR səhifə
  yox idi (``exam_center_ticket_resume`` bilet tələb edir) — tələbə «müəllim qərar verənə qədər gözləyin»
  ekranında ilişib qalırdı.
* Kabinet modalında dil seçimi yox idi; start təsdiq səhifəsində də yox idi. Server dili tapmayanda cəhd
  yaratmadan tələbəni siyahıya «dil seçin» xəbərdarlığı ilə qaytarırdı — seçmək üçün yer qalmırdı.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import (
    Exam,
    ExamAttempt,
    ExamLanguageVariant,
    ExamQuestion,
    ExamQuestionOption,
    ExamRoom,
    ExamSupervisionConfig,
    SupervisionIncident,
)
from apps.exams.services import attempts as attempts_service
from apps.exams.services import language_step
from apps.exams.services.start_intent import start_intent_token
from apps.exams.services.supervision import teacher_resume_attempt
from apps.exams.services.supervision.identity import can_view_student_photo
from apps.exams.tests.test_views import _assign_user_to_org, _login_with_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class _QuizBase(TestCase):
    exam_type = "test"
    category = "quiz"

    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user("qp_teacher", "qp_teacher@example.com", "StrongPass123!")
        cls.other_teacher = User.objects.create_user("qp_other", "qp_other@example.com", "StrongPass123!")
        cls.student = User.objects.create_user("qp_student", "qp_student@example.com", "StrongPass123!")
        cls.org = Organization.objects.create(
            name="QP Org", org_type=OrganizationType.UNIVERSITY, owner=cls.teacher, status="active", is_active=True
        )
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER)
        _assign_user_to_org(cls.other_teacher, cls.org, ProfileRole.TEACHER)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT)

    def make_exam(self, *, languages=("az",), variants=True, access_code=None, policy="teacher_controlled", **extra):
        exam = Exam.objects.create(
            author=self.teacher,
            organization=self.org,
            title="Quiz 1",
            exam_type=self.exam_type,
            exam_type_extended=self.category,
            is_active=True,
            total_duration_minutes=30,
            **({"access_code": access_code} if access_code else {}),
            **{"is_public": True, **extra},
        )
        order = 0
        for language in languages:
            if variants:
                ExamLanguageVariant.objects.create(exam=exam, language=language, is_active=True)
            for _ in range(2):
                order += 1
                question = ExamQuestion.objects.create(
                    exam=exam, order=order, text=f"Q{order}-{language}", language=language
                )
                if self.exam_type == "test":
                    for label in ("A", "B"):
                        ExamQuestionOption.objects.create(
                            question=question, label=label, text=label, is_correct=label == "A"
                        )
        ExamSupervisionConfig.objects.create(exam=exam, enabled=True, recovery_policy=policy)
        return exam

    def start_url(self, exam, user=None, **params):
        user = user or self.student
        query = "&".join(f"{key}={value}" for key, value in params.items())
        url = reverse("exams:start_exam", args=[exam.slug]) + "?si=" + start_intent_token(user.pk, exam.pk)
        return url + ("&" + query if query else "")

    def locked_attempt(self, exam, *, manual=False):
        return ExamAttempt.objects.create(
            user=self.student,
            exam=exam,
            status="in_progress",
            attempt_number=1,
            supervision_status="locked",
            supervision_violation_count=3,
            supervision_manual_lock=manual,
        )


class QuizLanguageChoiceTests(_QuizBase):
    """Problem 1 + 2d: dil seçimi məcburi, gözə çarpan addımdır və HƏR girişdən əlçatandır."""

    def test_multilingual_quiz_from_cabinet_shows_required_language_step_instead_of_bouncing(self):
        exam = self.make_exam(languages=("az", "ru"))
        _login_with_org(self.client, self.student, self.org)

        response = self.client.get(self.start_url(exam))

        # Əvvəl: 302 → kabinet + «dil seçin» xəbərdarlığı, seçim yeri yox idi.
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "exams/student/exam_start_confirm.html")
        html = response.content.decode()
        self.assertIn("data-language-step", html)
        self.assertIn('name="language" value="az" required', html)
        self.assertIn('name="language" value="ru" required', html)
        self.assertNotIn("checked", html.split("data-language-step", 1)[1].split("</fieldset>", 1)[0])
        self.assertFalse(ExamAttempt.objects.filter(exam=exam).exists())

    def test_posting_the_language_step_starts_attempt_in_chosen_language(self):
        exam = self.make_exam(languages=("az", "ru"))
        _login_with_org(self.client, self.student, self.org)
        url = self.start_url(exam)

        response = self.client.post(url, {"language": "ru"})

        self.assertEqual(response.status_code, 302)
        attempt = ExamAttempt.objects.get(exam=exam, user=self.student)
        self.assertEqual(attempt.language, "ru")
        self.assertEqual(set(attempt.answers.values_list("question__language", flat=True)), {"ru"})

    def test_posted_language_wins_over_stale_query_language(self):
        exam = self.make_exam(languages=("az", "ru"))
        _login_with_org(self.client, self.student, self.org)

        self.client.post(self.start_url(exam, language="az"), {"language": "ru"})

        self.assertEqual(ExamAttempt.objects.get(exam=exam, user=self.student).language, "ru")

    def test_submitting_without_language_shows_error_state_and_creates_nothing(self):
        exam = self.make_exam(languages=("az", "ru"))
        _login_with_org(self.client, self.student, self.org)

        response = self.client.post(self.start_url(exam), {})

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("els is-invalid", html)
        self.assertIn('id="els-error"', html)
        self.assertFalse(ExamAttempt.objects.filter(exam=exam).exists())

    def test_tokenless_confirm_page_also_has_the_language_step(self):
        exam = self.make_exam(languages=("az", "ru"))
        _login_with_org(self.client, self.student, self.org)

        response = self.client.get(reverse("exams:start_exam", args=[exam.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("data-language-step", response.content.decode())

    def test_single_language_quiz_starts_without_choice(self):
        exam = self.make_exam(languages=("az",))
        _login_with_org(self.client, self.student, self.org)

        response = self.client.get(self.start_url(exam))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamAttempt.objects.get(exam=exam, user=self.student).language, "az")

    def test_quiz_without_language_variants_starts_without_choice(self):
        exam = self.make_exam(languages=("az",), variants=False)
        _login_with_org(self.client, self.student, self.org)

        response = self.client.get(self.start_url(exam))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(ExamAttempt.objects.filter(exam=exam, user=self.student).exists())

    def test_ajax_code_check_without_language_returns_language_required(self):
        exam = self.make_exam(languages=("az", "ru"), access_code="123456")
        _login_with_org(self.client, self.student, self.org)

        response = self.client.post(
            reverse("exams:exam_code_check"),
            {"exam_slug": exam.slug, "access_code": "123456"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertTrue(payload["language_required"])
        self.assertEqual({option["language"] for option in payload["language_options"]}, {"az", "ru"})
        self.assertFalse(ExamAttempt.objects.filter(exam=exam).exists())

    def test_code_check_page_forwards_code_back_to_code_check(self):
        exam = self.make_exam(languages=("az", "ru"), access_code="123456")
        _login_with_org(self.client, self.student, self.org)

        response = self.client.post(reverse("exams:exam_code_check"), {"exam_slug": exam.slug, "access_code": "123456"})

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(f'action="{reverse("exams:exam_code_check")}"', html)
        self.assertIn('name="access_code" value="123456"', html)

        response = self.client.post(
            reverse("exams:exam_code_check"), {"exam_slug": exam.slug, "access_code": "123456", "language": "ru"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ExamAttempt.objects.get(exam=exam, user=self.student).language, "ru")


class CabinetLanguageStepTests(_QuizBase):
    """Kabinet («Təyin olunmuş tapşırıqlar») kartı modal üçün dilləri daşıyır."""

    def test_assigned_quiz_card_carries_language_options(self):
        exam = self.make_exam(languages=("az", "ru"), is_public=False)
        exam.allowed_users.add(self.student)
        _login_with_org(self.client, self.student, self.org)

        response = self.client.get(reverse("accounts:profile"), {"section": "assigned-exams"})

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(f'id="assigned-exam-languages-{exam.id}"', html)
        self.assertIn(f'data-language-options-id="assigned-exam-languages-{exam.id}"', html)
        self.assertIn('id="assignedExamLanguageStep"', html)
        self.assertIn("exams/css/exam_language_step.css", html)


class SupervisionRoomTests(_QuizBase):
    """Problem 2a–2c: quiz üçün «Nəzarət otağı» + «Bərpa et» + «Dayandır»."""

    def test_exam_detail_links_to_supervision_room(self):
        exam = self.make_exam()
        _login_with_org(self.client, self.teacher, self.org)

        response = self.client.get(reverse("exams:teacher_exam_detail", args=[exam.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("exams:exam_supervision_room", args=[exam.slug]))

    def test_room_page_renders_live_and_locked_students(self):
        exam = self.make_exam()
        attempt = self.locked_attempt(exam)
        _login_with_org(self.client, self.teacher, self.org)

        response = self.client.get(reverse("exams:exam_supervision_room", args=[exam.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="svr-root"')
        self.assertContains(response, "exams/js/supervision_room.js")
        snapshot = response.context["snapshot"]
        self.assertEqual(snapshot["counts"]["locked"], 1)
        row = snapshot["rows"][0]
        self.assertEqual(row["attempt_id"], attempt.pk)
        self.assertEqual(row["state"], "locked")
        self.assertTrue(row["can_resume"])

    def test_snapshot_json(self):
        exam = self.make_exam()
        self.locked_attempt(exam)
        _login_with_org(self.client, self.teacher, self.org)

        response = self.client.get(reverse("exams:exam_supervision_room_snapshot", args=[exam.slug]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["supervised"])
        self.assertEqual(payload["rows"][0]["username"], self.student.username)

    def test_resume_unlocks_student(self):
        exam = self.make_exam()
        attempt = self.locked_attempt(exam)
        _login_with_org(self.client, self.teacher, self.org)

        response = self.client.post(
            reverse("exams:exam_supervision_attempt_resume", args=[exam.slug, attempt.pk]), {"grant_extra_chance": "1"}
        )

        self.assertEqual(response.status_code, 200, response.content)
        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_status, "resumed")
        self.assertEqual(attempt.supervision_extra_chances, 1)
        self.assertTrue(
            SupervisionIncident.objects.filter(attempt=attempt, event_type="teacher_granted_chance").exists()
        )

    def test_resume_refused_when_policy_forbids_second_chance(self):
        exam = self.make_exam(policy="no_second_chance")
        attempt = self.locked_attempt(exam)
        _login_with_org(self.client, self.teacher, self.org)

        snapshot = self.client.get(reverse("exams:exam_supervision_room_snapshot", args=[exam.slug])).json()
        self.assertFalse(snapshot["rows"][0]["can_resume"])
        self.assertEqual(snapshot["rows"][0]["resume_refusal"], "policy")
        response = self.client.post(reverse("exams:exam_supervision_attempt_resume", args=[exam.slug, attempt.pk]))

        self.assertEqual(response.status_code, 409)
        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_status, "locked")

    def test_manual_pause_then_resume_round_trip(self):
        exam = self.make_exam(policy="no_second_chance")
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress", attempt_number=1)
        _login_with_org(self.client, self.teacher, self.org)

        response = self.client.post(
            reverse("exams:exam_supervision_attempt_pause", args=[exam.slug, attempt.pk]), {"reason": "telefon"}
        )
        self.assertEqual(response.status_code, 200, response.content)
        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_status, "locked")
        self.assertTrue(attempt.supervision_manual_lock)

        # Əl ilə pauza siyasətdən asılı olmadan həmişə bərpa olunur.
        response = self.client.post(reverse("exams:exam_supervision_attempt_resume", args=[exam.slug, attempt.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_status, "resumed")
        self.assertFalse(attempt.supervision_manual_lock)

    def test_attempt_detail_snapshot(self):
        exam = self.make_exam()
        attempt = self.locked_attempt(exam)
        _login_with_org(self.client, self.teacher, self.org)

        response = self.client.get(reverse("exams:exam_supervision_attempt_snapshot", args=[exam.slug, attempt.pk]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["attempt_id"], attempt.pk)
        self.assertIn("timeline", payload["proctor"])

    def test_room_is_closed_to_other_teachers_and_students(self):
        exam = self.make_exam()
        attempt = self.locked_attempt(exam)
        resume_url = reverse("exams:exam_supervision_attempt_resume", args=[exam.slug, attempt.pk])
        for user in (self.other_teacher, self.student):
            _login_with_org(self.client, user, self.org)
            room = self.client.get(reverse("exams:exam_supervision_room", args=[exam.slug]))
            self.assertIn(room.status_code, (403, 404), user.username)
            self.assertIn(self.client.post(resume_url).status_code, (403, 404), user.username)
        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_status, "locked")

    def test_attempt_of_another_exam_is_not_reachable(self):
        exam = self.make_exam()
        other_exam = self.make_exam()
        foreign = self.locked_attempt(other_exam)
        _login_with_org(self.client, self.teacher, self.org)

        response = self.client.post(reverse("exams:exam_supervision_attempt_resume", args=[exam.slug, foreign.pk]))

        self.assertEqual(response.status_code, 404)

    def test_resume_endpoint_requires_post(self):
        exam = self.make_exam()
        attempt = self.locked_attempt(exam)
        _login_with_org(self.client, self.teacher, self.org)

        response = self.client.get(reverse("exams:exam_supervision_attempt_resume", args=[exam.slug, attempt.pk]))

        self.assertEqual(response.status_code, 405)

    def test_student_lock_flow_is_resumable_end_to_end(self):
        """Tələbə pozuntu limitinə çatır → kilid → müəllim otaqdan bərpa edir → tələbə davam edir."""
        exam = self.make_exam()
        _login_with_org(self.client, self.student, self.org)
        self.assertEqual(self.client.get(self.start_url(exam)).status_code, 302)
        attempt = ExamAttempt.objects.get(exam=exam, user=self.student)
        log_url = reverse("exams:supervision_log_incident", args=[attempt.pk])
        for _ in range(3):
            self.client.post(
                log_url,
                data=json.dumps({"event_type": "tab_switched", "metadata": {}}),
                content_type="application/json",
            )
        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_status, "locked")
        take_url = reverse("exams:take_exam", args=[exam.slug, attempt.pk])
        self.assertEqual(self.client.get(take_url).status_code, 200)

        _login_with_org(self.client, self.teacher, self.org)
        response = self.client.post(reverse("exams:exam_supervision_attempt_resume", args=[exam.slug, attempt.pk]))
        self.assertEqual(response.status_code, 200, response.content)

        _login_with_org(self.client, self.student, self.org)
        self.assertEqual(self.client.get(take_url).status_code, 200)
        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_status, "active")

    def test_author_can_see_photo_of_own_exam_student_only(self):
        exam = self.make_exam()
        ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress", attempt_number=1)

        self.assertTrue(can_view_student_photo(self.teacher, self.org, self.student.pk))
        self.assertFalse(can_view_student_photo(self.other_teacher, self.org, self.student.pk))


class WrittenExamSupervisionRoomTests(SupervisionRoomTests):
    """Yazılı imtahan — eyni otaq, eyni bərpa."""

    exam_type = "written"
    category = "quiz"


class UncategorisedExamSupervisionRoomTests(SupervisionRoomTests):
    """Kateqoriyasız (adi) imtahan — eyni otaq."""

    exam_type = "test"
    category = None


class ReviewFixesTests(_QuizBase):
    """PR #225 review: kilid altında bərpa, dil səhifəsi start kilidinin xaricində."""

    def test_double_restore_is_refused_and_logs_one_incident(self):
        exam = self.make_exam()
        attempt = self.locked_attempt(exam)
        _login_with_org(self.client, self.teacher, self.org)
        url = reverse("exams:exam_supervision_attempt_resume", args=[exam.slug, attempt.pk])

        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertEqual(self.client.post(url).status_code, 409)

        self.assertEqual(
            SupervisionIncident.objects.filter(attempt=attempt, event_type__startswith="teacher_").count(), 1
        )

    def test_restore_refused_when_attempt_was_submitted_meanwhile(self):
        exam = self.make_exam()
        attempt = self.locked_attempt(exam)
        _login_with_org(self.client, self.teacher, self.org)
        # Sweep / tələbə otaq açılandan sonra cəhdi təhvil verib.
        ExamAttempt.objects.filter(pk=attempt.pk).update(status="submitted", finished_at=timezone.now())

        response = self.client.post(reverse("exams:exam_supervision_attempt_resume", args=[exam.slug, attempt.pk]))

        self.assertEqual(response.status_code, 409)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "submitted")

    def test_service_never_revives_a_stale_attempt_object(self):
        """Yaddaşdakı köhnə (kilidli, in_progress) obyekt — baza artıq təhvil verilib: bərpa rədd olunur."""
        exam = self.make_exam()
        stale = self.locked_attempt(exam)
        ExamAttempt.objects.filter(pk=stale.pk).update(status="submitted", finished_at=timezone.now())

        with self.assertRaises(ValueError):
            teacher_resume_attempt(stale, self.teacher)

        fresh = ExamAttempt.objects.get(pk=stale.pk)
        self.assertEqual(fresh.status, "submitted")
        self.assertFalse(SupervisionIncident.objects.filter(attempt=stale, event_type="teacher_resumed").exists())

    def test_language_page_is_rendered_outside_the_start_lock(self):
        exam = self.make_exam(languages=("az", "ru"))
        _login_with_org(self.client, self.student, self.org)
        held = {"now": False, "at_render": None}
        real_lock = attempts_service._exam_start_actor_lock
        real_render = language_step.language_choice_response

        @contextmanager
        def tracking_lock(*args, **kwargs):
            with real_lock(*args, **kwargs):
                held["now"] = True
                try:
                    yield
                finally:
                    held["now"] = False

        def tracking_render(*args, **kwargs):
            held["at_render"] = held["now"]
            return real_render(*args, **kwargs)

        with (
            mock.patch.object(attempts_service, "_exam_start_actor_lock", tracking_lock),
            mock.patch.object(language_step, "language_choice_response", tracking_render),
        ):
            response = self.client.get(self.start_url(exam))

        self.assertEqual(response.status_code, 200)
        self.assertIs(held["at_render"], False)


class CenterHallPauseTests(_QuizBase):
    """Zaldakı final cəhdini otaqdakı «Dayandır» yan keçə bilməz — rəsmi yol zal monitorudur."""

    category = "final"

    def test_pause_of_hall_attempt_is_refused_with_hall_monitor_link(self):
        exam = self.make_exam()
        room = ExamRoom.objects.create(organization=self.org, name="Zal QP", code="ZQP", capacity=10)
        attempt = ExamAttempt.objects.create(
            user=self.student, exam=exam, status="in_progress", attempt_number=1, room=room
        )
        _login_with_org(self.client, self.teacher, self.org)

        snapshot = self.client.get(reverse("exams:exam_supervision_room_snapshot", args=[exam.slug])).json()
        self.assertFalse(snapshot["rows"][0]["can_pause"])
        self.assertEqual(snapshot["rows"][0]["pause_refusal"], "hall")

        response = self.client.post(
            reverse("exams:exam_supervision_attempt_pause", args=[exam.slug, attempt.pk]), {"reason": "telefon"}
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["hall_monitor_url"], reverse("exams:exam_center_room_list"))
        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_status, "active")
        self.assertFalse(attempt.supervision_manual_lock)

    def test_pause_of_final_attempt_outside_any_hall_still_works(self):
        exam = self.make_exam()
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress", attempt_number=1)
        _login_with_org(self.client, self.teacher, self.org)

        response = self.client.post(reverse("exams:exam_supervision_attempt_pause", args=[exam.slug, attempt.pk]))

        self.assertEqual(response.status_code, 200, response.content)
