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
        self.owner = User.objects.create_user(username="media_owner", email="owner@orga.com", password="testpass123")
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


class QuestionMediaProtectionIntegrationTest(TestCase):
    """
    Integration tests for the ``question_media/`` hardening.

    Verifies that question media (images, videos attached to exam questions)
    is no longer publicly accessible and enforces org-membership checks.
    """

    def setUp(self):
        import os
        import tempfile

        from apps.exams.models import Exam, ExamQuestion
        from apps.organizations.models import Membership, Organization
        from core.constants import OrganizationType

        self.factory = RequestFactory()
        self.media_tmp = tempfile.mkdtemp()

        # Users
        self.member = User.objects.create_user(
            username="qm_int_member",
            email="qm_int_member@example.com",
            password="TestPass123!",
        )
        self.stranger = User.objects.create_user(
            username="qm_int_stranger",
            email="qm_int_stranger@example.com",
            password="TestPass123!",
        )
        self.superadmin = User.objects.create_superuser(
            username="qm_int_super",
            email="qm_int_super@example.com",
            password="TestPass123!",
        )

        # Organization + exam
        self.org = Organization.objects.create(
            name="QM Integration Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.member,
            status="active",
            is_active=True,
        )
        student_role = self.org.roles.get(name="student")
        Membership.objects.create(
            user=self.member,
            organization=self.org,
            role=student_role,
            is_primary=True,
            is_active=True,
        )

        self.exam = Exam.objects.create(
            title="QM Integration Exam",
            author=self.member,
            organization=self.org,
            is_active=True,
        )
        self.question = ExamQuestion.objects.create(
            exam=self.exam,
            text="Sample question?",
            order=1,
            points=5,
        )

        # Physical file
        self.file_path = f"question_media/exam_{self.exam.pk}/q_{self.question.pk}/sample.jpg"
        # Yol yalnız DB qeydi ilə uyğun gələndə açılır: checker path-i konkret
        # sualın media sahəsi ilə tutuşdurur (bax `_check_question_media_access`).
        self.question.image = self.file_path
        self.question.save(update_fields=["image"])
        file_dir = os.path.join(
            self.media_tmp,
            "question_media",
            f"exam_{self.exam.pk}",
            f"q_{self.question.pk}",
        )
        os.makedirs(file_dir, exist_ok=True)
        with open(os.path.join(file_dir, "sample.jpg"), "wb") as f:
            f.write(b"\xff\xd8\xff\xe0")

    @override_settings(
        MEDIA_ACCEL_REDIRECT_URL="/internal_media",
    )
    def test_unauthenticated_cannot_access_question_media(self):
        """Unauthenticated access to question_media/ must be redirected to login."""
        request = self.factory.get(f"/media/{self.file_path}")
        request.user = AnonymousUser()

        response = protected_media(request, path=self.file_path)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"].lower())

    @override_settings(
        MEDIA_ACCEL_REDIRECT_URL="/internal_media",
    )
    def test_org_member_can_access_question_media(self):
        """İmtahan müəllifi öz sualının mediasını ala bilir (X-Accel yolu).

        Sırf org üzvlüyü artıq kifayət deyil — tələbə üçün çatdırılmış
        ``ExamAnswer`` tələb olunur (bax `core/tests/test_media_views.py`).
        """
        request = self.factory.get(f"/media/{self.file_path}")
        request.user = self.member

        response = protected_media(request, path=self.file_path)
        self.assertEqual(response.status_code, 200)
        self.assertIn("X-Accel-Redirect", response)

    @override_settings(
        MEDIA_ACCEL_REDIRECT_URL="/internal_media",
    )
    def test_cross_org_user_denied_question_media(self):
        """A user with no org membership is denied access to question media."""
        from django.core.exceptions import PermissionDenied

        request = self.factory.get(f"/media/{self.file_path}")
        request.user = self.stranger

        with self.assertRaises(PermissionDenied):
            protected_media(request, path=self.file_path)

    @override_settings(
        MEDIA_ACCEL_REDIRECT_URL="/internal_media",
    )
    def test_superadmin_can_access_question_media(self):
        """Superadmin can access any question media regardless of org membership."""
        request = self.factory.get(f"/media/{self.file_path}")
        request.user = self.superadmin

        response = protected_media(request, path=self.file_path)
        self.assertEqual(response.status_code, 200)
        self.assertIn("X-Accel-Redirect", response)
