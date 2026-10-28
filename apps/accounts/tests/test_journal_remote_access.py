"""Şəxsi jurnal şəbəkə istisnası digər hesablara və səthlərə keçməməlidir."""

from types import SimpleNamespace
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.accounts.journal_remote_access import journal_remote_access_allowed, journal_remote_auth
from apps.accounts.network_zone import NetworkZoneMiddleware
from core.admin_auth import ADMIN_2FA_VERIFIED_USER_SESSION_KEY


@override_settings(JOURNAL_REMOTE_USER_IDS=("41",), ADMIN_2FA_REQUIRED=False)
class JournalRemoteAccessTest(SimpleTestCase):
    def request(self, uid=41, path="/jurnal/", **fields):
        request = RequestFactory().get(path, REMOTE_ADDR="203.0.113.5")
        request.user = SimpleNamespace(pk=uid, is_authenticated=True, is_active=True, is_staff=False, **fields)
        request.session = {}
        return request

    def test_only_explicit_active_account_is_allowed(self):
        self.assertTrue(journal_remote_access_allowed(self.request()))
        self.assertFalse(journal_remote_access_allowed(self.request(42)))
        request = self.request()
        request.user.is_active = False
        self.assertFalse(journal_remote_access_allowed(request))
        request.user.is_active = True
        request.user.is_authenticated = False
        self.assertFalse(journal_remote_access_allowed(request))
        with override_settings(JOURNAL_REMOTE_USER_IDS=()):
            self.assertFalse(journal_remote_access_allowed(self.request()))

    def test_client_header_cannot_grant_access(self):
        request = self.request(42)
        request.META["HTTP_JOURNAL_REMOTE_USER_IDS"] = "42"
        self.assertEqual(journal_remote_auth(request).status_code, 403)
        self.assertEqual(journal_remote_auth(self.request()).status_code, 204)

    def test_view_as_uses_real_actor_not_target(self):
        request = self.request(41)
        request.is_view_as = True
        request.real_user = self.request(42).user
        self.assertFalse(journal_remote_access_allowed(request))
        request.user, request.real_user = request.real_user, request.user
        self.assertTrue(journal_remote_access_allowed(request))

    @override_settings(ADMIN_2FA_REQUIRED=True)
    def test_admin_must_have_account_bound_verified_2fa(self):
        request = self.request()
        request.user.is_staff = True
        self.assertFalse(journal_remote_access_allowed(request))
        request.session[ADMIN_2FA_VERIFIED_USER_SESSION_KEY] = "42"
        self.assertFalse(journal_remote_access_allowed(request))
        request.session[ADMIN_2FA_VERIFIED_USER_SESSION_KEY] = "41"
        self.assertTrue(journal_remote_access_allowed(request))

    @override_settings(NETWORK_ZONE_ENFORCED=True, INTERNAL_NETWORKS=[])
    @patch("apps.accounts.network_zone.temporary_superuser_exempt", return_value=False)
    @patch("apps.accounts.network_zone._HttpGateFacts.kind", return_value="teacher")
    def test_only_journal_network_gate_is_exempt(self, *_mocks):
        middleware = NetworkZoneMiddleware(lambda request: HttpResponse("domain permissions still run"))
        middleware._deny = lambda request, **kwargs: HttpResponse(status=403)
        self.assertEqual(middleware(self.request()).status_code, 200)
        self.assertEqual(middleware(self.request(42)).status_code, 403)
        self.assertEqual(middleware(self.request(path="/accounts/imtahan-bali/")).status_code, 403)
