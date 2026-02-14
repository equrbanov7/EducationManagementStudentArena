"""
Tests for profile and dashboard views.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


class ProfileViewTest(TestCase):
    """Tests for the profile view."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

    def test_profile_requires_login(self):
        """Test that profile page requires authentication."""
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_profile_page_loads(self):
        """Test that profile page loads for authenticated user."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profil")

    def test_profile_creates_userprofile(self):
        """Test that profile view creates UserProfile if missing."""
        from apps.accounts.models import UserProfile

        # Delete any auto-created profile
        UserProfile.objects.filter(user=self.user).delete()

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(UserProfile.objects.filter(user=self.user).exists())

    def test_profile_has_stats(self):
        """Test that profile page includes stats context."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertIn("assigned_exams_count", response.context)
        self.assertIn("assigned_courses_count", response.context)
        self.assertIn("is_teacher", response.context)
        self.assertIn("is_admin", response.context)

    def test_profile_settings_section(self):
        """Test that settings section renders form."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:profile") + "?section=settings")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Yadda Saxla")


class AssignedItemsViewTest(TestCase):
    """Tests for assigned exams and courses views."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

    def test_assigned_exams_requires_login(self):
        """Test that assigned exams page requires authentication."""
        response = self.client.get(reverse("accounts:assigned_exams"))
        self.assertEqual(response.status_code, 302)

    def test_assigned_exams_loads(self):
        """Test that assigned exams page loads."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:assigned_exams"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Təyin olunmuş imtahanlarım")

    def test_assigned_courses_requires_login(self):
        """Test that assigned courses page requires authentication."""
        response = self.client.get(reverse("accounts:assigned_courses"))
        self.assertEqual(response.status_code, 302)

    def test_assigned_courses_loads(self):
        """Test that assigned courses page loads."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:assigned_courses"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Təyin olunmuş kurslarım")


class PendingReviewViewTest(TestCase):
    """Tests for pending review view (teacher-only)."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

    def test_pending_review_requires_login(self):
        """Test that pending review requires authentication."""
        response = self.client.get(reverse("accounts:pending_review"))
        self.assertEqual(response.status_code, 302)

    def test_pending_review_redirects_non_teacher(self):
        """Test that non-teacher users are redirected."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("accounts:pending_review"))
        self.assertEqual(response.status_code, 302)  # Redirect for non-teacher
