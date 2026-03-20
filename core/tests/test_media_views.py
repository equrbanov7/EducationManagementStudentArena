"""
Tests for core.media_views – protected media serving.
"""

from __future__ import annotations

import os
import tempfile

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import Client, TestCase, override_settings

User = get_user_model()


class ProtectedMediaViewTest(TestCase):
    """
    Verify that private media files redirect unauthenticated users and that
    public files are freely accessible.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="media_test_user",
            email="media@example.com",
            password="StrongPass123!",
        )
        self.superuser = User.objects.create_superuser(
            username="media_superuser",
            email="media_super@example.com",
            password="StrongPass123!",
        )
        # Create a temporary directory to act as MEDIA_ROOT for tests
        self.media_tmp = tempfile.mkdtemp()

        # Create sample files in both public and private sub-directories
        for subdir in ("post_images", "projects/submissions", "labs/submissions", "avatars"):
            path = os.path.join(self.media_tmp, subdir)
            os.makedirs(path, exist_ok=True)
            with open(os.path.join(path, "sample.txt"), "w") as f:
                f.write("test content")

    def test_private_file_redirects_unauthenticated_user(self):
        """Private files (projects/submissions/) must redirect unauthenticated users to login."""
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        from core.media_views import protected_media

        factory = RequestFactory()
        request = factory.get("/media/projects/submissions/sample.txt")
        request.user = AnonymousUser()

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            SERVE_MEDIA=True,
            DEBUG=False,
            MEDIA_ACCEL_REDIRECT_URL="",
        ):
            response = protected_media(request, path="projects/submissions/sample.txt")
            # Should redirect to login (302)
            self.assertEqual(response.status_code, 302)
            self.assertIn("login", response["Location"].lower())

    def test_private_file_forbidden_for_authenticated_user_without_ownership(self):
        """Authenticated user with no file ownership or org membership gets 403."""
        from django.test import RequestFactory

        from core.media_views import protected_media

        factory = RequestFactory()
        request = factory.get("/media/projects/submissions/sample.txt")
        request.user = self.user  # regular user, no ownership record in DB

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            SERVE_MEDIA=True,
            DEBUG=False,
            MEDIA_ACCEL_REDIRECT_URL="",
        ):
            with self.assertRaises(PermissionDenied):
                protected_media(request, path="projects/submissions/sample.txt")

    def test_private_file_accessible_to_superuser(self):
        """Superusers can access any private media file regardless of ownership."""
        from django.test import RequestFactory

        from core.media_views import protected_media

        factory = RequestFactory()
        request = factory.get("/media/projects/submissions/sample.txt")
        request.user = self.superuser

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            SERVE_MEDIA=True,
            DEBUG=False,
            MEDIA_ACCEL_REDIRECT_URL="",
        ):
            response = protected_media(request, path="projects/submissions/sample.txt")
            self.assertEqual(response.status_code, 200)

    def test_labs_submission_redirects_unauthenticated(self):
        """Labs submission files must not be publicly accessible."""
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        from core.media_views import protected_media

        factory = RequestFactory()
        request = factory.get("/media/labs/submissions/sample.txt")
        request.user = AnonymousUser()

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            SERVE_MEDIA=True,
            DEBUG=False,
            MEDIA_ACCEL_REDIRECT_URL="",
        ):
            response = protected_media(request, path="labs/submissions/sample.txt")
            self.assertEqual(response.status_code, 302)
            self.assertIn("login", response["Location"].lower())

    def test_path_traversal_returns_404(self):
        """Path traversal attempts must be rejected."""
        from django.core.exceptions import SuspiciousFileOperation
        from django.http import Http404
        from django.test import RequestFactory

        from core.media_views import protected_media

        factory = RequestFactory()
        request = factory.get("/media/../../etc/passwd")
        request.user = self.superuser  # superuser to bypass auth; path check comes first

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            SERVE_MEDIA=True,
            DEBUG=False,
            MEDIA_ACCEL_REDIRECT_URL="",
        ):
            with self.assertRaises((Http404, SuspiciousFileOperation)):
                protected_media(request, path="../../etc/passwd")

    def test_is_private_helper(self):
        """Verify that _is_private correctly classifies known paths."""
        from core.media_views import _is_private

        self.assertTrue(_is_private("projects/submissions/file.pdf"))
        self.assertTrue(_is_private("exam_uploads/answer.pdf"))
        self.assertTrue(_is_private("exam_paints/draw.png"))
        self.assertTrue(_is_private("labs/teacher_files/notes.pdf"))
        self.assertTrue(_is_private("labs/submissions/sub.zip"))
        self.assertTrue(_is_private("avatars/photo.png"))
        self.assertTrue(_is_private("course_resources/lecture.pdf"))

        self.assertFalse(_is_private("post_images/cover.jpg"))
        self.assertFalse(_is_private("course_covers/cover.png"))
        self.assertTrue(_is_private("question_media/exam_1/q_1/image.jpg"))

    def test_public_file_accessible_without_login(self):
        """Blog post images (post_images/) must be accessible without authentication."""
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        from core.media_views import protected_media

        factory = RequestFactory()
        request = factory.get("/media/post_images/sample.txt")
        request.user = AnonymousUser()

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            SERVE_MEDIA=True,
            DEBUG=False,
            MEDIA_ACCEL_REDIRECT_URL="",
        ):
            response = protected_media(request, path="post_images/sample.txt")
            self.assertEqual(response.status_code, 200)

    def test_x_accel_redirect_header_set_for_private_file(self):
        """When MEDIA_ACCEL_REDIRECT_URL is set, response uses X-Accel-Redirect (superuser)."""
        from django.test import RequestFactory

        from core.media_views import protected_media

        factory = RequestFactory()
        request = factory.get("/media/projects/submissions/sample.txt")
        request.user = self.superuser  # superuser bypasses ownership check

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            MEDIA_ACCEL_REDIRECT_URL="/internal_media",
            DEBUG=False,
        ):
            response = protected_media(request, path="projects/submissions/sample.txt")
            self.assertEqual(response.status_code, 200)
            self.assertIn("X-Accel-Redirect", response)
            self.assertTrue(response["X-Accel-Redirect"].startswith("/internal_media/"))
            self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_serve_media_false_does_not_expose_media_in_production(self):
        """SERVE_MEDIA=False in production means no Django-based media serving."""
        import sys

        from django.urls import clear_url_caches

        # Force URL module re-import so the test is not affected by previous
        # tests that temporarily set SERVE_MEDIA=True (which causes the URL to
        # be registered in sys.modules["config.urls"].urlpatterns).
        sys.modules.pop("config.urls", None)
        clear_url_caches()

        # When SERVE_MEDIA is False (the production default), the /media/ URL
        # pattern is not registered at all, so requests return 404.
        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            SERVE_MEDIA=False,
            DEBUG=False,
        ):
            response = self.client.get("/media/projects/submissions/sample.txt")
            self.assertEqual(response.status_code, 404)

        # Restore URL module for subsequent tests
        sys.modules.pop("config.urls", None)
        clear_url_caches()


class ProtectedMediaOwnershipTest(TestCase):
    """
    Verify that private media access is tenant-aware and owner-aware.

    Tests cover:
    * File owner may access their own submission.
    * Teacher-level org member may access files in their org.
    * Cross-org access is denied.
    * Unauthenticated access is always redirected.
    """

    def setUp(self):
        from apps.courses.models import Course
        from apps.organizations.models import Membership, Organization
        from apps.projects.models import Project, ProjectSubmission
        from core.constants import OrganizationType

        self.media_tmp = tempfile.mkdtemp()

        # Create two users
        self.student = User.objects.create_user(
            username="media_owner_student",
            email="media_owner_student@example.com",
            password="StrongPass123!",
        )
        self.teacher = User.objects.create_user(
            username="media_owner_teacher",
            email="media_owner_teacher@example.com",
            password="StrongPass123!",
        )
        self.other_user = User.objects.create_user(
            username="media_other_user",
            email="media_other@example.com",
            password="StrongPass123!",
        )

        # Create organization A (where the file belongs)
        self.org_a = Organization.objects.create(
            name="Media Test Org A",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )

        # Create organization B (for cross-org denial tests)
        self.org_b = Organization.objects.create(
            name="Media Test Org B",
            org_type=OrganizationType.SCHOOL,
            owner=self.other_user,
            status="active",
            is_active=True,
        )

        # Assign teacher to org A with teacher role
        teacher_role_a = self.org_a.roles.get(name="teacher")
        Membership.objects.create(
            user=self.teacher,
            organization=self.org_a,
            role=teacher_role_a,
            is_primary=True,
            is_active=True,
        )

        # Assign student to org A with student role
        student_role_a = self.org_a.roles.get(name="student")
        Membership.objects.create(
            user=self.student,
            organization=self.org_a,
            role=student_role_a,
            is_primary=True,
            is_active=True,
        )

        # Assign other_user only to org B (so they have no access to org A resources)
        teacher_role_b = self.org_b.roles.get(name="teacher")
        Membership.objects.create(
            user=self.other_user,
            organization=self.org_b,
            role=teacher_role_b,
            is_primary=True,
            is_active=True,
        )

        # Create course and project in org A
        self.course = Course.objects.create(
            owner=self.teacher,
            title="Media Test Course",
            status="published",
            organization=self.org_a,
        )
        self.project = Project.objects.create(
            course=self.course,
            title="Media Test Project",
            description="For media access tests",
            start_date="2024-01-01 00:00:00+00:00",
            deadline="2099-01-01 00:00:00+00:00",
            status="active",
        )

        # Create a submission from the student
        self.file_path = "projects/submissions/media_test_file.pdf"
        self.submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.student,
            content="Test submission content",
            file=self.file_path,
        )

        # Create the physical file in the temporary media directory
        file_dir = os.path.join(self.media_tmp, "projects", "submissions")
        os.makedirs(file_dir, exist_ok=True)
        with open(os.path.join(file_dir, "media_test_file.pdf"), "w") as f:
            f.write("test content")

    def _make_request(self, user, path):
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get(f"/media/{path}")
        request.user = user
        return request

    def test_file_owner_can_access_own_submission(self):
        """The student who submitted a file can access it."""
        from core.media_views import protected_media

        request = self._make_request(self.student, self.file_path)

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            SERVE_MEDIA=True,
            DEBUG=False,
            MEDIA_ACCEL_REDIRECT_URL="",
        ):
            response = protected_media(request, path=self.file_path)
            self.assertEqual(response.status_code, 200)

    def test_teacher_in_same_org_can_access_submission(self):
        """A teacher-level member of the same org can access submissions in their org."""
        from core.media_views import protected_media

        request = self._make_request(self.teacher, self.file_path)

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            SERVE_MEDIA=True,
            DEBUG=False,
            MEDIA_ACCEL_REDIRECT_URL="",
        ):
            response = protected_media(request, path=self.file_path)
            self.assertEqual(response.status_code, 200)

    def test_cross_org_user_cannot_access_submission(self):
        """A user from a different org cannot access another org's submission files."""
        from core.media_views import protected_media

        request = self._make_request(self.other_user, self.file_path)

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            SERVE_MEDIA=True,
            DEBUG=False,
            MEDIA_ACCEL_REDIRECT_URL="",
        ):
            with self.assertRaises(PermissionDenied):
                protected_media(request, path=self.file_path)

    def test_unauthenticated_user_redirected_to_login(self):
        """Unauthenticated users are always redirected to login for private files."""
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        from core.media_views import protected_media

        factory = RequestFactory()
        request = factory.get(f"/media/{self.file_path}")
        request.user = AnonymousUser()

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            SERVE_MEDIA=True,
            DEBUG=False,
            MEDIA_ACCEL_REDIRECT_URL="",
        ):
            response = protected_media(request, path=self.file_path)
            self.assertEqual(response.status_code, 302)
            self.assertIn("login", response["Location"].lower())

    def test_file_not_in_db_returns_403(self):
        """Files that cannot be matched to a DB record are denied (deny-by-default)."""
        from core.media_views import protected_media

        # This path doesn't exist in the database
        unknown_path = "projects/submissions/unknown_file_not_in_db.pdf"

        # Create the physical file
        file_dir = os.path.join(self.media_tmp, "projects", "submissions")
        os.makedirs(file_dir, exist_ok=True)
        with open(os.path.join(file_dir, "unknown_file_not_in_db.pdf"), "w") as f:
            f.write("orphan file")

        request = self._make_request(self.teacher, unknown_path)

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            SERVE_MEDIA=True,
            DEBUG=False,
            MEDIA_ACCEL_REDIRECT_URL="",
        ):
            with self.assertRaises(PermissionDenied):
                protected_media(request, path=unknown_path)


