"""«Köhnə nəticə» yazma endpoint-inin XƏTA CAVABLARI daxili detal sızdırmır.

CodeQL `py/stack-trace-exposure` (2026-09-02 PR audit): ``PermissionDenied``
mətni birbaşa JSON cavaba qoyulurdu. Bu istisna Django-nun daxili qatlarından
da gələ bilir (mesajında sahə/model/yol adı ola bilər), ona görə klientə sabit
mətn qayıdır, səbəb isə server log-una yazılır.
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.views.legacy_review.policy import LegacyReviewActor

User = get_user_model()

_SECRET = "İç detal: LegacyGradeReview.reviewed_by /srv/app/apps/registrar/models.py"


class LegacyReviewActionErrorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("lra_user", "lra_user@qku.edu.az", "pw")

    def _client(self):
        client = Client()
        client.force_login(self.user)
        return client

    def _actor(self):
        return LegacyReviewActor(
            user=self.user, organization=object(), can_review=True, can_observe=True, is_superadmin=False
        )

    def test_permission_denied_message_is_not_echoed(self):
        with (
            mock.patch("apps.accounts.views.legacy_review.actions.resolve_actor", return_value=self._actor()),
            mock.patch(
                "apps.accounts.views.legacy_review.actions.review_write.record_decision",
                side_effect=PermissionDenied(_SECRET),
            ),
        ):
            resp = self._client().post(
                reverse("accounts:legacy_review_action"),
                {"action": "verify", "fact_id": "42"},
            )
        self.assertEqual(resp.status_code, 403)
        body = resp.content.decode("utf-8")
        self.assertNotIn("srv/app", body)
        self.assertNotIn("LegacyGradeReview", body)
        self.assertEqual(resp.json()["error"], "permission_denied")

    def test_denied_action_is_logged_without_newline_injection(self):
        with (
            mock.patch("apps.accounts.views.legacy_review.actions.resolve_actor", return_value=self._actor()),
            mock.patch(
                "apps.accounts.views.legacy_review.actions.review_write.record_decision",
                side_effect=PermissionDenied(_SECRET),
            ),
            self.assertLogs("apps.accounts.views.legacy_review.actions", level="WARNING") as captured,
        ):
            self._client().post(reverse("accounts:legacy_review_action"), {"action": "verify", "fact_id": "42"})
        # Yalnız allow-list-dəki `action` loglanır və o, təmizlənmiş dəyərdir.
        self.assertIn("action=verify", captured.records[0].getMessage())
