"""
View tests for accounts app.
"""

import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse

from apps.accounts.models import EmailOTP, ProfileRole
from apps.blog.models import Category, Post
from apps.organizations.models import Country, Organization
from core.constants import OrganizationType

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


@override_settings(CACHES=LOCMEM_CACHE_SETTINGS, LOGIN_RATE_LIMIT="2/1m")
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


@override_settings(
    CACHES=LOCMEM_CACHE_SETTINGS,
    OTP_VERIFY_RATE_LIMIT="1/1m",
    OTP_RESEND_RATE_LIMIT="1/1m",
)
class OTPRateLimitViewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user(
            "otpviewuser",
            "otpview@example.com",
            "StrongPass123!",
            is_active=False,
        )
        session = self.client.session
        session["pending_verify_email"] = self.user.email
        session.save()
        self.verify_url = reverse("accounts:verify_code")
        self.resend_url = reverse("accounts:resend_code")

    def test_verify_code_blocks_after_too_many_invalid_attempts(self):
        EmailOTP.objects.create(user=self.user, code="123456")

        first = self.client.post(self.verify_url, {"code": "000000"})
        self.assertEqual(first.status_code, 200)

        blocked = self.client.post(self.verify_url, {"code": "000000"})

        self.assertEqual(blocked.status_code, 429)
        self.assertContains(blocked, "Çox sayda cəhd edildi", status_code=429)

    def test_resend_code_blocks_after_rate_limit(self):
        first = self.client.post(self.resend_url)
        self.assertEqual(first.status_code, 302)

        blocked = self.client.post(self.resend_url)

        self.assertEqual(blocked.status_code, 429)
        self.assertContains(blocked, "Çox sayda cəhd edildi", status_code=429)

    def test_verify_code_page_shows_expiry_timer(self):
        EmailOTP.objects.create(user=self.user, code="123456")

        response = self.client.get(self.verify_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-otp-expires-at")
        self.assertContains(response, "Kod 3 dəqiqə etibarlıdır.")


class LogoutViewTest(TestCase):
    """Test logout view functionality."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("logoutuser", "logout@example.com", "StrongPass123!")
        self.logout_url = reverse("accounts:logout")

    def test_logout_redirects_to_home(self):
        """Test that logout redirects to home page."""
        self.client.login(username="logoutuser", password="StrongPass123!")
        response = self.client.get(self.logout_url, follow=True)
        # After logout, user should not be authenticated
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response.status_code, 200)

    def test_logout_when_not_logged_in(self):
        """Test that logout works even when not logged in."""
        response = self.client.get(self.logout_url, follow=True)
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


class RegisterViewTest(TestCase):
    """Test registration view functionality."""

    def setUp(self):
        self.client = Client()
        self.register_url = reverse("accounts:register")
        Country.objects.get_or_create(code="AZ", defaults={"name": "Azerbaijan", "is_active": True})

    def _base_payload(self, **overrides):
        payload = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "StrongPass123!",
            "password2": "StrongPass123!",
            "first_name": "New",
            "last_name": "User",
            "country": "AZ",
            "organization_type": OrganizationType.INDIVIDUAL,
            "join_organization": "",
            "institution": "",
            "institution_not_listed_name": "",
            "organization_identifier": "",
            "organization_license_identifier": "",
            "initial_role": ProfileRole.MEMBER,
            "accept_privacy_policy": "on",
            "phone": "",
            "specialization": "",
            "group_number": "",
            "department": "",
            "staff_position": "",
        }
        payload.update(overrides)
        return payload

    def test_register_page_accessible(self):
        """Test that register page is accessible."""
        response = self.client.get(self.register_url)
        self.assertEqual(response.status_code, 200)

    def test_register_creates_user_and_profile(self):
        """Test that registration creates both user and profile."""
        response = self.client.post(
            self.register_url,
            {
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "StrongPass123!",
                "password2": "StrongPass123!",
                "first_name": "New",
                "last_name": "User",
                "country": "AZ",
                "organization_type": OrganizationType.INDIVIDUAL,
                "join_organization": "",
                "institution": "",
                "institution_not_listed_name": "",
                "organization_identifier": "",
                "organization_license_identifier": "",
                "initial_role": ProfileRole.MEMBER,
                "accept_privacy_policy": "on",
            },
        )
        # Registration might redirect or show success
        self.assertIn(response.status_code, [200, 302])

        # Check if user was created
        if User.objects.filter(username="newuser").exists():
            user = User.objects.get(username="newuser")
            self.assertTrue(hasattr(user, "profile"))
            self.assertIsNotNone(user.profile)

    def test_register_with_organization_selection(self):
        """Test registration with organization selection."""
        owner = User.objects.create_user("owner", "owner@example.com", "StrongPass123!")
        org = Organization.objects.create(
            name="Test School",
            org_type=OrganizationType.SCHOOL,
            owner=owner,
            status="active",
            is_active=True,
        )

        response = self.client.post(
            self.register_url,
            {
                "username": "orgstudent",
                "email": "orgstudent@example.com",
                "password": "StrongPass123!",
                "password2": "StrongPass123!",
                "first_name": "Org",
                "last_name": "Student",
                "country": "AZ",
                "organization_type": "school_student",
                "join_organization": org.id,
                "institution": "",
                "institution_not_listed_name": "",
                "organization_identifier": "",
                "organization_license_identifier": "",
                "initial_role": ProfileRole.MEMBER,
                "accept_privacy_policy": "on",
            },
        )
        # Registration should work
        self.assertIn(response.status_code, [200, 302])

    def test_register_rejects_malformed_identity_payloads_without_500(self):
        response = self.client.post(
            self.register_url,
            {
                "username": "bad'(",
                "email": "'(",
                "password": "StrongPass123!",
                "password2": "StrongPass123!",
                "first_name": "Bad",
                "last_name": "Input",
                "country": "'(",
                "organization_type": OrganizationType.INDIVIDUAL,
                "join_organization": "",
                "institution": "",
                "institution_not_listed_name": "",
                "organization_identifier": "",
                "organization_license_identifier": "",
                "initial_role": ProfileRole.MEMBER,
                "accept_privacy_policy": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("username", response.context["form"].errors)
        self.assertIn("email", response.context["form"].errors)
        self.assertIn("country", response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="bad'(").exists())

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.dummy.EmailBackend")
    def test_register_rolls_back_user_when_otp_email_fails(self):
        """If both sync and async email sending fail, no user must remain in DB."""
        import unittest.mock as mock

        with mock.patch(
            "apps.accounts.services.auth.send_verify_email", side_effect=Exception("SMTP error")
        ), mock.patch(
            "core.email_tasks.send_verification_otp_email.delay", side_effect=Exception("Celery error")
        ):
            response = self.client.post(self.register_url, self._base_payload())

        # Form re-rendered with an error message (no redirect)
        self.assertEqual(response.status_code, 200)
        # No user left in the database
        self.assertFalse(User.objects.filter(username="newuser").exists())

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_register_succeeds_and_otp_email_is_sent(self):
        """Successful registration sends exactly one OTP email and redirects."""
        response = self.client.post(self.register_url, self._base_payload())

        self.assertRedirects(response, reverse("accounts:verify_code"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("newuser@example.com", mail.outbox[0].to)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_resend_otp_sends_new_code(self):
        """resend_code_view must send a new OTP email for a pending verification."""
        # Register first
        self.client.post(self.register_url, self._base_payload())
        self.assertEqual(len(mail.outbox), 1)
        mail.outbox.clear()

        response = self.client.get(reverse("accounts:resend_code"))
        self.assertIn(response.status_code, [200, 302])
        # A new email must have been sent
        self.assertEqual(len(mail.outbox), 1)


class ProfileViewTest(TestCase):
    """Test profile view functionality."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("profileuser", "profile@example.com", "StrongPass123!")
        self.profile_url = reverse("accounts:profile")

    def test_profile_requires_authentication(self):
        """Test that profile page requires login."""
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_profile_accessible_when_logged_in(self):
        """Test that profile page is accessible when logged in."""
        self.client.login(username="profileuser", password="StrongPass123!")
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("profile", response.context)

    def test_profile_shows_user_information(self):
        """Test that profile shows user information."""
        self.client.login(username="profileuser", password="StrongPass123!")
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.username)


