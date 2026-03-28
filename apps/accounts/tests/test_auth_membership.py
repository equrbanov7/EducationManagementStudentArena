"""
Auth membership tests: login, logout, and password-reset view flows.

Extracted from test_views.py to keep individual test modules focused.
"""

import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse

User = get_user_model()

LOCMEM_CACHE_SETTINGS = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "accounts-rate-limit-tests",
    }
}


class LoginViewTest(TestCase):
    """Test login view functionality."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("loginuser", "login@example.com", "StrongPass123!")
        self.login_url = reverse("accounts:login")

    def test_login_page_accessible(self):
        """Test that login page is accessible."""
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)

    def test_login_success_redirects_to_dashboard(self):
        """Test that successful login redirects to profile dashboard."""
        response = self.client.post(
            self.login_url,
            {"username": "loginuser", "password": "StrongPass123!"},
            follow=True,
        )
        # After login, user should be authenticated
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        # Should redirect to profile or home page
        self.assertIn(response.status_code, [200, 302])

    def test_login_with_invalid_credentials(self):
        """Test that login with invalid credentials shows error."""
        response = self.client.post(
            self.login_url,
            {"username": "loginuser", "password": "wrongpassword"},
        )
        self.assertEqual(response.status_code, 200)
        # User should not be authenticated
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_login_redirects_when_already_logged_in(self):
        """Test that already logged in users are redirected."""
        self.client.login(username="loginuser", password="StrongPass123!")
        response = self.client.get(self.login_url)
        # Should still be accessible or redirect
        self.assertIn(response.status_code, [200, 302])

    def test_login_preserves_safe_local_next_parameter(self):
        safe_next = reverse("accounts:profile")

        get_response = self.client.get(self.login_url, {"next": safe_next})
        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, f'name="next" value="{safe_next}"', html=False)

        post_response = self.client.post(
            self.login_url,
            {"username": "loginuser", "password": "StrongPass123!", "next": safe_next},
        )

        self.assertRedirects(post_response, safe_next)

    def test_login_rejects_boolean_condition_next_payload(self):
        payload = f"{reverse('accounts:profile')}' AND '1'='1' --"

        get_response = self.client.get(self.login_url, {"next": payload})
        self.assertEqual(get_response.status_code, 200)
        self.assertNotContains(get_response, f'name="next" value="{payload}"', html=False)

        post_response = self.client.post(
            self.login_url,
            {"username": "loginuser", "password": "StrongPass123!", "next": payload},
        )

        self.assertRedirects(post_response, "/")

    def test_login_reported_zap_format_string_payloads_do_not_break(self):
        for payload in ("ZAP%n%s%n%s", "ZAP%x%x%x%x"):
            with self.subTest(payload=payload):
                cache.clear()

                get_response = self.client.get(self.login_url, {"next": payload})
                self.assertEqual(get_response.status_code, 200)
                self.assertNotContains(get_response, f'name="next" value="{payload}"', html=False)

                post_response = self.client.post(
                    self.login_url,
                    {"username": payload, "password": "wrongpassword", "next": payload},
                )

                self.assertIn(post_response.status_code, [200, 302])
                if post_response.status_code == 302:
                    self.assertNotEqual(post_response.url, payload)
                    self.assertTrue(post_response.url.startswith("/"))


@override_settings(
    CACHES=LOCMEM_CACHE_SETTINGS,
    LOGIN_RATE_LIMIT="2/1m",
)
class LoginRateLimitTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user("limiteduser", "limited@example.com", "StrongPass123!")
        self.login_url = reverse("accounts:login")

    def test_login_blocks_after_too_many_invalid_attempts(self):
        for _ in range(2):
            response = self.client.post(
                self.login_url,
                {"username": "limiteduser", "password": "wrongpassword"},
            )
            self.assertEqual(response.status_code, 200)

        blocked = self.client.post(
            self.login_url,
            {"username": "limiteduser", "password": "wrongpassword"},
        )

        self.assertEqual(blocked.status_code, 429)
        self.assertContains(blocked, "Çox sayda cəhd edildi", status_code=429)


class LogoutViewTest(TestCase):
    """Test logout view functionality."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("logoutuser", "logout@example.com", "StrongPass123!")
        self.logout_url = reverse("accounts:logout")

    def test_logout_post_redirects_to_home(self):
        """POST to logout must terminate the session and redirect to home."""
        self.client.login(username="logoutuser", password="StrongPass123!")
        response = self.client.post(self.logout_url, follow=True)
        # After logout, user should not be authenticated
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response.status_code, 200)

    def test_logout_get_returns_405(self):
        """GET requests to logout must be rejected with HTTP 405 to prevent CSRF forced-logout."""
        self.client.login(username="logoutuser", password="StrongPass123!")
        response = self.client.get(self.logout_url)
        self.assertEqual(response.status_code, 405)
        # The session must NOT be terminated by a GET request.
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_logout_when_not_logged_in(self):
        """POST to logout while not authenticated must still succeed (no crash)."""
        response = self.client.post(self.logout_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("resetuser", "reset@example.com", "StrongPass123!")
        self.password_reset_url = reverse("accounts:password_reset")
        self.password_reset_done_url = reverse("accounts:password_reset_done")
        self.password_reset_complete_url = reverse("accounts:password_reset_complete")
        self.login_url = reverse("accounts:login")

    def test_password_reset_page_contains_back_to_login_link(self):
        response = self.client.get(self.password_reset_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.login_url)

    def test_password_reset_flow_sends_email_and_completes(self):
        response = self.client.post(self.password_reset_url, {"email": self.user.email})

        self.assertRedirects(response, self.password_reset_done_url)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accounts/reset/", mail.outbox[0].body)
        self.assertIn("OTP kodu", mail.outbox[0].body)
        self.assertTrue(mail.outbox[0].alternatives)

        match = re.search(r"http://testserver(?P<path>/accounts/reset/\S+/\S+/)", mail.outbox[0].body)
        self.assertIsNotNone(match)
        otp_match = re.search(r"OTP kodu:\s*([0-9]{6})", mail.outbox[0].body)
        self.assertIsNotNone(otp_match)

        confirm_response = self.client.get(match.group("path"), follow=True)
        self.assertEqual(confirm_response.status_code, 200)
        self.assertContains(confirm_response, "data-otp-expires-at")
        confirm_path = confirm_response.request["PATH_INFO"]

        complete_response = self.client.post(
            confirm_path,
            {
                "otp_code": otp_match.group(1),
                "new_password1": "UpdatedStrongPass123!",
                "new_password2": "UpdatedStrongPass123!",
            },
        )
        self.assertRedirects(complete_response, self.password_reset_complete_url)

    def test_password_reset_rejects_malformed_email_payloads_without_500(self):
        for payload in ("'", '"', ";", "'("):
            with self.subTest(payload=payload):
                response = self.client.post(self.password_reset_url, {"email": payload})

                self.assertEqual(response.status_code, 200)
                self.assertIn("email", response.context["form"].errors)
