"""Dalğa 2 (2026-09-14) — audit 2026-09-13 backend F-07: `create_lab` (lab +
icazəli tələbələr + fayl) və `create_question` (sual + əlavə) ``transaction.atomic``
içindədir; view geniş `except` ilə 500 JSON qaytarır, amma yarımçıq sətir qalmır."""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.courses.models import Course
from apps.labs.models import Lab, LabBlock, LabQuestion
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()
PW = "W2AtomicPass123!"


def _assign(user, organization, profile_role, role_name):
    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={"role": organization.roles.get(name=role_name), "is_primary": True, "is_active": True},
    )


class _Base(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("w2lab_teacher", "w2lab_teacher@example.com", PW)
        self.student = User.objects.create_user("w2lab_student", "w2lab_student@example.com", PW)
        self.org = Organization.objects.create(
            name="W2 Lab Org",
            slug="w2-lab-org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign(self.teacher, self.org, ProfileRole.TEACHER, "teacher")
        _assign(self.student, self.org, ProfileRole.STUDENT, "student")
        self.course = Course.objects.create(owner=self.teacher, title="W2 Lab Course", status="published")
        self.client = Client()
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()


class CreateLabAtomicTest(_Base):
    def _post(self):
        now = timezone.now()
        return self.client.post(
            reverse("labs:create_lab", kwargs={"course_id": self.course.id}),
            {
                "title": "W2 Lab",
                "start_datetime": now.strftime("%Y-%m-%dT%H:%M"),
                "end_datetime": (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
                "student_ids[]": [str(self.student.pk)],
            },
        )

    def test_student_set_failure_rolls_back_the_lab(self):
        # M2M `set()` `through` cədvəlinə `bulk_create` ilə yazır — məhz o sınır.
        with mock.patch("django.db.models.query.QuerySet.bulk_create", side_effect=RuntimeError("m2m boom")):
            response = self._post()
        self.assertEqual(response.status_code, 500)
        self.assertFalse(Lab.objects.filter(course=self.course).exists())

    def test_happy_path_writes_lab_and_students(self):
        response = self._post()
        self.assertEqual(response.status_code, 200, response.content[:300])
        lab = Lab.objects.get(course=self.course)
        self.assertEqual(list(lab.allowed_students.values_list("pk", flat=True)), [self.student.pk])


class CreateLabQuestionAtomicTest(_Base):
    def setUp(self):
        super().setUp()
        self.lab = Lab.objects.create(
            course=self.course,
            title="W2 Lab Q",
            start_datetime=timezone.now(),
            end_datetime=timezone.now() + timedelta(days=1),
            max_score=100,
            max_attempts=1,
            status="draft",
            created_by=self.teacher,
            allowed_extensions="txt",
        )
        self.block = LabBlock.objects.create(lab=self.lab, title="Blok", order=1)
        self.url = reverse("labs:create_question", kwargs={"block_id": self.block.id})

    def _post(self):
        return self.client.post(
            self.url,
            {"question_text": "Sual?", "points": "5", "attachment": SimpleUploadedFile("a.txt", b"hello")},
        )

    def test_attachment_save_failure_rolls_back_the_question(self):
        original_save = LabQuestion.save

        def _save(instance, *args, **kwargs):
            if instance.pk is not None:  # ikinci yazı — əlavə faylı ilə yeniləmə
                raise RuntimeError("attachment boom")
            return original_save(instance, *args, **kwargs)

        with mock.patch.object(LabQuestion, "save", _save):
            response = self._post()
        self.assertEqual(response.status_code, 500)
        self.assertFalse(LabQuestion.objects.filter(block=self.block).exists())

    def test_happy_path_writes_question_with_attachment(self):
        response = self._post()
        self.assertEqual(response.status_code, 200, response.content[:300])
        question = LabQuestion.objects.get(block=self.block)
        self.assertTrue(question.attachment)
