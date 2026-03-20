"""
Integration tests – Media Access Control.

Verifies that the protected media view enforces tenant/ownership boundaries
for private files, specifically ``exam_uploads/`` files.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.db.models.signals import post_save
from django.test import RequestFactory, TestCase, override_settings

from apps.exams.domain.attempts import ExamAnswer, ExamAnswerFile, ExamAttempt
from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption
from apps.organizations.models import Membership, Organization, Role
from apps.organizations.signals import create_default_roles
from core.constants import OrganizationType, RoleScopeType
from core.media_views import protected_media

User = get_user_model()


def _make_org(name, slug, owner):
    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        org = Organization.objects.create(
            name=name,
            slug=slug,
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
    finally:
        post_save.connect(create_default_roles, sender=Organization)
    return org


def _make_teacher_role(org):
    return Role.objects.create(
        organization=org,
        name="teacher",
        display_name="Teacher",
        level=60,
        scope_type=RoleScopeType.COURSE,
        permissions=["course.*"],
        is_active=True,
    )


def _assign(user, org, role, *, is_primary=True):
    profile = user.profile
    profile.organization = org
    profile.organization_type = org.org_type
    profile.save(update_fields=["organization", "organization_type", "updated_at"])
    return Membership.objects.create(
        user=user,
        organization=org,
        role=role,
        is_primary=is_primary,
        is_active=True,
    )


class MediaViewCrossTenantExamUploadTest(TestCase):
    """
    A user from a different organization must be denied access to
    ``exam_uploads/`` files belonging to another org's exam.
    """

    def setUp(self):
        self.factory = RequestFactory()

        # Org A owns the exam / submission
        self.owner = User.objects.create_user(
            username="media_owner", email="owner@orga.com", password="testpass123"
        )
        # Intruder belongs to a completely different org
        self.intruder = User.objects.create_user(
            username="media_intruder", email="intruder@orgb.com", password="testpass123"
        )

        self.org_a = _make_org("Media Org A", "media-org-a", self.owner)
        self.org_b = _make_org("Media Org B", "media-org-b", self.intruder)

        role_a = _make_teacher_role(self.org_a)
        role_b = _make_teacher_role(self.org_b)

        _assign(self.owner, self.org_a, role_a)
        _assign(self.intruder, self.org_b, role_b)

        # Create exam owned by Org A
        self.exam = Exam.objects.create(
            title="Protected Exam",
            author=self.owner,
            organization=self.org_a,
            is_active=True,
        )
        self.question = ExamQuestion.objects.create(
            exam=self.exam,
            text="Q1",
            order=1,
            points=10,
        )
        ExamQuestionOption.objects.create(question=self.question, text="Opt A", is_correct=True)

        # Create an attempt + answer + file for the owner
        self.attempt = ExamAttempt.objects.create(
            user=self.owner,
            exam=self.exam,
        )
        self.answer = ExamAnswer.objects.create(
            attempt=self.attempt,
            question=self.question,
        )
        # Register the file path in the DB (file need not exist on disk for access-control tests)
        self.file_path = "exam_uploads/2024/01/owner_submission.pdf"
        self.answer_file = ExamAnswerFile.objects.create(
            answer=self.answer,
            file=self.file_path,
        )

    @override_settings(
        MEDIA_ROOT="/tmp/nonexistent_media_root",
        MEDIA_ACCEL_REDIRECT_URL="/internal_media",
    )
    def test_media_view_denies_cross_tenant_exam_upload(self):
        """
        An authenticated user from Org B must receive 403 when requesting an
        ``exam_uploads/`` file that belongs to Org A's exam attempt.
        """
        request = self.factory.get(f"/media/{self.file_path}")
        request.user = self.intruder

        with self.assertRaises(PermissionDenied):
            protected_media(request, path=self.file_path)

    @override_settings(
        MEDIA_ROOT="/tmp/nonexistent_media_root",
        MEDIA_ACCEL_REDIRECT_URL="/internal_media",
    )
    def test_media_view_allows_owner_access(self):
        """
        The user who submitted the file must be granted access to the same
        ``exam_uploads/`` resource.

        With X-Accel-Redirect configured the view returns a 200 with the
        internal redirect header rather than streaming the file from disk.
        """
        request = self.factory.get(f"/media/{self.file_path}")
        request.user = self.owner

        response = protected_media(request, path=self.file_path)
        self.assertEqual(response.status_code, 200)
        self.assertIn("X-Accel-Redirect", response)

    @override_settings(
        MEDIA_ROOT="/tmp/nonexistent_media_root",
        MEDIA_ACCEL_REDIRECT_URL="/internal_media",
    )
    def test_media_view_denies_unauthenticated_for_private_path(self):
        """
        Unauthenticated requests to private paths must be redirected to login.
        """
        request = self.factory.get(f"/media/{self.file_path}")
        request.user = AnonymousUser()

        response = protected_media(request, path=self.file_path)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"].lower())