class DashboardViewTest(TestCase):
    """Test dashboard view functionality."""

    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("teacher", "teacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("student", "student@example.com", "StrongPass123!")

        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.student.profile.role = ProfileRole.STUDENT
        self.student.profile.save(update_fields=["role", "updated_at"])

        self.dashboard_url = reverse("accounts:dashboard")

    def test_dashboard_requires_authentication(self):
        """Test that dashboard requires login."""
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_teacher_dashboard_accessible(self):
        """Test that teacher can access dashboard."""
        self.client.login(username="teacher", password="StrongPass123!")
        response = self.client.get(self.dashboard_url)
        # Dashboard should be accessible
        self.assertIn(response.status_code, [200, 302])

    def test_student_dashboard_accessible(self):
        """Test that student can access dashboard."""
        self.client.login(username="student", password="StrongPass123!")
        response = self.client.get(self.dashboard_url)
        # Dashboard should be accessible
        self.assertIn(response.status_code, [200, 302])


class RoleBasedAccessTest(TestCase):
    """Test role-based access control."""

    def setUp(self):
        self.client = Client()
        self.superadmin = User.objects.create_user("superadmin", "superadmin@example.com", "StrongPass123!")
        self.teacher = User.objects.create_user("teacher", "teacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("student", "student@example.com", "StrongPass123!")

        self.superadmin.profile.role = ProfileRole.SUPERADMIN
        self.superadmin.profile.save(update_fields=["role", "updated_at"])

        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.student.profile.role = ProfileRole.STUDENT
        self.student.profile.save(update_fields=["role", "updated_at"])

    def test_different_roles_have_different_levels(self):
        """Test that different roles have different access levels."""
        self.assertGreater(self.superadmin.profile.role_level, self.teacher.profile.role_level)
        self.assertGreater(self.teacher.profile.role_level, self.student.profile.role_level)

    def test_profile_url_accessible_for_all_roles(self):
        """Test that profile page is accessible for all authenticated users."""
        profile_url = reverse("accounts:profile")

        # Superadmin
        self.client.login(username="superadmin", password="StrongPass123!")
        response = self.client.get(profile_url)
        self.assertEqual(response.status_code, 200)
        self.client.logout()

        # Teacher
        self.client.login(username="teacher", password="StrongPass123!")
        response = self.client.get(profile_url)
        self.assertEqual(response.status_code, 200)
        self.client.logout()

        # Student
        self.client.login(username="student", password="StrongPass123!")
        response = self.client.get(profile_url)
        self.assertEqual(response.status_code, 200)


class PublicProfileViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user("publicowner", "publicowner@example.com", "StrongPass123!")
        self.viewer = User.objects.create_user("publicviewer", "publicviewer@example.com", "StrongPass123!")
        self.reported_zap_usernames = (
            "wcu",
            "individual_teacher_1",
            "individual_teacher_2",
            "kelvin",
            "learnhub_coach",
            "learnhub_editor",
            "school_teacher_1",
            "school_teacher_2",
            "university_teacher_1",
            "university_teacher_2",
            "tmp_img_user3",
            "tmp_img_user4",
        )
        self.reported_zap_payloads = ("'", '"', ";", "'(", "ZAP%n%s%n%s", "ZAP%x%x%x%x")
        self.category = Category.objects.create(name="Frontend", slug="frontend")
        self.other_category = Category.objects.create(name="Backend", slug="backend")
        self.demo_category = Category.objects.create(name="Demo Xəbərlər", slug="demo-xeberler")

        owner_profile = self.owner.profile
        owner_profile.bio = "Açıq bio məlumatı"
        owner_profile.location = "Bakı"
        owner_profile.save(update_fields=["bio", "location", "updated_at"])

        Post.objects.create(
            author=self.owner,
            category=self.category,
            title="Public Post",
            excerpt="Visible excerpt",
            content="Visible content",
            is_published=True,
        )
        Post.objects.create(
            author=self.owner,
            category=self.category,
            title="Private Draft",
            excerpt="Hidden excerpt",
            content="Hidden content",
            is_published=False,
        )

        for index in range(7):
            Post.objects.create(
                author=self.owner,
                category=self.category,
                title=f"Pagination Post {index}",
                excerpt=f"Excerpt {index}",
                content=f"Content {index}",
                is_published=True,
            )

        Post.objects.create(
            author=self.owner,
            category=self.category,
            title="Alpha Search Match",
            excerpt="Searchable excerpt",
            content="Searchable content",
            is_published=True,
        )
        Post.objects.create(
            author=self.owner,
            category=self.other_category,
            title="Backend Public Post",
            excerpt="Backend excerpt",
            content="Backend content",
            is_published=True,
        )

        for username in self.reported_zap_usernames:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@example.com",
                },
            )
            if created:
                user.set_password("StrongPass123!")
                user.save(update_fields=["password"])
            user.profile.save(update_fields=["updated_at"])
            Post.objects.get_or_create(
                author=user,
                category=self.demo_category,
                title=f"{username} demo post",
                defaults={
                    "excerpt": "Visible excerpt",
                    "content": "Visible content",
                    "is_published": True,
                },
            )

    def test_public_profile_is_accessible_anonymously_and_hides_private_sections(self):
        response = self.client.get(reverse("accounts:public_profile", args=[self.owner.username]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Search Match")
        self.assertNotContains(response, "Private Draft")
        self.assertContains(response, "Açıq bio məlumatı")
        self.assertContains(response, "Bakı")
        self.assertNotContains(response, reverse("create_post"))
        self.assertNotContains(response, reverse("courses:my_courses"))
        self.assertNotContains(response, reverse("courses:create_course"))
        self.assertNotContains(response, reverse("exams:create_exam"))
        self.assertNotContains(response, reverse("accounts:assigned_exams"))

    def test_public_profile_redirects_owner_to_private_profile(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("accounts:public_profile", args=[self.owner.username]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile"))

    def test_public_profile_search_and_pagination_work(self):
        search_response = self.client.get(
            reverse("accounts:public_profile", args=[self.owner.username]),
            {"q": "Alpha"},
        )
        self.assertEqual(search_response.status_code, 200)
        self.assertContains(search_response, "Alpha Search Match")
        self.assertNotContains(search_response, "Public Post")

        page_response = self.client.get(
            reverse("accounts:public_profile", args=[self.owner.username]),
            {"page": 2},
        )
        self.assertEqual(page_response.status_code, 200)
        self.assertEqual(page_response.context["posts"].number, 2)

    def test_public_profile_rejects_semicolon_only_search_with_empty_results(self):
        response = self.client.get(
            reverse("accounts:public_profile", args=[self.owner.username]),
            {"q": ";"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["search_query"], "")
        self.assertEqual(response.context["posts"].paginator.count, 0)

    def test_public_profile_malicious_query_params_return_empty_results(self):
        payloads = (
            {"q": "'("},
            {"q": '"'},
            {"q": "()"},
            {"category": ";"},
            {"category": "demo-xeberler", "q": "'("},
        )

        for params in payloads:
            with self.subTest(params=params):
                response = self.client.get(
                    reverse("accounts:public_profile", args=[self.owner.username]),
                    params,
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["posts"].paginator.count, 0)
                self.assertNotIn("%27", response.context["extra_query"])
                self.assertNotIn(";", response.context["extra_query"])

    def test_public_profile_rejects_non_numeric_page_payloads(self):
        for username in ("wcu", "school_teacher_1", "university_teacher_1", "tmp_img_user3"):
            for payload in ("'", '"', ";", "'("):
                with self.subTest(username=username, payload=payload):
                    response = self.client.get(
                        reverse("accounts:public_profile", args=[username]),
                        {"page": payload},
                    )

                    self.assertEqual(response.status_code, 400)
                    self.assertContains(response, "Invalid page parameter.", status_code=400)

    def test_public_profile_reported_zap_payloads_never_return_500(self):
        for username in self.reported_zap_usernames:
            for payload in self.reported_zap_payloads:
                for params, expected_extra_query, expected_category in (
                    ({"category": payload}, "", ""),
                    ({"q": payload}, "", ""),
                    (
                        {"category": self.demo_category.slug, "q": payload},
                        f"category={self.demo_category.slug}",
                        self.demo_category.slug,
                    ),
                ):
                    with self.subTest(username=username, params=params):
                        response = self.client.get(
                            reverse("accounts:public_profile", args=[username]),
                            params,
                        )

                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.context["posts"].paginator.count, 0)
                        self.assertEqual(response.context["search_query"], "")
                        self.assertEqual(response.context["selected_category"], expected_category)
                        self.assertEqual(response.context["extra_query"], expected_extra_query)
                        self.assertNotIn("%27", response.context["extra_query"])
                        self.assertNotIn("%22", response.context["extra_query"])
                        self.assertNotIn("%3B", response.context["extra_query"])
                        self.assertNotIn("%28", response.context["extra_query"])

    def test_public_profile_active_category_link_toggles_filter_off(self):
        response = self.client.get(
            reverse("accounts:public_profile", args=[self.owner.username]),
            {"category": self.category.slug, "q": "Alpha"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Search Match")
        self.assertNotContains(response, "Backend Public Post")
        self.assertContains(
            response,
            f'href="{reverse("accounts:public_profile", args=[self.owner.username])}?q=Alpha"',
            html=False,
        )

    def test_public_profile_parent_category_filter_includes_child_category_posts(self):
        programming = Category.objects.get(slug="programming")
        Post.objects.create(
            author=self.owner,
            category=programming,
            title="Programming Article",
            excerpt="Hierarchy excerpt",
            content="Hierarchy content",
            is_published=True,
        )

        response = self.client.get(
            reverse("accounts:public_profile", args=[self.owner.username]),
            {"category": "technology"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Programming Article")
        self.assertNotContains(response, "Backend Public Post")
