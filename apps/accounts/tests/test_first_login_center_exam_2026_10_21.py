"""İlk girişi bitməmiş tələbə final/midterm zal sessiyasında parol ekranına atılmır (sahib 2026-10-21)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.middleware import FirstLoginPasswordMiddleware

User = get_user_model()


class FirstLoginCenterExamTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("flc.student", "flc@flc.test", "pw")
        profile = self.user.profile
        profile.password_change_required = True
        profile.save(update_fields=["password_change_required", "updated_at"])
        self.factory = RequestFactory()
        self.mw = FirstLoginPasswordMiddleware(lambda request: "passed")

    def _call(self, path, *, ticket=False):
        request = self.factory.get(path)
        request.user = self.user
        request.session = {"final_exam_ticket_id": 7} if ticket else {}
        return self.mw(request)

    def test_entry_pages_are_reachable(self):
        self.assertEqual(self._call(reverse("exams:final_exam_entry")), "passed")
        self.assertEqual(self._call(reverse("exams:midterm_exam_entry")), "passed")

    def test_take_page_reachable_only_with_center_ticket(self):
        path = reverse("exams:take_exam", args=["mid-1", 123])
        self.assertEqual(self._call(path, ticket=True), "passed")
        response = self._call(path)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:set_initial_password"))

    def test_cabinet_stays_gated_even_with_ticket(self):
        response = self._call(reverse("accounts:profile"), ticket=True)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:set_initial_password"))


def test_session_key_matches_exam_centre():
    from apps.accounts.middleware_center_exam import CENTER_SESSION_KEY
    from apps.exams.services.final_center.entry import ENTRY_SESSION_KEY

    assert CENTER_SESSION_KEY == ENTRY_SESSION_KEY
