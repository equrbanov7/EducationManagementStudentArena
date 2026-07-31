"""
Auth membership tests: login, logout, and password-reset view flows.

Extracted from test_views.py to keep individual test modules focused.
"""

import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.accounts.views.auth import AUTH_DEVICE_COOKIE_NAME
from apps.exams.models import Exam
from apps.organizations.models import Membership, Organization, Role
from core.constants import OrganizationType, RoleScopeType

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

    def _grant_exam_manage_access(self, user, organization):
        role, _ = Role.objects.update_or_create(
            organization=organization,
            name=f"teacher-{organization.pk}",
            defaults={
                "display_name": "Teacher",
                "level": 50,
                "scope_type": RoleScopeType.ORGANIZATION,
                "permissions": ["exam.manage"],
                "is_system": False,
                "is_active": True,
            },
        )
        Membership.objects.update_or_create(
            user=user,
            organization=organization,
            defaults={"role": role, "is_active": True, "is_primary": True},
        )

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

    def test_login_preserves_exact_password_whitespace(self):
        password = "  MobileExactPass123!  "
        User.objects.create_user("spacepass", "spacepass@example.com", password)

        response = self.client.post(
            self.login_url,
            {"username": " spacepass@example.com ", "password": password},
            follow=True,
        )

        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response.wsgi_request.user.username, "spacepass")

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

        # The login FORM (with the hidden ``next``) now lives at the role-specific
        # portal URLs; ``/accounts/login/`` itself is the portal chooser.
        get_response = self.client.get(reverse("accounts:staff_login"), {"next": safe_next})
        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, f'name="next" value="{safe_next}"', html=False)

        post_response = self.client.post(
            self.login_url,
            {"username": "loginuser", "password": "StrongPass123!", "next": safe_next},
        )

        self.assertRedirects(post_response, safe_next)

    def test_login_ignores_final_exam_entry_next_parameter(self):
        final_entry = reverse("exams:final_exam_entry")

        get_response = self.client.get(reverse("accounts:staff_login"), {"next": final_entry})
        self.assertEqual(get_response.status_code, 200)
        self.assertNotContains(get_response, f'name="next" value="{final_entry}"', html=False)

        post_response = self.client.post(
            self.login_url,
            {"username": "loginuser", "password": "StrongPass123!", "next": final_entry},
        )

        self.assertRedirects(post_response, settings.LOGIN_REDIRECT_URL, fetch_redirect_response=False)

    def test_login_rejects_boolean_condition_next_payload(self):
        payload = f"{reverse('accounts:profile')}' AND '1'='1' --"

        get_response = self.client.get(self.login_url, {"next": payload})
        self.assertEqual(get_response.status_code, 200)
        self.assertNotContains(get_response, f'name="next" value="{payload}"', html=False)

        post_response = self.client.post(
            self.login_url,
            {"username": "loginuser", "password": "StrongPass123!", "next": payload},
        )

        # An invalid/malicious next falls back to LOGIN_REDIRECT_URL, which for the
        # e-university cabinet is the profile page (a safe internal destination).
        self.assertRedirects(post_response, settings.LOGIN_REDIRECT_URL, fetch_redirect_response=False)

    def test_login_redirects_home_when_safe_next_would_404(self):
        response = self.client.post(
            self.login_url,
            {"username": "loginuser", "password": "StrongPass123!", "next": "/definitely-missing-after-login/"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], reverse("home"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_login_redirects_home_when_next_points_to_inaccessible_exam(self):
        owner = User.objects.create_user("examowner", "examowner@example.com", "StrongPass123!")
        owner.profile.role = ProfileRole.TEACHER
        owner.profile.save(update_fields=["role", "updated_at"])

        self.user.profile.role = ProfileRole.TEACHER
        self.user.profile.save(update_fields=["role", "updated_at"])

        owner_org = Organization.objects.create(
            name="Owner Org",
            org_type=OrganizationType.SCHOOL,
            owner=owner,
            status="active",
            is_active=True,
        )
        login_org = Organization.objects.create(
            name="Login Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.user,
            status="active",
            is_active=True,
        )

        owner.profile.organization = owner_org
        owner.profile.organization_type = owner_org.org_type
        owner.profile.save(update_fields=["organization", "organization_type", "updated_at"])
        self.user.profile.organization = login_org
        self.user.profile.organization_type = login_org.org_type
        self.user.profile.save(update_fields=["organization", "organization_type", "updated_at"])

        self._grant_exam_manage_access(owner, owner_org)
        self._grant_exam_manage_access(self.user, login_org)

        protected_exam = Exam.objects.create(
            title="Protected Exam",
            slug="protected-exam",
            author=owner,
            organization=owner_org,
            is_active=True,
        )

        response = self.client.post(
            self.login_url,
            {
                "username": "loginuser",
                "password": "StrongPass123!",
                "next": reverse("exams:teacher_exam_detail", args=[protected_exam.slug]),
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], reverse("home"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

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
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    LOGIN_RATE_LIMIT="2/1m",
    # İP qatı qəsdən daha genişdir (kampus NAT-ı) — testdə də bu nisbət saxlanılır.
    LOGIN_IP_RATE_LIMIT="10/1m",
)
class LoginRateLimitTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user("limiteduser", "limited@example.com", "StrongPass123!")
        self.superadmin = User.objects.create_superuser(
            "limitedsuperadmin",
            "limitedsuperadmin@example.com",
            "StrongPass123!",
        )
        self.login_url = reverse("accounts:login")
        self.password_reset_url = reverse("accounts:password_reset")
        self.password_reset_done_url = reverse("accounts:password_reset_done")

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

    def test_login_page_sets_auth_device_cookie(self):
        response = self.client.get(self.login_url)

        self.assertEqual(response.status_code, 200)
        self.assertIn(AUTH_DEVICE_COOKIE_NAME, response.cookies)
        self.assertTrue(response.cookies[AUTH_DEVICE_COOKIE_NAME]["httponly"])
        self.assertEqual(response.cookies[AUTH_DEVICE_COOKIE_NAME]["samesite"], "Lax")

    def test_login_rate_limit_isolated_by_device_cookie_on_same_ip(self):
        shared_ip = "198.51.100.10"
        noisy_client = Client()
        peer_client = Client()

        for _ in range(2):
            response = noisy_client.post(
                self.login_url,
                {"username": "limiteduser", "password": "wrongpassword"},
                REMOTE_ADDR=shared_ip,
            )
            self.assertEqual(response.status_code, 200)

        blocked = noisy_client.post(
            self.login_url,
            {"username": "limiteduser", "password": "wrongpassword"},
            REMOTE_ADDR=shared_ip,
        )
        self.assertEqual(blocked.status_code, 429)

        peer_response = peer_client.post(
            self.login_url,
            {"username": "limiteduser", "password": "StrongPass123!"},
            REMOTE_ADDR=shared_ip,
        )
        self.assertEqual(peer_response.status_code, 302)
        self.assertTrue(peer_response.wsgi_request.user.is_authenticated)

    def test_cookieless_client_cannot_bypass_login_throttle(self):
        """P0 reqressiya: cookie GÖNDƏRMƏYƏN klient limitə düşməlidir.

        Əvvəl hər iki vedrə yalnız cihaz cookie-si üzərində qurulurdu; cookie
        yoxdursa `_get_auth_device_id` hər sorğuda TƏZƏ id yaradırdı, yəni hər
        cəhd öz vedrəsinə düşür və limit heç vaxt işə düşmürdü (brute-force
        tam açıq). İndi İP qatı bunu bağlayır.
        """
        attacker_ip = "203.0.113.77"
        statuses = []
        for _ in range(12):
            # Hər cəhd üçün TƏMİZ klient = cookie saxlanılmır (real hücum modeli).
            fresh_client = Client()
            response = fresh_client.post(
                self.login_url,
                {"username": "limiteduser", "password": "wrongpassword"},
                REMOTE_ADDR=attacker_ip,
            )
            statuses.append(response.status_code)

        self.assertIn(429, statuses, "cookie-siz klient heç vaxt bloklanmadı — throttle keçilir")

    def test_ip_throttle_does_not_block_legitimate_shared_ip_login(self):
        """Kampus NAT-ı: eyni İP-dən bir neçə səhv cəhd düzgün girişi bloklamamalıdır."""
        shared_ip = "198.51.100.44"
        noisy = Client()
        for _ in range(3):
            noisy.post(
                self.login_url,
                {"username": "limiteduser", "password": "wrongpassword"},
                REMOTE_ADDR=shared_ip,
            )

        peer = Client()
        response = peer.post(
            self.login_url,
            {"username": "limiteduser", "password": "StrongPass123!"},
            REMOTE_ADDR=shared_ip,
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_superadmin_correct_login_clears_limit_and_allows_access(self):
        for _ in range(2):
            response = self.client.post(
                self.login_url,
                {"username": "limitedsuperadmin", "password": "wrongpassword"},
            )
            self.assertEqual(response.status_code, 200)

        success = self.client.post(
            self.login_url,
            {"username": "limitedsuperadmin", "password": "StrongPass123!"},
        )

        self.assertEqual(success.status_code, 302)
        self.assertTrue(success.wsgi_request.user.is_authenticated)

        self.client.logout()
        retry = self.client.post(
            self.login_url,
            {"username": "limitedsuperadmin", "password": "wrongpassword"},
        )
        self.assertEqual(retry.status_code, 200)

    def test_successful_password_reset_clears_login_rate_limit_wait(self):
        for _ in range(2):
            response = self.client.post(
                self.login_url,
                {"username": "limiteduser", "password": "wrongpassword"},
            )
            self.assertEqual(response.status_code, 200)

        blocked = self.client.post(
            self.login_url,
            {"username": "limiteduser", "password": "StrongPass123!"},
        )
        self.assertEqual(blocked.status_code, 429)

        self.client.post(self.password_reset_url, {"email": self.user.email})
        otp_match = re.search(r"OTP kodu:\s*([0-9]{6})", mail.outbox[-1].body)
        self.assertIsNotNone(otp_match)

        reset_response = self.client.post(
            self.password_reset_done_url,
            {
                "otp_code": otp_match.group(1),
                "new_password1": "ResetStrongPass123!",
                "new_password2": "ResetStrongPass123!",
            },
        )
        self.assertEqual(reset_response.status_code, 302)

        login_after_reset = self.client.post(
            self.login_url,
            {"username": "limiteduser", "password": "ResetStrongPass123!"},
        )
        self.assertEqual(login_after_reset.status_code, 302)
        self.assertTrue(login_after_reset.wsgi_request.user.is_authenticated)


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

        confirm_response = self.client.get(self.password_reset_done_url)
        self.assertEqual(confirm_response.status_code, 200)
        self.assertContains(confirm_response, "data-otp-expires-at")
        self.assertContains(confirm_response, 'name="otp_code"')
        self.assertContains(confirm_response, 'name="new_password1"')
        self.assertContains(confirm_response, 'name="new_password2"')

        complete_response = self.client.post(
            self.password_reset_done_url,
            {
                "otp_code": otp_match.group(1),
                "new_password1": "UpdatedStrongPass123!",
                "new_password2": "UpdatedStrongPass123!",
            },
        )
        self.assertRedirects(complete_response, self.password_reset_complete_url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("UpdatedStrongPass123!"))

    def test_password_reset_unknown_email_does_not_send_otp(self):
        response = self.client.post(self.password_reset_url, {"email": "missing@example.com"})

        self.assertRedirects(response, self.password_reset_done_url)
        self.assertEqual(len(mail.outbox), 0)

        done_response = self.client.get(self.password_reset_done_url)
        self.assertEqual(done_response.status_code, 200)
        self.assertContains(done_response, 'name="email"', html=False)

    def test_password_reset_completes_for_user_without_organization_membership(self):
        self.assertIsNone(self.user.profile.organization)
        self.assertFalse(self.user.memberships.exists())

        self.client.post(self.password_reset_url, {"email": self.user.email})
        otp_match = re.search(r"OTP kodu:\s*([0-9]{6})", mail.outbox[0].body)
        self.assertIsNotNone(otp_match)

        response = self.client.post(
            self.password_reset_done_url,
            {
                "otp_code": otp_match.group(1),
                "new_password1": "AnotherStrongPass123!",
                "new_password2": "AnotherStrongPass123!",
            },
        )

        self.assertRedirects(response, self.password_reset_complete_url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("AnotherStrongPass123!"))

    def test_password_reset_rejects_malformed_email_payloads_without_500(self):
        for payload in ("'", '"', ";", "'("):
            with self.subTest(payload=payload):
                response = self.client.post(self.password_reset_url, {"email": payload})

                self.assertEqual(response.status_code, 200)
                self.assertIn("email", response.context["form"].errors)
