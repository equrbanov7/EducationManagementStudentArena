"""
Tests for core.admin_security — AdminSecurityMiddleware.

Covers:
* IP allowlist enforcement (403 for denied IPs, pass-through when list is empty)
* Admin login rate-limiting (429 after threshold, pass-through for non-POST)
* Correct pass-through for non-admin paths
"""

from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

from core.admin_security import AdminSecurityMiddleware

_LOCMEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "admin-security-tests",
    }
}


def _make_middleware(get_response=None):
    if get_response is None:

        def get_response(request):
            from django.http import HttpResponse

            return HttpResponse("ok")

    return AdminSecurityMiddleware(get_response)


class AdminIPRestrictionTest(TestCase):
    """IP allowlist checks."""

    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = _make_middleware()

    @override_settings(ADMIN_URL_PREFIX="admin/", ADMIN_ALLOWED_IPS=["10.0.0.1"])
    def test_allowed_ip_can_reach_admin(self):
        request = self.factory.get("/admin/", REMOTE_ADDR="10.0.0.1")
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    @override_settings(ADMIN_URL_PREFIX="admin/", ADMIN_ALLOWED_IPS=["10.0.0.1"])
    def test_denied_ip_receives_403(self):
        request = self.factory.get("/admin/", REMOTE_ADDR="1.2.3.4")
        response = self.middleware(request)
        self.assertEqual(response.status_code, 403)

    @override_settings(ADMIN_URL_PREFIX="admin/", ADMIN_ALLOWED_IPS=[])
    def test_empty_allowlist_permits_all_ips(self):
        request = self.factory.get("/admin/", REMOTE_ADDR="1.2.3.4")
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    @override_settings(ADMIN_URL_PREFIX="admin/", ADMIN_ALLOWED_IPS=["10.0.0.1"])
    def test_non_admin_path_not_restricted(self):
        request = self.factory.get("/accounts/login/", REMOTE_ADDR="1.2.3.4")
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    @override_settings(ADMIN_URL_PREFIX="manage/", ADMIN_ALLOWED_IPS=["10.0.0.1"])
    def test_custom_prefix_is_respected(self):
        # Old /admin/ is now unrestricted (different prefix)
        request_old = self.factory.get("/admin/", REMOTE_ADDR="1.2.3.4")
        response_old = self.middleware(request_old)
        self.assertEqual(response_old.status_code, 200)

        # New prefix is restricted
        request_new = self.factory.get("/manage/", REMOTE_ADDR="1.2.3.4")
        response_new = self.middleware(request_new)
        self.assertEqual(response_new.status_code, 403)

    @override_settings(ADMIN_URL_PREFIX="admin/", ADMIN_ALLOWED_IPS=["10.0.0.1"])
    def test_x_forwarded_for_is_used_for_ip(self):
        request = self.factory.get(
            "/admin/",
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_FORWARDED_FOR="10.0.0.1",
        )
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)

    @override_settings(ADMIN_URL_PREFIX="admin/", ADMIN_ALLOWED_IPS=["10.0.0.1"])
    def test_x_forwarded_for_denied_ip_blocked(self):
        request = self.factory.get(
            "/admin/",
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_FORWARDED_FOR="9.9.9.9",
        )
        response = self.middleware(request)
        self.assertEqual(response.status_code, 403)


@override_settings(
    CACHES=_LOCMEM_CACHE,
    ADMIN_URL_PREFIX="admin/",
    ADMIN_ALLOWED_IPS=[],
    ADMIN_LOGIN_RATE_LIMIT="2/5m",
)
class AdminLoginRateLimitTest(TestCase):
    """Admin login rate-limit checks."""

    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.middleware = _make_middleware()

    def test_first_post_is_allowed(self):
        request = self.factory.post("/admin/login/", REMOTE_ADDR="192.168.1.50")
        response = self.middleware(request)
        self.assertNotEqual(response.status_code, 429)

    def test_post_within_limit_is_allowed(self):
        for _ in range(2):
            request = self.factory.post("/admin/login/", REMOTE_ADDR="192.168.1.51")
            response = self.middleware(request)
        self.assertNotEqual(response.status_code, 429)

    def test_post_exceeding_limit_returns_429(self):
        for _ in range(2):
            self.factory.post("/admin/login/", REMOTE_ADDR="192.168.1.52")
            self.middleware(self.factory.post("/admin/login/", REMOTE_ADDR="192.168.1.52"))

        blocked = self.factory.post("/admin/login/", REMOTE_ADDR="192.168.1.52")
        response = self.middleware(blocked)
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)

    def test_get_to_login_is_not_rate_limited(self):
        # Exhaust POST quota first
        for _ in range(3):
            self.middleware(self.factory.post("/admin/login/", REMOTE_ADDR="192.168.1.53"))

        # GET must still succeed (no rate limit applied)
        request = self.factory.get("/admin/login/", REMOTE_ADDR="192.168.1.53")
        response = self.middleware(request)
        self.assertNotEqual(response.status_code, 429)

    def test_different_ips_have_independent_counters(self):
        ip_a, ip_b = "192.168.1.60", "192.168.1.61"
        # Exhaust ip_a
        for _ in range(3):
            self.middleware(self.factory.post("/admin/login/", REMOTE_ADDR=ip_a))

        # ip_b must still get through
        request = self.factory.post("/admin/login/", REMOTE_ADDR=ip_b)
        response = self.middleware(request)
        self.assertNotEqual(response.status_code, 429)

    def test_non_login_admin_path_not_rate_limited(self):
        for _ in range(3):
            self.middleware(self.factory.post("/admin/login/", REMOTE_ADDR="192.168.1.70"))

        # Different admin path must not be rate-limited
        request = self.factory.post("/admin/auth/user/add/", REMOTE_ADDR="192.168.1.70")
        response = self.middleware(request)
        self.assertNotEqual(response.status_code, 429)
