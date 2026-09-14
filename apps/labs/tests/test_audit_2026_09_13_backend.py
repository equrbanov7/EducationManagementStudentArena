"""Backend auditi 2026-09-13 — F-10 (lab tələbə endpoint-lərində «200 + success:false»).

``auto_save_answer`` / ``submit_lab`` bağlı lab və tükənmiş cəhd üçün HTTP 200
ilə ``{"success": false}`` qaytarırdı. İndi 409 (vəziyyət konflikti);
``lab_detail.js`` cavabı statusdan asılı olmayaraq ``r.json()`` ilə oxuyub
``data.success``-ə baxır — davranış dəyişmir, status düzəlir.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.courses.models import Course, CourseMembership
from apps.labs.models import Lab, LabAssignment, LabSubmission
from apps.labs.tests.test_views import _assign_user_to_org, _login_with_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class LabFailureStatusTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user("f10_lab_owner", "f10_lab_owner@example.com", "pw")
        self.student = User.objects.create_user("f10_lab_student", "f10_lab_student@example.com", "pw")
        self.organization = Organization.objects.create(
            name="F10 Lab Org", org_type=OrganizationType.SCHOOL, owner=self.owner, status="active", is_active=True
        )
        _assign_user_to_org(self.owner, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)
        self.course = Course.objects.create(owner=self.owner, title="F10 Course", status="published")
        CourseMembership.objects.create(course=self.course, user=self.student, role="student", group_name="A1")
        self.lab = Lab.objects.create(
            course=self.course,
            title="F10 Lab",
            description="x",
            start_datetime=timezone.now() - timedelta(hours=2),
            end_datetime=timezone.now() + timedelta(days=1),
            max_score=100,
            max_attempts=1,
            status="published",
            created_by=self.owner,
        )
        _login_with_org(self.client, self.student, self.organization)

    def _close_lab(self):
        Lab.objects.filter(pk=self.lab.pk).update(end_datetime=timezone.now() - timedelta(hours=1))

    def test_auto_save_on_closed_lab_is_409(self):
        self._close_lab()
        response = self.client.post(reverse("labs:auto_save_answer", kwargs={"pk": self.lab.id}), {})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["success"], False)

    def test_submit_on_closed_lab_without_late_policy_is_409(self):
        self._close_lab()
        response = self.client.post(reverse("labs:submit_lab", kwargs={"pk": self.lab.id}), {})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["success"], False)
        self.assertFalse(LabSubmission.objects.filter(assignment__lab=self.lab).exists())

    def test_submit_with_exhausted_attempts_is_409(self):
        assignment = LabAssignment.get_or_create_for_student(self.lab, self.student)
        LabSubmission.objects.create(assignment=assignment, status="submitted", attempt_number=1)
        response = self.client.post(reverse("labs:submit_lab", kwargs={"pk": self.lab.id}), {})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["success"], False)
        self.assertEqual(LabSubmission.objects.filter(assignment=assignment).count(), 1)
