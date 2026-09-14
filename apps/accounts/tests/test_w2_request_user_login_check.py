"""2026-09-14 — `request.user` üçün giriş-bağlılığı yoxlamasının memoizasiyası (perf F-08).

Hər səhifədə eyni `accounts_userprofile.access_state` SELECT-i 3 dəfə gedirdi
(backend `get_user`, `AccountsMiddleware`, view-as köməkçiləri). Backend yükləyəndə
obyektə işarə qoyur; middleware/view-as həmin obyekt üçün DB-yə getmir.
Servis səthi (`user_access_is_login_blocked`) dəyişməyib — arxivləmə növbəti
sorğuda təzə obyektlə yenidən oxunur və giriş bağlanır.
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.identity import REQUEST_USER_LOGIN_CHECKED_ATTR, request_user_login_blocked
from apps.accounts.models import UserProfile
from apps.accounts.tests.test_cabinet_shell_query_budget import _build_tenant, _client_for

User = get_user_model()


class RequestUserLoginCheckMemoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = _build_tenant(slug="w2lc", subject_count=1)

    def _access_state_queries(self, client, url):
        client.get(url)
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(url)
        self.assertEqual(response.status_code, 200)
        return [q["sql"] for q in ctx.captured_queries if '"accounts_userprofile"."access_state" IN' in q["sql"]]

    def test_access_state_is_read_once_per_request(self):
        client = _client_for(self.tenant["org"], self.tenant["teacher"])
        url = reverse("accounts:profile") + "?section=profile-info"
        self.assertEqual(len(self._access_state_queries(client, url)), 1)

    def test_archived_account_is_still_logged_out_on_the_next_request(self):
        teacher = self.tenant["teacher"]
        client = _client_for(self.tenant["org"], teacher)
        url = reverse("accounts:profile") + "?section=profile-info"
        self.assertEqual(client.get(url).status_code, 200)
        UserProfile.objects.filter(user=teacher).update(access_state=UserProfile.AccessState.ARCHIVED)
        response = client.get(url)
        self.assertNotEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", client.session)

    def test_helper_only_trusts_the_backend_marker(self):
        teacher = self.tenant["teacher"]
        fresh = User.objects.get(pk=teacher.pk)
        with self.assertNumQueries(1):
            self.assertFalse(request_user_login_blocked(fresh))
        setattr(fresh, REQUEST_USER_LOGIN_CHECKED_ATTR, True)
        with self.assertNumQueries(0):
            self.assertFalse(request_user_login_blocked(fresh))
        UserProfile.objects.filter(user=teacher).update(access_state=UserProfile.AccessState.ARCHIVED)
        unmarked = User.objects.get(pk=teacher.pk)
        with self.assertNumQueries(1):
            self.assertTrue(request_user_login_blocked(unmarked))
