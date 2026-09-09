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


class LegacyReviewObserverScopeTest(TestCase):
    """Oxu rejimindəki aktor növbəni GÖRMƏLİDİR (sahib şikayəti, 2026-09-09).

    Regressiya: `annotated_facts` əhatəni YALNIZ `final_score.entry` (yazma)
    açarı ilə həll edirdi. `journal.correct` daşıyan müşahidəçidə
    `has_structure_access` False çıxıb siyahı `none()`-a düşürdü — QA klonunda
    növbədə 22 759 sətir olduğu halda ekran boş görünürdü.
    """

    def test_observer_scope_falls_back_to_the_read_permission(self):
        from unittest.mock import patch

        from apps.registrar import legacy_grade_review as review

        class _Scope:
            def __init__(self, ok):
                self.has_structure_access = ok
                self.is_org_wide = ok

        calls = []

        def fake_scope(user, organization, permission):
            calls.append(permission)
            # Yazma açarı əhatə vermir, oxu açarı verir.
            return _Scope(permission == "journal.correct")

        with patch("apps.organizations.models.OrgUnit.user_permission_scope", staticmethod(fake_scope)):
            scope = review.actor_scope(object(), object())

        self.assertEqual(calls, ["final_score.entry", "journal.correct"])
        self.assertTrue(scope.has_structure_access)

    def test_write_permission_scope_wins_when_present(self):
        from unittest.mock import patch

        from apps.registrar import legacy_grade_review as review

        class _Scope:
            has_structure_access = True
            is_org_wide = True

        calls = []

        def fake_scope(user, organization, permission):
            calls.append(permission)
            return _Scope()

        with patch("apps.organizations.models.OrgUnit.user_permission_scope", staticmethod(fake_scope)):
            review.actor_scope(object(), object())

        # Yazma açarı əhatə verirsə ikinci sorğu ATILMIR.
        self.assertEqual(calls, ["final_score.entry"])
