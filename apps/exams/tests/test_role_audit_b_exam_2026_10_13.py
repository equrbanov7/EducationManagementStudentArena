"""Rol auditi 2026-10-13 B1 — imtahan mərkəzinin QƏRAR əməlləri ``exam_center.decide`` açarı ilə.

Əvvəl rol ADI (``is_exam_center_user``) kifayət edirdi: imtahan mərkəzi işçisi və RİM əməkdaşı ikinci şans
verir, midterm/kollokvium pəncərəsini dəyişir, müəllimin sual göndərişini qəbul/rədd edirdi. İndi bölmələr
onlara GÖRÜNÜR (GET 200, yalnız-oxu), qərar POST-u 403-dür; rəhbər (açar miqrasiya 0061 / şablonla) qərar verir.
"""

from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.accounts.tests.test_midterm_windows_screen import _MidtermScreenBase
from apps.exams.models import QuestionSubmission, StudentExamAttemptGrant
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.exams.tests.test_question_submission import _Base as _SubmissionBase
from apps.exams.tests.test_second_chance import _Base as _ChanceBase
from apps.organizations.models import Membership
from apps.registrar.models import KollokviumWindow
from core.rls import bypass_rls

User = get_user_model()

_READ_ONLY_ROLES = ("exam_center_staff", "rim_staff")


def _make_users(org, prefix):
    users = {}
    for role_name in _READ_ONLY_ROLES:
        user = User.objects.create_user(f"{prefix}_{role_name}", f"{prefix}_{role_name}@test.az", PASSWORD)
        _assign_user_to_org(user, org, ProfileRole.MEMBER, role_name)
        users[role_name] = user
    return users


class SecondChanceDecisionKeyTests(_ChanceBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.readers = _make_users(cls.org, "b1sc")

    def _grant(self, user, exam):
        return self._client_for(user).post(
            reverse("accounts:exam_chance"), {"exam_id": str(exam.pk), "usernames": self.student.username}
        )

    def test_staff_and_rim_staff_see_section_but_cannot_grant(self):
        exam = self._make_exam("final", title="B1 final")
        for role_name, user in self.readers.items():
            with self.subTest(role=role_name):
                page = self._client_for(user).get(f"{reverse('accounts:profile')}?section=exam-chance")
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, "Son verilən şanslar")
                self.assertNotContains(page, 'name="exam_id"')
                self.assertEqual(self._grant(user, exam).status_code, 403)
        self.assertFalse(StudentExamAttemptGrant.objects.filter(exam=exam).exists())

    def test_head_grants(self):
        exam = self._make_exam("final", title="B1 final rəhbər")
        self.assertEqual(self._grant(self.center, exam).status_code, 302)
        self.assertTrue(StudentExamAttemptGrant.objects.filter(exam=exam, student=self.student).exists())


class QuestionSubmissionDecisionKeyTests(_SubmissionBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.readers = _make_users(cls.org, "b1qs")

    def _decide(self, user, submission):
        return self._client_for(user).post(
            reverse("exams:question_submission_decide", kwargs={"submission_id": submission.id}),
            {"decision": "accept", "bank_id": "", "new_bank_name": "B1 bankı"},
        )

    def test_staff_and_rim_staff_view_but_cannot_decide(self):
        submission = self._to_center(self._submission(title="B1 göndəriş"))
        review_url = reverse("exams:question_submission_review", kwargs={"submission_id": submission.id})
        for role_name, user in self.readers.items():
            with self.subTest(role=role_name):
                listing = self._client_for(user).get(f"{reverse('accounts:profile')}?section=question-submissions")
                self.assertEqual(listing.status_code, 200)
                self.assertContains(listing, "B1 göndəriş")
                review = self._client_for(user).get(review_url)
                self.assertEqual(review.status_code, 200)
                self.assertFalse(review.context["can_decide"])
                self.assertNotContains(review, "js-qsubr-form")
                self.assertEqual(self._decide(user, submission).status_code, 403)
        submission.refresh_from_db()
        # Yalnız-oxu baxış statusu da dəyişmir (chair_approved → center_review yalnız qərar verənlə).
        self.assertEqual(submission.status, QuestionSubmission.STATUS_CHAIR_APPROVED)

    def test_head_decides(self):
        submission = self._to_center(self._submission(title="B1 rəhbər göndərişi"))
        self.assertEqual(self._decide(self.exam_center, submission).status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_ACCEPTED)


class KollokviumWindowDecisionKeyTests(_MidtermScreenBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.readers = {}
        with bypass_rls():
            for role_name in _READ_ONLY_ROLES:
                user = User.objects.create_user(f"b1kw_{role_name}", f"b1kw_{role_name}@qku.edu.az", "pw")
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role_name),
                    is_primary=True,
                    is_active=True,
                )
                cls.readers[role_name] = user

    def _client_as(self, user):
        original, self.head = self.head, user
        try:
            return self._client()
        finally:
            self.head = original

    def _save_data(self):
        return {
            "action": "save_window",
            "period": str(self.midterm_period.pk),
            "k_index": "0",
            "opens_on": (self.today + datetime.timedelta(days=1)).isoformat(),
            "closes_on": (self.today + datetime.timedelta(days=10)).isoformat(),
        }

    def test_staff_and_rim_staff_see_windows_but_cannot_change(self):
        window = self._window(self.midterm_period, 0)
        for role_name, user in self.readers.items():
            with self.subTest(role=role_name):
                client = self._client_as(user)
                page = client.get(
                    reverse("accounts:profile"),
                    {
                        "section": "kollokvium-windows",
                        "win_year": self.midterm_period.year_display,
                        "period": str(self.midterm_period.pk),
                    },
                )
                self.assertEqual(page.status_code, 200)
                self.assertFalse(page.context["kollokvium_windows_section"]["can_decide"])
                self.assertNotContains(page, 'class="kw-cardbtns"')
                for data in (
                    self._save_data(),
                    {"action": "toggle_window_active", "window_id": str(window.pk)},
                    {"action": "delete_window", "window_id": str(window.pk)},
                ):
                    self.assertEqual(client.post(reverse("accounts:kollokvium_windows"), data).status_code, 403)
        with bypass_rls():
            window.refresh_from_db()
            self.assertFalse(window.is_active)
            self.assertEqual(KollokviumWindow.objects.filter(organization=self.org).count(), 1)

    def test_head_still_saves(self):
        _response, _messages = self._post(self._save_data())
        self.assertIn(0, self._windows(self.midterm_period))
