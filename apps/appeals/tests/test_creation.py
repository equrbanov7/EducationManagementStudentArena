"""Apellyasiya yaratma validasiya testləri."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.appeals.constants import APPEAL_MIN_COMMENT_LENGTH, APPEAL_TYPE_WRONG_ANSWER_KEY
from apps.appeals.models import AppealItem
from apps.appeals.services import create_appeal
from apps.appeals.services.scoring import accept_appeal_item
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.services.question_snapshot import build_question_snapshot
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()

VALID_COMMENT = "x" * APPEAL_MIN_COMMENT_LENGTH


def _assign_user_to_org(user, organization, profile_role, membership_role_name):
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


class AppealCreationTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("c_teacher", "c_t@example.com", "pw")
        self.student = User.objects.create_user("c_student", "c_s@example.com", "pw")
        self.org = Organization.objects.create(
            name="C Org", org_type=OrganizationType.UNIVERSITY, owner=self.teacher, status="active", is_active=True
        )
        self.exam = Exam.objects.create(
            title="C Exam", author=self.teacher, organization=self.org, exam_type="test", is_active=True
        )
        self.q1 = ExamQuestion.objects.create(exam=self.exam, order=1, text="Q1")
        self.q2 = ExamQuestion.objects.create(exam=self.exam, order=2, text="Q2")
        self.q_other = ExamQuestion.objects.create(exam=self.exam, order=3, text="Not delivered")
        self.attempt = ExamAttempt.objects.create(
            user=self.student, exam=self.exam, status="submitted", finished_at=timezone.now()
        )
        # Delivered set = q1, q2 (q_other NOT delivered).
        ExamAnswer.objects.create(attempt=self.attempt, question=self.q1)
        ExamAnswer.objects.create(attempt=self.attempt, question=self.q2)

    def _item(self, question, comment=VALID_COMMENT, appeal_type=APPEAL_TYPE_WRONG_ANSWER_KEY):
        return {"question_id": question.id, "appeal_type": appeal_type, "comment": comment}

    def test_create_single_item_appeal(self):
        appeal = create_appeal(attempt=self.attempt, student=self.student, items=[self._item(self.q1)])
        self.assertEqual(appeal.items.count(), 1)
        self.assertEqual(appeal.exam_id, self.exam.id)
        self.assertEqual(appeal.organization_id, self.org.id)

    def test_create_multi_item_appeal(self):
        appeal = create_appeal(
            attempt=self.attempt, student=self.student, items=[self._item(self.q1), self._item(self.q2)]
        )
        self.assertEqual(appeal.items.count(), 2)

    def test_empty_items_rejected(self):
        with self.assertRaises(ValidationError):
            create_appeal(attempt=self.attempt, student=self.student, items=[])

    def test_short_comment_rejected(self):
        with self.assertRaises(ValidationError):
            create_appeal(attempt=self.attempt, student=self.student, items=[self._item(self.q1, comment="too short")])

    def test_duplicate_question_rejected(self):
        with self.assertRaises(ValidationError):
            create_appeal(attempt=self.attempt, student=self.student, items=[self._item(self.q1), self._item(self.q1)])

    def test_question_already_appealed_for_attempt_rejected(self):
        create_appeal(attempt=self.attempt, student=self.student, items=[self._item(self.q1)])

        with self.assertRaisesMessage(ValidationError, "artıq göndərilib"):
            create_appeal(attempt=self.attempt, student=self.student, items=[self._item(self.q1)])

    def test_question_not_in_attempt_rejected(self):
        with self.assertRaises(ValidationError):
            create_appeal(attempt=self.attempt, student=self.student, items=[self._item(self.q_other)])

    def test_invalid_appeal_type_rejected(self):
        with self.assertRaises(ValidationError):
            create_appeal(
                attempt=self.attempt,
                student=self.student,
                items=[self._item(self.q1, appeal_type="not_a_type")],
            )


class AppealCreateViewTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("cv_teacher", "cv_t@example.com", "StrongPass123!")
        self.student = User.objects.create_user("cv_student", "cv_s@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="CV Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.student, self.org, ProfileRole.STUDENT, "student")
        self.exam = Exam.objects.create(
            title="CV Exam",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=True,
            is_public=True,
        )
        self.question = ExamQuestion.objects.create(exam=self.exam, order=1, text="GDPR sualı")
        self.correct = ExamQuestionOption.objects.create(
            question=self.question,
            label="A",
            text="Düzgün cavab",
            is_correct=True,
        )
        self.wrong = ExamQuestionOption.objects.create(
            question=self.question,
            label="B",
            text="Yanlış cavab",
            is_correct=False,
        )
        self.attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            status="submitted",
            finished_at=timezone.now(),
        )
        self.answer = ExamAnswer.objects.create(attempt=self.attempt, question=self.question, is_correct=False)
        self.answer.selected_options.add(self.wrong)
        self.client = Client()
        self.client.force_login(self.student)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def test_create_page_shows_student_and_correct_answer_and_search(self):
        response = self.client.get(reverse("appeals:appeal_create", args=[self.attempt.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-appeal-search", html=False)
        self.assertContains(response, "Tələbənin cavabı")
        self.assertContains(response, "Yanlış cavab")
        self.assertContains(response, "Düzgün cavab")
        self.assertContains(response, "data-appeal-text=", html=False)
        self.assertContains(response, "data-appeal-submit-hint", html=False)
        self.assertContains(response, "data-i18n-fix-both", html=False)
        self.assertContains(response, 'aria-disabled="true"', html=False)
        self.assertNotContains(response, "data-appeal-submit disabled", html=False)

    def test_result_and_appeal_render_frozen_snapshot_after_live_edit(self):
        self.question.text = "Çatdırılmış sual"
        self.question.save(update_fields=["text"])
        self.correct.text = "Çatdırılmış düzgün"
        self.correct.save(update_fields=["text"])
        self.wrong.text = "Çatdırılmış seçim"
        self.wrong.save(update_fields=["text"])
        self.answer.question_snapshot = build_question_snapshot(self.question, [self.correct, self.wrong])
        self.answer.selected_option_ids_snapshot = [self.wrong.id]
        self.answer.save(update_fields=["question_snapshot", "selected_option_ids_snapshot"])

        self.question.text = "Canlı redaktə edilmiş sual"
        self.question.save(update_fields=["text"])
        self.correct.text = "Canlı redaktə edilmiş düzgün"
        self.correct.is_correct = False
        self.correct.save(update_fields=["text", "is_correct"])
        self.wrong.text = "Canlı redaktə edilmiş seçim"
        self.wrong.is_correct = True
        self.wrong.save(update_fields=["text", "is_correct"])

        urls = [
            reverse("exams:exam_result", args=[self.exam.slug, self.attempt.id]),
            reverse("appeals:appeal_create", args=[self.attempt.id]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Çatdırılmış sual")
                self.assertContains(response, "Çatdırılmış düzgün")
                self.assertContains(response, "Çatdırılmış seçim")
                self.assertNotContains(response, "Canlı redaktə edilmiş")

    def test_result_and_appeal_legacy_answer_fall_back_to_live_question(self):
        self.answer.question_snapshot = {}
        self.answer.selected_option_ids_snapshot = None
        self.answer.save(update_fields=["question_snapshot", "selected_option_ids_snapshot"])
        self.question.text = "Legacy canlı sual"
        self.question.save(update_fields=["text"])

        for url in (
            reverse("exams:exam_result", args=[self.exam.slug, self.attempt.id]),
            reverse("appeals:appeal_create", args=[self.attempt.id]),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Legacy canlı sual")

    def _close_window(self):
        from datetime import timedelta

        # İmtahan 4 gün əvvəl bitib → 3-günlük pəncərə bağlıdır.
        self.attempt.finished_at = timezone.now() - timedelta(days=4)
        self.attempt.save(update_fields=["finished_at"])

    def test_closed_window_shows_readonly_notice_not_form(self):
        """3 gün keçib: səhifə 200 qaytarır, form yox, "müddət bitib" bildirişi var."""
        self._close_window()
        response = self.client.get(reverse("appeals:appeal_create", args=[self.attempt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Apellyasiya müddəti bitib")
        self.assertContains(response, "Nəticəyə bax")
        # Göndərmə formu görünmür.
        self.assertNotContains(response, "data-appeal-search", html=False)
        self.assertNotContains(response, "data-appeals-form", html=False)

    def test_closed_window_shows_existing_appeal_result(self):
        """Pəncərə açıq ikən verilmiş appeal, pəncərə bağlananda da statusu ilə görünür."""
        create_appeal(
            attempt=self.attempt,
            student=self.student,
            items=[
                {"question_id": self.question.id, "appeal_type": APPEAL_TYPE_WRONG_ANSWER_KEY, "comment": VALID_COMMENT}
            ],
        )
        self._close_window()
        response = self.client.get(reverse("appeals:appeal_create", args=[self.attempt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Apellyasiyanızın nəticəsi")

    def test_closed_window_post_does_not_create_appeal(self):
        """Bağlı pəncərədə crafted POST appeal yaratmır (view + servis guard)."""
        self._close_window()
        response = self.client.post(
            reverse("appeals:appeal_create", args=[self.attempt.id]),
            {
                f"appeal_q_{self.question.id}": "1",
                f"appeal_type_{self.question.id}": APPEAL_TYPE_WRONG_ANSWER_KEY,
                f"comment_{self.question.id}": VALID_COMMENT,
            },
        )
        self.assertEqual(response.status_code, 200)
        from apps.appeals.models import Appeal

        self.assertFalse(Appeal.objects.filter(attempt=self.attempt).exists())

    def test_service_rejects_appeal_after_window(self):
        """create_appeal servisi bağlı pəncərədə ValidationError atır (defense-in-depth)."""
        self._close_window()
        with self.assertRaises(ValidationError):
            create_appeal(
                attempt=self.attempt,
                student=self.student,
                items=[
                    {
                        "question_id": self.question.id,
                        "appeal_type": APPEAL_TYPE_WRONG_ANSWER_KEY,
                        "comment": VALID_COMMENT,
                    }
                ],
            )

    def test_create_page_from_profile_results_hides_answer_details(self):
        response = self.client.get(
            reverse("appeals:appeal_create", args=[self.attempt.id]),
            {
                "from_section": "my-results",
                "return_to": reverse("accounts:profile") + "?section=my-results",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "GDPR sualı")
        self.assertContains(response, "Cavabınız: səhv")
        self.assertNotContains(response, "Variantlar")
        self.assertNotContains(response, "Tələbənin cavabı")
        self.assertNotContains(response, "Yanlış cavab")
        self.assertNotContains(response, "Düzgün cavab")

    def test_create_page_shows_answer_details_immediately(self):
        """Məhsul qərarı (2026-07-13): tələbə təhvildən sonra dərhal öz
        cavablarını və detallarını görür — apellyasiya səthi də kilidsizdir."""
        self.exam.end_datetime = timezone.now() + timedelta(hours=1)
        self.exam.save(update_fields=["end_datetime"])

        response = self.client.get(reverse("appeals:appeal_create", args=[self.attempt.id]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["hide_answer_details"])
        self.assertContains(response, "GDPR sualı")

    def test_create_page_locks_questions_already_appealed(self):
        create_appeal(
            attempt=self.attempt,
            student=self.student,
            items=[
                {
                    "question_id": self.question.id,
                    "appeal_type": APPEAL_TYPE_WRONG_ANSWER_KEY,
                    "comment": VALID_COMMENT,
                }
            ],
        )

        response = self.client.get(reverse("appeals:appeal_create", args=[self.attempt.id]))

        self.assertContains(response, 'data-appeal-locked="1"', html=False)
        self.assertContains(response, "Bu sual üzrə apellyasiya artıq göndərilib")
        self.assertContains(response, "Artıq göndərilib")

        response = self.client.post(
            reverse("appeals:appeal_create", args=[self.attempt.id]),
            {
                f"appeal_q_{self.question.id}": "1",
                f"appeal_type_{self.question.id}": APPEAL_TYPE_WRONG_ANSWER_KEY,
                f"comment_{self.question.id}": VALID_COMMENT,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(AppealItem.objects.filter(appeal__attempt=self.attempt).count(), 1)
        self.assertContains(response, "artıq göndərilib")

    def test_create_page_has_no_marked_quick_select_button(self):
        # "İşarələnmişləri seç" sürətli düyməsi silinib (məntiqi əsası yox idi).
        self.attempt.marked_question_ids = [self.question.id]
        self.attempt.save(update_fields=["marked_question_ids"])

        response = self.client.get(reverse("appeals:appeal_create", args=[self.attempt.id]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-appeal-select-marked", html=False)

    def test_final_exam_hides_my_appeals_link_and_returns_to_entry_after_submit(self):
        self.exam.exam_type_extended = "final"
        self.exam.save(update_fields=["exam_type_extended"])

        response = self.client.get(reverse("appeals:appeal_create", args=[self.attempt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "section=my-appeals", html=False)
        # Final imtahanda sayt başlığı/naviqasiyası gizlədilir.
        self.assertNotContains(response, "blog-header", html=False)
        # Göndərmədən əvvəl təsdiq modalı olmalıdır.
        self.assertContains(response, "data-appeal-confirm-modal", html=False)

        response = self.client.post(
            reverse("appeals:appeal_create", args=[self.attempt.id]),
            {
                f"appeal_q_{self.question.id}": "1",
                f"appeal_type_{self.question.id}": APPEAL_TYPE_WRONG_ANSWER_KEY,
                f"comment_{self.question.id}": VALID_COMMENT,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("exams:final_exam_entry"))

    def test_final_exam_from_profile_results_returns_to_my_appeals_after_submit(self):
        self.exam.exam_type_extended = "final"
        self.exam.save(update_fields=["exam_type_extended"])
        params = {
            "from_section": "my-results",
            "return_to": reverse("accounts:profile") + "?section=my-results",
        }

        response = self.client.get(reverse("appeals:appeal_create", args=[self.attempt.id]), params)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "section=my-appeals", html=False)
        self.assertContains(response, "blog-header", html=False)

        response = self.client.post(
            reverse("appeals:appeal_create", args=[self.attempt.id]),
            {
                "from_section": "my-results",
                "return_to": reverse("accounts:profile") + "?section=my-results",
                f"appeal_q_{self.question.id}": "1",
                f"appeal_type_{self.question.id}": APPEAL_TYPE_WRONG_ANSWER_KEY,
                f"comment_{self.question.id}": VALID_COMMENT,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounts:profile") + "?section=my-appeals")


class AppealExamCenterRoutingTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("route_teacher", "route_t@example.com", "StrongPass123!")
        self.student = User.objects.create_user("route_student", "route_s@example.com", "StrongPass123!")
        self.exam_center = User.objects.create_user("route_center", "route_ec@example.com", "StrongPass123!")
        self.org = Organization.objects.create(
            name="Route Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.org, ProfileRole.TEACHER, "teacher")
        _assign_user_to_org(self.student, self.org, ProfileRole.STUDENT, "student")
        _assign_user_to_org(self.exam_center, self.org, ProfileRole.MEMBER, "exam_center_head")
        self.exam = Exam.objects.create(
            title="Route Appeal Exam",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=True,
            is_public=True,
        )
        self.question = ExamQuestion.objects.create(exam=self.exam, order=1, text="Route sualı")
        ExamQuestionOption.objects.create(question=self.question, label="A", text="Düz cavab", is_correct=True)
        self.attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            status="submitted",
            finished_at=timezone.now(),
        )
        ExamAnswer.objects.create(attempt=self.attempt, question=self.question)
        self.appeal = create_appeal(
            attempt=self.attempt,
            student=self.student,
            items=[
                {
                    "question_id": self.question.id,
                    "appeal_type": APPEAL_TYPE_WRONG_ANSWER_KEY,
                    "comment": VALID_COMMENT,
                }
            ],
        )

    def _client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_teacher_cannot_manage_or_review_appeals(self):
        client = self._client_for(self.teacher)

        self.assertEqual(client.get(reverse("appeals:manage_appeals")).status_code, 403)
        self.assertEqual(client.get(reverse("appeals:review_appeal", args=[self.appeal.id])).status_code, 403)

    def test_standalone_appeal_urls_redirect_to_dashboard_sections(self):
        # Standalone səhifə yoxdur → birbaşa URL sidebar-lı dashboard bölməsinə yönlənir.
        client = self._client_for(self.exam_center)

        manage_redirect = client.get(reverse("appeals:manage_appeals") + "?status=pending")
        self.assertEqual(manage_redirect.status_code, 302)
        self.assertIn("section=manage-appeals", manage_redirect["Location"])
        self.assertIn("status=pending", manage_redirect["Location"])

        review_redirect = client.get(reverse("appeals:review_appeal", args=[self.appeal.id]))
        self.assertEqual(review_redirect.status_code, 302)
        self.assertIn("section=manage-appeals", review_redirect["Location"])

        student_client = self._client_for(self.student)
        detail_redirect = student_client.get(reverse("appeals:appeal_detail", args=[self.appeal.id]))
        self.assertEqual(detail_redirect.status_code, 302)
        self.assertIn("section=my-appeals", detail_redirect["Location"])

    def test_exam_center_sees_all_org_appeals_and_can_review(self):
        client = self._client_for(self.exam_center)

        manage_response = client.get(reverse("appeals:manage_appeals") + "?fragment=1")
        self.assertEqual(manage_response.status_code, 200)
        self.assertContains(manage_response, "Route Appeal Exam")
        self.assertContains(manage_response, "data-appeal-manage-filter-form", html=False)
        self.assertContains(manage_response, "data-appeal-auto-search", html=False)

        review_response = client.get(reverse("appeals:review_appeal", args=[self.appeal.id]) + "?fragment=1")
        self.assertEqual(review_response.status_code, 200)
        self.assertContains(review_response, "Route sualı")
        self.assertContains(review_response, 'data-review-award="1"', html=False)
        self.assertContains(review_response, 'data-review-existing-delta="0"', html=False)

    def test_exam_center_profile_sidebar_shows_pending_appeal_badge(self):
        client = self._client_for(self.exam_center)

        response = client.get(reverse("accounts:profile"), {"section": "manage-appeals"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pending_appeals_count"], 1)
        self.assertInHTML(
            (
                '<span class="sidebar-menu-badge sidebar-menu-badge--warning sidebar-menu-badge--pulse" '
                'data-badge-key="pending_appeals_count">1</span>'
            ),
            response.content.decode(),
        )

    def test_profile_badges_api_updates_pending_appeals_after_decision(self):
        from django.core.cache import cache

        cache.clear()
        client = self._client_for(self.exam_center)
        badge_url = reverse("accounts:profile_badges_api")

        first_response = client.get(badge_url)
        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.json()["badges"]["pending_appeals_count"], 1)

        accept_appeal_item(self.appeal.items.first(), reviewer=self.exam_center, response_text="Qəbul")

        second_response = client.get(badge_url)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.json()["badges"]["pending_appeals_count"], 0)

    def test_review_ajax_accept_returns_score_delta_toast_and_list_edit_timer(self):
        client = self._client_for(self.exam_center)
        item = self.appeal.items.first()

        response = client.post(
            reverse("appeals:review_appeal", args=[self.appeal.id]) + "?fragment=1",
            {
                f"decision_{item.id}": "accept",
                f"response_{item.id}": "Açar səhv idi",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["score_delta"], "1")
        self.assertIn("+1 bal əlavə olundu", payload["toast"])
        self.assertIn("5 dəqiqədən sonra", payload["toast"])

        manage_response = client.get(reverse("appeals:manage_appeals") + "?fragment=1")
        self.assertContains(manage_response, "Dəyişmək üçün qalan vaxt")

        review_response = client.get(reverse("appeals:review_appeal", args=[self.appeal.id]) + "?fragment=1")
        self.assertContains(review_response, 'data-review-existing-delta="1"', html=False)

    def test_detail_score_update_notice_belongs_to_current_appeal(self):
        from datetime import timedelta

        second_question = ExamQuestion.objects.create(exam=self.exam, order=2, text="İkinci sual")
        ExamQuestionOption.objects.create(question=second_question, label="A", text="Düz cavab", is_correct=True)
        ExamAnswer.objects.create(attempt=self.attempt, question=second_question)
        second_appeal = create_appeal(
            attempt=self.attempt,
            student=self.student,
            items=[
                {
                    "question_id": second_question.id,
                    "appeal_type": APPEAL_TYPE_WRONG_ANSWER_KEY,
                    "comment": VALID_COMMENT,
                }
            ],
        )
        accept_appeal_item(self.appeal.items.first(), reviewer=self.exam_center, response_text="Qəbul")
        student_client = self._client_for(self.student)

        accepted_response = student_client.get(reverse("appeals:appeal_detail", args=[self.appeal.id]) + "?fragment=1")
        pending_response = student_client.get(reverse("appeals:appeal_detail", args=[second_appeal.id]) + "?fragment=1")

        self.assertNotContains(accepted_response, "Bu apellyasiya nəticəsində")
        self.assertContains(accepted_response, "Baxılır")
        self.assertNotContains(pending_response, "Bu apellyasiya nəticəsində")

        old_resolved_at = timezone.now() - timedelta(minutes=6)
        item = self.appeal.items.first()
        item.resolved_at = old_resolved_at
        item.save(update_fields=["resolved_at", "updated_at"])
        self.appeal.reviewed_at = old_resolved_at
        self.appeal.save(update_fields=["reviewed_at", "updated_at"])

        visible_response = student_client.get(reverse("appeals:appeal_detail", args=[self.appeal.id]) + "?fragment=1")
        self.assertContains(visible_response, "Bu apellyasiya nəticəsində +1 bal əlavə olundu")
        self.assertContains(visible_response, "Qəbul")