class QuestionMediaAccessTest(TestCase):
    """
    Verify that ``question_media/`` files are now treated as private.

    Tests cover:
    * Unauthenticated users are redirected to login.
    * An authenticated org member (student level) can access question media.
    * A cross-org user is denied access.
    * A path with a non-existent exam ID is denied (fail-closed).
    """

    def setUp(self):
        from apps.exams.models import Exam, ExamQuestion
        from apps.organizations.models import Membership, Organization
        from core.constants import OrganizationType

        self.media_tmp = tempfile.mkdtemp()

        self.student = User.objects.create_user(
            username="qm_student",
            email="qm_student@example.com",
            password="StrongPass123!",
        )
        self.other_user = User.objects.create_user(
            username="qm_other",
            email="qm_other@example.com",
            password="StrongPass123!",
        )
        self.superuser = User.objects.create_superuser(
            username="qm_superuser",
            email="qm_super@example.com",
            password="StrongPass123!",
        )

        # Create org and enroll student
        self.org = Organization.objects.create(
            name="QM Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.student,
            status="active",
            is_active=True,
        )
        student_role = self.org.roles.get(name="student")
        Membership.objects.create(
            user=self.student,
            organization=self.org,
            role=student_role,
            is_primary=True,
            is_active=True,
        )

        # Create exam in org
        self.exam = Exam.objects.create(
            title="QM Test Exam",
            author=self.student,
            organization=self.org,
            is_active=True,
        )
        self.question = ExamQuestion.objects.create(
            exam=self.exam,
            text="What is 2+2?",
            order=1,
            points=1,
        )

        self.file_path = f"question_media/exam_{self.exam.pk}/q_{self.question.pk}/img.jpg"

        # Create the physical file
        file_dir = os.path.join(
            self.media_tmp, "question_media", f"exam_{self.exam.pk}", f"q_{self.question.pk}"
        )
        os.makedirs(file_dir, exist_ok=True)
        with open(os.path.join(file_dir, "img.jpg"), "wb") as f:
            f.write(b"\xff\xd8\xff\xe0")

    def _make_request(self, user, path):
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get(f"/media/{path}")
        request.user = user
        return request

    def test_question_media_is_now_private(self):
        """_is_private must return True for question_media/ paths."""
        from core.media_views import _is_private

        self.assertTrue(_is_private(self.file_path))

    def test_unauthenticated_redirected_for_question_media(self):
        """Unauthenticated users are redirected to login for question_media files."""
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        from core.media_views import protected_media

        factory = RequestFactory()
        request = factory.get(f"/media/{self.file_path}")
        request.user = AnonymousUser()

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            SERVE_MEDIA=True,
            DEBUG=False,
            MEDIA_ACCEL_REDIRECT_URL="",
        ):
            response = protected_media(request, path=self.file_path)
            self.assertEqual(response.status_code, 302)
            self.assertIn("login", response["Location"].lower())

    def test_org_member_can_access_question_media(self):
        """An authenticated member of the exam's org can access question media."""
        from core.media_views import protected_media

        request = self._make_request(self.student, self.file_path)

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            SERVE_MEDIA=True,
            DEBUG=False,
            MEDIA_ACCEL_REDIRECT_URL="",
        ):
            response = protected_media(request, path=self.file_path)
            self.assertEqual(response.status_code, 200)

    def test_cross_org_user_denied_question_media(self):
        """A user with no membership in the exam's org is denied access."""
        from core.media_views import protected_media

        request = self._make_request(self.other_user, self.file_path)

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            SERVE_MEDIA=True,
            DEBUG=False,
            MEDIA_ACCEL_REDIRECT_URL="",
        ):
            with self.assertRaises(PermissionDenied):
                protected_media(request, path=self.file_path)

    def test_superuser_can_access_question_media(self):
        """Superusers bypass ownership checks and can access any question media."""
        from core.media_views import protected_media

        request = self._make_request(self.superuser, self.file_path)

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            SERVE_MEDIA=True,
            DEBUG=False,
            MEDIA_ACCEL_REDIRECT_URL="",
        ):
            response = protected_media(request, path=self.file_path)
            self.assertEqual(response.status_code, 200)

    def test_nonexistent_exam_id_denied(self):
        """A question_media path with a non-existent exam ID is denied (fail-closed)."""
        from core.media_views import protected_media

        bad_path = "question_media/exam_999999/q_1/img.jpg"
        file_dir = os.path.join(self.media_tmp, "question_media", "exam_999999", "q_1")
        os.makedirs(file_dir, exist_ok=True)
        with open(os.path.join(file_dir, "img.jpg"), "wb") as f:
            f.write(b"\xff\xd8\xff\xe0")

        request = self._make_request(self.student, bad_path)

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            SERVE_MEDIA=True,
            DEBUG=False,
            MEDIA_ACCEL_REDIRECT_URL="",
        ):
            with self.assertRaises(PermissionDenied):
                protected_media(request, path=bad_path)
