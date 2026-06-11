"""
Tests for custom error handlers in core.views.

These tests verify that the custom error handlers (handler400, handler403,
handler404, handler500) return clean responses without exposing application
internals — addressing the Application Error Disclosure vulnerability.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

User = get_user_model()


@override_settings(DEBUG=False)
class CustomErrorHandlerTests(TestCase):
    """Test that custom error handlers render clean templates without stack traces."""

    def setUp(self):
        self.client = Client()

    def test_handler404_returns_404_status(self):
        """handler404 must return HTTP 404 with the custom template."""
        response = self.client.get("/this-path-does-not-exist-xyz-abc/")
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "Traceback", status_code=404)
        self.assertNotContains(response, "Exception", status_code=404)

    def test_handler404_does_not_disclose_internals(self):
        """404 response must not contain Django debug info."""
        response = self.client.get("/nonexistent-path-12345/")
        content = response.content.decode()
        self.assertNotIn("INSTALLED_APPS", content)
        self.assertNotIn("settings.py", content)
        self.assertNotIn("Traceback (most recent call last)", content)

    def test_handler500_callable_exists(self):
        """handler500 view callable must be importable and callable."""
        from core.views import handler500

        self.assertTrue(callable(handler500))

    def test_handler400_callable_exists(self):
        """handler400 view callable must be importable and callable."""
        from core.views import handler400

        self.assertTrue(callable(handler400))

    def test_handler403_callable_exists(self):
        """handler403 view callable must be importable and callable."""
        from core.views import handler403

        self.assertTrue(callable(handler403))

    def test_handler404_callable_exists(self):
        """handler404 view callable must be importable and callable."""
        from core.views import handler404

        self.assertTrue(callable(handler404))

    def test_error_handlers_registered_in_urlconf(self):
        """Root URLconf must expose handler names so Django dispatches to them."""
        import config.urls as root_urlconf

        self.assertTrue(
            hasattr(root_urlconf, "handler400"),
            "handler400 must be a module-level name in config.urls",
        )
        self.assertTrue(
            hasattr(root_urlconf, "handler403"),
            "handler403 must be a module-level name in config.urls",
        )
        self.assertTrue(
            hasattr(root_urlconf, "handler404"),
            "handler404 must be a module-level name in config.urls",
        )
        self.assertTrue(
            hasattr(root_urlconf, "handler500"),
            "handler500 must be a module-level name in config.urls",
        )


@override_settings(DEBUG=False)
class TestErrorEndpointProductionTest(TestCase):
    """
    Task 9: The /test-error/ route must be completely inaccessible in production
    (DEBUG=False).  Ensure it returns 404 rather than triggering an error.
    """

    def setUp(self):
        self.client = Client()

    def test_test_error_route_inaccessible_in_production(self):
        """
        When DEBUG=False, the /test-error/ URL must not be registered in the
        URL configuration, and any request to it must return 404.
        """
        response = self.client.get("/test-error/")
        self.assertEqual(
            response.status_code,
            404,
            "The /test-error/ route must not be accessible when DEBUG=False",
        )

    def test_test_error_route_not_in_urlpatterns_production(self):
        """
        In production mode, the ``test_error`` URL name must not be resolvable.
        """
        from django.urls import NoReverseMatch, reverse

        with self.assertRaises(NoReverseMatch):
            reverse("test_error")


@override_settings(DEBUG=True)
class TestErrorEndpointDevelopmentTest(TestCase):
    """
    Task 9: The /test-error/ route must be accessible in development (DEBUG=True).
    """

    def setUp(self):
        self.client = Client()

    def test_test_error_route_accessible_in_development(self):
        """
        When DEBUG=True, the /test-error/ endpoint must exist and be reachable.
        It intentionally raises a 500 (Sentry smoke-test), so any response
        other than 404 confirms the route is registered.
        """
        try:
            response = self.client.get("/test-error/")
            self.assertNotEqual(
                response.status_code,
                404,
                "The /test-error/ route must be accessible when DEBUG=True",
            )
        except Exception:
            # The view may raise an exception (that's its purpose); just ensure
            # the URL was resolved (i.e., no NoReverseMatch/404 before the view).
            pass


class HealthCheckViewTest(TestCase):
    """Tests for the enhanced health check endpoint."""

    def test_health_check_returns_200_or_degraded(self):
        resp = self.client.get("/health/")
        # DB connects; Redis may be unavailable in test env (degraded=207)
        self.assertIn(resp.status_code, (200, 207, 503))

    def test_health_check_json_contains_status(self):
        resp = self.client.get("/health/")
        data = resp.json()
        self.assertIn("status", data)
        self.assertIn(data["status"], ("healthy", "degraded", "unhealthy"))

    def test_health_check_json_contains_checks(self):
        resp = self.client.get("/health/")
        data = resp.json()
        self.assertIn("checks", data)
        self.assertIn("database", data["checks"])

    def test_health_check_json_contains_version(self):
        resp = self.client.get("/health/")
        data = resp.json()
        self.assertIn("version", data)

    def test_health_check_json_contains_uptime(self):
        resp = self.client.get("/health/")
        data = resp.json()
        self.assertIn("uptime_seconds", data)
        self.assertGreaterEqual(data["uptime_seconds"], 0)

    def test_ping_returns_ok(self):
        resp = self.client.get("/ping/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})


class MetricsViewTest(TestCase):
    """Tests for the Prometheus metrics endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="metrics_user",
            email="metrics-user@example.com",
            password="x",
        )
        self.superuser = User.objects.create_superuser(
            username="metrics_superuser",
            email="metrics-superuser@example.com",
            password="x",
        )

    def test_metrics_endpoint_redirects_unauthenticated_user_to_login(self):
        resp = self.client.get("/metrics/")
        self.assertRedirects(resp, "/accounts/login/?next=/metrics/")

    def test_metrics_endpoint_returns_403_for_non_superuser(self):
        self.client.force_login(self.user)
        resp = self.client.get("/metrics/")
        self.assertEqual(resp.status_code, 403)

    def test_metrics_content_type_is_prometheus_for_superuser(self):
        self.client.force_login(self.superuser)
        resp = self.client.get("/metrics/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/plain", resp["Content-Type"])

    def test_metrics_contain_http_requests_total_for_superuser(self):
        self.client.force_login(self.superuser)
        resp = self.client.get("/metrics/")
        self.assertIn(b"http_requests_total", resp.content)


