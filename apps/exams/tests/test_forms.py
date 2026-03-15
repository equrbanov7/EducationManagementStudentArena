from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.exams.forms import ExamForm
from apps.exams.models import Exam
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class ExamFormDefaultStateTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="exam_form_teacher",
            email="exam_form_teacher@example.com",
            password="StrongPass123!",
        )
        self.org = Organization.objects.create(
            name="Exam Form Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

    def test_create_form_marks_is_active_checked_by_default(self):
        form = ExamForm()
        self.assertTrue(form.initial.get("is_active"))

    def test_edit_form_keeps_existing_is_active_value(self):
        exam = Exam.objects.create(
            author=self.teacher,
            title="Draft exam",
            exam_type="test",
            is_active=False,
        )
        form = ExamForm(instance=exam)
        self.assertFalse(bool(form["is_active"].value()))
