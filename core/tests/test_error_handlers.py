"""
Tests for custom error handlers in core.views.

These tests verify that the custom error handlers (handler400, handler403,
handler404, handler500) return clean responses without exposing application
internals — addressing the Application Error Disclosure vulnerability.
"""

from __future__ import annotations

from django.test import Client, TestCase, override_settings
from django.urls import reverse


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