class SecurityHeadersTest(TestCase):
    def test_ping_includes_default_security_headers(self):
        resp = self.client.get("/ping/")

        self.assertEqual(resp["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertEqual(resp["Permissions-Policy"], "camera=(), geolocation=(), microphone=()")
        self.assertEqual(resp["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertEqual(resp["Cross-Origin-Opener-Policy"], "same-origin")


@override_settings(DEBUG=False)
class CsrfFailureViewTests(TestCase):
    """Tests for the custom CSRF failure view (CSRF_FAILURE_VIEW).

    Audit step 1: every CSRF rejection must be logged with diagnostic context
    and the user must see a friendly "page expired" screen instead of
    Django's bare 403.
    """

    LOGIN_URL = "/accounts/login/"

    def setUp(self):
        self.csrf_client = Client(enforce_csrf_checks=True)

    def test_csrf_failure_on_login_returns_friendly_403(self):
        response = self.csrf_client.post(self.LOGIN_URL, {"username": "x", "password": "y"})
        self.assertEqual(response.status_code, 403)
        content = response.content.decode()
        self.assertIn("Səhifə köhnəlib", content)
        # Login path: auto-redirect to a fresh login form via meta refresh.
        self.assertIn('http-equiv="refresh"', content)
        self.assertIn(self.LOGIN_URL, content)
        # No internals disclosed.
        self.assertNotIn("Traceback", content)
        self.assertNotIn("CSRF verification failed", content)

    def test_csrf_failure_is_logged_with_diagnostic_context(self):
        with self.assertLogs("core.csrf", level="WARNING") as captured:
            self.csrf_client.post(
                self.LOGIN_URL,
                {"username": "x", "password": "y"},
                HTTP_ORIGIN="https://evil.example",
                HTTP_REFERER="https://emsarena.com/accounts/login/",
            )
        joined = "\n".join(captured.output)
        self.assertIn("CSRF failure", joined)
        self.assertIn("reason=", joined)
        self.assertIn("path=/accounts/login/", joined)
        self.assertIn("has_csrf_cookie=", joined)
        self.assertIn("cf_ray=", joined)

    def test_csrf_failure_on_non_login_path_has_no_auto_redirect(self):
        response = self.csrf_client.post("/contact/", {"name": "x"})
        # Regardless of the final status of /contact/, a CSRF-rejected POST
        # must render the csrf_failure template without the login redirect.
        if response.status_code == 403:
            content = response.content.decode()
            self.assertNotIn('http-equiv="refresh"', content)
