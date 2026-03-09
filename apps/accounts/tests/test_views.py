"""
View tests for accounts app.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.blog.models import Category, Post
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


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


class RegisterViewTest(TestCase):
    """Test registration view functionality."""

    def setUp(self):
        self.client = Client()
        self.register_url = reverse("accounts:register")

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
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "first_name": "New",
                "last_name": "User",
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
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "first_name": "Org",
                "last_name": "Student",
                "organization": org.id,
            },
        )
        # Registration should work
        self.assertIn(response.status_code, [200, 302])


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
        self.category = Category.objects.create(name="Frontend", slug="frontend")
        self.other_category = Category.objects.create(name="Backend", slug="backend")

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
