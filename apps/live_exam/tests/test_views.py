"""
View tests for live_exam app.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam
from apps.live_exam.models import LiveSession
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class LiveExamJoinPageTest(TestCase):
    """Test basic live exam join page functionality."""

    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user(
            username="live_teacher",
            email="live_teacher@example.com",
            password="StrongPass123!",
        )
        self.org = Organization.objects.create(
            name="Live Exam Org",
            organization_type=OrganizationType.UNIVERSITY,
        )
        ProfileRole.objects.create(
            profile=self.teacher.profile,
            organization=self.org,
            role="teacher",
        )
        self.exam = Exam.objects.create(
            title="Live Test Exam",
            slug="live-test-exam",
            owner=self.teacher,
            duration_minutes=30,
        )
        self.session = LiveSession.objects.create(
            exam=self.exam,
            pin="TEST123",
            host=self.teacher,
        )

    def test_join_page_accessible_without_login(self):
        """Test that join page is accessible without authentication."""
        url = reverse("liveExam:join_page", kwargs={"pin": self.session.pin})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_join_page_with_invalid_pin(self):
        """Test that invalid PIN returns 404."""
        url = reverse("liveExam:join_page", kwargs={"pin": "INVALID"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class LiveExamHostAccessTest(TestCase):
    """Test host access control for live exam sessions."""

    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user(
            username="host_teacher",
            email="host_teacher@example.com",
            password="StrongPass123!",
        )
        self.other_user = User.objects.create_user(
            username="other_user",
            email="other_user@example.com",
            password="StrongPass123!",
        )
        self.org = Organization.objects.create(
            name="Host Org",
            organization_type=OrganizationType.UNIVERSITY,
        )
        ProfileRole.objects.create(
            profile=self.teacher.profile,
            organization=self.org,
            role="teacher",
        )
        self.exam = Exam.objects.create(
            title="Host Test Exam",
            slug="host-test-exam",
            owner=self.teacher,
            duration_minutes=30,
        )
        self.session = LiveSession.objects.create(
            exam=self.exam,
            pin="HOST123",
            host=self.teacher,
        )

    def test_host_lobby_requires_login(self):
        """Test that host lobby requires authentication."""
        url = reverse("liveExam:host_lobby", kwargs={"pin": self.session.pin})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_host_lobby_accessible_by_host(self):
        """Test that host can access their session lobby."""
        self.client.login(username="host_teacher", password="StrongPass123!")
        url = reverse("liveExam:host_lobby", kwargs={"pin": self.session.pin})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
