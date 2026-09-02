"""
Tests for core.media_views – protected media serving.
"""

from __future__ import annotations

import os
import tempfile

from django.contrib.auth import get_user_model
from django.http import Http404
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
            with self.assertRaises(Http404):  # icazəsiz → 404 (mövcudluq sızmasın)
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

    def test_private_file_denied_for_plain_staff_user(self):
        """P0 reqressiya: ``is_staff`` private media-ya çıxış VERMƏMƏLİDİR.

        ``is_staff`` Django-nun admin-panel bayrağıdır — tenant daşımır və
        provision/seed yolları onu adi istifadəçilərə verir. Əvvəl bu bayraq
        bütün tenant-ların bütün private fayllarına şərtsiz giriş verirdi
        (cross-tenant sızma: jurnal, cavab vərəqi, apellyasiya sənədi).
        """
        from django.test import RequestFactory

        from core.media_views import protected_media

        staff_user = User.objects.create_user("plain_staff", "plain_staff@example.com", "pw")
        staff_user.is_staff = True
        staff_user.save(update_fields=["is_staff"])

        factory = RequestFactory()
        request = factory.get("/media/projects/submissions/sample.txt")
        request.user = staff_user

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            SERVE_MEDIA=True,
            DEBUG=False,
            MEDIA_ACCEL_REDIRECT_URL="",
        ):
            with self.assertRaises(Http404):  # icazəsiz → 404 (mövcudluq sızmasın)
                protected_media(request, path="projects/submissions/sample.txt")

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
        self.assertTrue(_is_private("bank_media/bank_1/q_1/image.png"))
        self.assertTrue(_is_private("question_imports/token/q_1.png"))
        self.assertTrue(_is_private("import_jobs/2026/07/source.pdf"))

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
        """SERVE_MEDIA=False in production means files are never served directly.

        The protected_media view is always registered (so Django can enforce
        authentication and emit X-Accel-Redirect headers for nginx).  For
        unauthenticated requests to private paths, the view redirects to the
        login page regardless of SERVE_MEDIA — files are never exposed.
        """
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        from core.media_views import protected_media

        factory = RequestFactory()
        request = factory.get("/media/projects/submissions/sample.txt")
        request.user = AnonymousUser()

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            SERVE_MEDIA=False,
            DEBUG=False,
            MEDIA_ACCEL_REDIRECT_URL="",
        ):
            response = protected_media(request, path="projects/submissions/sample.txt")
            # Unauthenticated users must be redirected to login, not served the file.
            self.assertEqual(response.status_code, 302)
            self.assertIn("login", response["Location"].lower())

    def test_dev_private_media_requires_auth(self):
        """
        In DEBUG mode, private media paths must still require authentication.
        Unauthenticated requests to private paths (e.g. exam_uploads/) must be
        redirected to the login page — not served openly.
        """
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        from core.media_views import protected_media

        factory = RequestFactory()
        request = factory.get("/media/exam_uploads/secret.pdf")
        request.user = AnonymousUser()

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            SERVE_MEDIA=True,
            DEBUG=True,
            MEDIA_ACCEL_REDIRECT_URL="",
        ):
            response = protected_media(request, path="exam_uploads/secret.pdf")
            self.assertEqual(response.status_code, 302)
            self.assertIn("login", response["Location"].lower())

    def test_unauthenticated_user_cannot_access_private_media(self):
        """
        Acceptance criteria: an unauthenticated (anonymous) user must never
        receive a successful response (HTTP 200) for any private media path.
        The view must redirect them to the login page (HTTP 302) instead.

        Covers multiple private prefixes to ensure the guard is applied
        consistently regardless of the specific private path family.
        """
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        from core.media_views import protected_media

        factory = RequestFactory()

        private_paths = [
            "projects/submissions/report.pdf",
            "exam_uploads/answer.pdf",
            "exam_paints/drawing.png",
            "labs/submissions/lab.zip",
        ]

        for path in private_paths:
            with self.subTest(path=path):
                request = factory.get(f"/media/{path}")
                request.user = AnonymousUser()

                with override_settings(
                    MEDIA_ROOT=self.media_tmp,
                    MEDIA_URL="/media/",
                    SERVE_MEDIA=True,
                    DEBUG=False,
                    MEDIA_ACCEL_REDIRECT_URL="",
                ):
                    response = protected_media(request, path=path)
                    self.assertEqual(
                        response.status_code,
                        302,
                        f"Unauthenticated user must be redirected for private path: {path}",
                    )
                    self.assertIn(
                        "login",
                        response["Location"].lower(),
                        f"Redirect must point to login for path: {path}",
                    )

    def test_dev_public_media_accessible_without_auth(self):
        """
        In DEBUG mode, public media paths (post_images/) must remain accessible
        without authentication.
        """
        import os

        public_dir = os.path.join(self.media_tmp, "post_images")
        os.makedirs(public_dir, exist_ok=True)
        with open(os.path.join(public_dir, "cover.jpg"), "wb") as f:
            f.write(b"\xff\xd8\xff\xe0")

        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        from core.media_views import protected_media

        factory = RequestFactory()
        request = factory.get("/media/post_images/cover.jpg")
        request.user = AnonymousUser()

        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            MEDIA_URL="/media/",
            SERVE_MEDIA=True,
            DEBUG=True,
            MEDIA_ACCEL_REDIRECT_URL="",
        ):
            response = protected_media(request, path="post_images/cover.jpg")
            # Public files must be served (200), not redirected
            self.assertEqual(response.status_code, 200)


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
            with self.assertRaises(Http404):  # icazəsiz → 404 (mövcudluq sızmasın)
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
            with self.assertRaises(Http404):  # icazəsiz → 404 (mövcudluq sızmasın)
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
        self.question.image = self.file_path
        self.question.save(update_fields=["image"])

        # Create the physical file
        file_dir = os.path.join(self.media_tmp, "question_media", f"exam_{self.exam.pk}", f"q_{self.question.pk}")
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
            with self.assertRaises(Http404):  # icazəsiz → 404 (mövcudluq sızmasın)
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
            with self.assertRaises(Http404):  # icazəsiz → 404 (mövcudluq sızmasın)
                protected_media(request, path=bad_path)


# ---------------------------------------------------------------------------
# Tests required by Task 6 (P1): explicit access-checker registry
# ---------------------------------------------------------------------------


class QuestionMediaAccessCheckerRegistryTest(TestCase):
    """
    Tests for the ``_ACCESS_CHECKERS`` registry introduced in Task 6.

    Success criteria:
    * ``question_media/`` has a dedicated entry in ``_ACCESS_CHECKERS``.
    * A student's attempt alone does not expose random-pool question media.
    * Only questions represented by ``ExamAnswer`` rows, and their options,
      are available to that student.
    * A path target must belong to the exam encoded in the same path.
    """

    def setUp(self):
        from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption
        from apps.organizations.models import Membership, Organization
        from core.constants import OrganizationType

        self.allowed_user = User.objects.create_user(
            username="checker_member",
            email="checker_member@example.com",
            password="StrongPass123!",
        )
        self.denied_user = User.objects.create_user(
            username="checker_outsider",
            email="checker_outsider@example.com",
            password="StrongPass123!",
        )
        self.author = User.objects.create_user(
            username="checker_author",
            email="checker_author@example.com",
            password="StrongPass123!",
        )

        self.org = Organization.objects.create(
            name="Checker Registry Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.author,
            status="active",
            is_active=True,
        )
        student_role = self.org.roles.get(name="student")
        Membership.objects.create(
            user=self.allowed_user,
            organization=self.org,
            role=student_role,
            is_primary=True,
            is_active=True,
        )

        self.exam = Exam.objects.create(
            title="Registry Test Exam",
            author=self.author,
            organization=self.org,
            is_active=True,
        )
        self.q1 = ExamQuestion.objects.create(
            exam=self.exam,
            text="Delivered question",
            order=1,
            points=1,
        )
        self.q2 = ExamQuestion.objects.create(
            exam=self.exam,
            text="Undelivered random-pool question",
            order=2,
            points=1,
        )
        self.q1_option = ExamQuestionOption.objects.create(
            question=self.q1,
            label="A",
            text="Delivered option",
        )
        self.q2_option = ExamQuestionOption.objects.create(
            question=self.q2,
            label="A",
            text="Undelivered option",
        )

        prefix = f"question_media/exam_{self.exam.pk}"
        self.q1_path = f"{prefix}/q_{self.q1.pk}/question.png"
        self.q2_path = f"{prefix}/q_{self.q2.pk}/question.png"
        self.q1_option_path = f"{prefix}/opt_{self.q1_option.pk}/option.png"
        self.q2_option_path = f"{prefix}/opt_{self.q2_option.pk}/option.png"
        self.q1.image = self.q1_path
        self.q2.image = self.q2_path
        self.q1.save(update_fields=["image"])
        self.q2.save(update_fields=["image"])
        self.q1_option.image = self.q1_option_path
        self.q2_option.image = self.q2_option_path
        self.q1_option.save(update_fields=["image"])
        self.q2_option.save(update_fields=["image"])
        self.path = self.q1_path

    def test_question_media_access_checker_exists(self):
        """
        ``_ACCESS_CHECKERS`` must contain an entry for the ``question_media/`` prefix.
        """
        from core.media_views import _ACCESS_CHECKERS

        self.assertIn(
            "question_media/",
            _ACCESS_CHECKERS,
            "question_media/ must have a dedicated entry in _ACCESS_CHECKERS",
        )
        checker = _ACCESS_CHECKERS["question_media/"]
        self.assertTrue(callable(checker), "_ACCESS_CHECKERS['question_media/'] must be callable")

    def test_student_can_access_only_delivered_question_and_its_options(self):
        """An ExamAnswer grants only its question and option media."""
        from apps.exams.models import ExamAnswer, ExamAttempt
        from core.media_views import _ACCESS_CHECKERS

        checker = _ACCESS_CHECKERS["question_media/"]

        # Sadə same-org membership sual məzmununa giriş vermir.
        self.assertFalse(checker(self.allowed_user, self.q1_path))

        attempt = ExamAttempt.objects.create(user=self.allowed_user, exam=self.exam, status="in_progress")

        # Attempt-in özü random pool-dakı heç bir sualı açmır.
        self.assertFalse(checker(self.allowed_user, self.q1_path))
        self.assertFalse(checker(self.allowed_user, self.q1_option_path))

        ExamAnswer.objects.create(attempt=attempt, question=self.q1)

        self.assertTrue(checker(self.allowed_user, self.q1_path))
        self.assertTrue(checker(self.allowed_user, self.q1_option_path))
        self.assertFalse(checker(self.allowed_user, self.q2_path))
        self.assertFalse(checker(self.allowed_user, self.q2_option_path))

        # Müəllif idarəetmə zamanı hələ çatdırılmamış sualı da görə bilər.
        self.assertTrue(checker(self.author, self.q2_path))
        self.assertTrue(checker(self.author, self.q2_option_path))

        # Denied: user has no membership in the exam's org
        self.assertFalse(
            checker(self.denied_user, self.q1_path),
            "Non-member must be denied access to question_media",
        )

    def test_question_and_option_targets_must_belong_to_path_exam(self):
        """Author bypass does not authorize a target from a different exam."""
        from apps.exams.models import Exam
        from core.media_views import _ACCESS_CHECKERS

        other_exam = Exam.objects.create(
            title="Other Registry Test Exam",
            author=self.author,
            organization=self.org,
            is_active=True,
        )
        checker = _ACCESS_CHECKERS["question_media/"]

        wrong_question_path = f"question_media/exam_{other_exam.pk}/q_{self.q1.pk}/question.png"
        wrong_option_path = f"question_media/exam_{other_exam.pk}/opt_{self.q1_option.pk}/option.png"

        self.assertFalse(checker(self.author, wrong_question_path))
        self.assertFalse(checker(self.author, wrong_option_path))

    def test_legacy_new_paths_resolve_only_by_exact_field_name(self):
        """ModelForm create zamanı yaranan q_new/opt_new yolları da scope-ludur."""
        from core.media_views import _ACCESS_CHECKERS

        checker = _ACCESS_CHECKERS["question_media/"]
        prefix = f"question_media/exam_{self.exam.pk}"
        question_path = f"{prefix}/q_new/manual-question.png"
        option_path = f"{prefix}/opt_new/manual-option.png"
        self.q1.image = question_path
        self.q1.save(update_fields=["image"])
        self.q1_option.image = option_path
        self.q1_option.save(update_fields=["image"])

        self.assertTrue(checker(self.author, question_path))
        self.assertTrue(checker(self.author, option_path))
        self.assertFalse(checker(self.author, f"{prefix}/q_new/not-the-field.png"))
        self.assertFalse(checker(self.author, f"{prefix}/opt_new/not-the-field.png"))

    def test_question_media_checker_denies_nonexistent_exam(self):
        """
        Checker must deny (fail-closed) when the exam ID does not exist in the DB.
        """
        from core.media_views import _ACCESS_CHECKERS

        checker = _ACCESS_CHECKERS["question_media/"]
        bad_path = "question_media/exam_999999/q_1/img.png"
        self.assertFalse(
            checker(self.allowed_user, bad_path),
            "Path with non-existent exam ID must be denied",
        )

    def test_question_media_checker_denies_malformed_path(self):
        """
        Checker must deny paths that do not contain a recognisable exam segment.
        """
        from core.media_views import _ACCESS_CHECKERS

        checker = _ACCESS_CHECKERS["question_media/"]
        malformed = "question_media/unknown/file.png"
        self.assertFalse(
            checker(self.allowed_user, malformed),
            "Malformed question_media path must be denied",
        )


class ImportAndBankMediaAccessTest(TestCase):
    """Tenant and ownership checks for import and question-bank media."""

    def setUp(self):
        from apps.exams.models import QuestionBank, TextExtractionJob
        from apps.organizations.models import Membership, Organization
        from core.constants import OrganizationType

        self.creator = User.objects.create_user(
            username="private_media_creator",
            email="private_media_creator@example.com",
            password="StrongPass123!",
        )
        self.member = User.objects.create_user(
            username="private_media_member",
            email="private_media_member@example.com",
            password="StrongPass123!",
        )
        self.teacher = User.objects.create_user(
            username="private_media_teacher",
            email="private_media_teacher@example.com",
            password="StrongPass123!",
        )
        self.inactive_teacher = User.objects.create_user(
            username="private_media_inactive_teacher",
            email="private_media_inactive_teacher@example.com",
            password="StrongPass123!",
        )
        self.outsider = User.objects.create_user(
            username="private_media_outsider",
            email="private_media_outsider@example.com",
            password="StrongPass123!",
        )

        self.org = Organization.objects.create(
            name="Private Media Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.creator,
            status="active",
            is_active=True,
        )
        self.other_org = Organization.objects.create(
            name="Private Media Other Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.outsider,
            status="active",
            is_active=True,
        )

        Membership.objects.create(
            user=self.member,
            organization=self.org,
            role=self.org.roles.get(name="student"),
            is_active=True,
            is_primary=True,
        )
        Membership.objects.create(
            user=self.teacher,
            organization=self.org,
            role=self.org.roles.get(name="teacher"),
            is_active=True,
            is_primary=True,
        )
        Membership.objects.create(
            user=self.inactive_teacher,
            organization=self.org,
            role=self.org.roles.get(name="teacher"),
            is_active=False,
            is_primary=True,
        )
        Membership.objects.create(
            user=self.outsider,
            organization=self.other_org,
            role=self.other_org.roles.get(name="teacher"),
            is_active=True,
            is_primary=True,
        )

        self.bank = QuestionBank.objects.create(
            name="Organization Bank",
            created_by=self.creator,
            organization=self.org,
            is_shared=True,
        )
        self.private_bank = QuestionBank.objects.create(
            name="Private Organization Bank",
            created_by=self.creator,
            organization=self.org,
            is_shared=False,
        )
        self.legacy_bank = QuestionBank.objects.create(
            name="Legacy Personal Bank",
            created_by=self.creator,
            organization=None,
        )
        self.bank_path = f"bank_media/bank_{self.bank.pk}/q_1/image.png"
        self.legacy_bank_path = f"bank_media/bank_{self.legacy_bank.pk}/q_1/image.png"

        self.job_file_path = "import_jobs/2026/07/source.pdf"
        self.job_result_path = "import_jobs/2026/07/result.docx"
        self.job = TextExtractionJob.objects.create(
            user=self.creator,
            organization=self.org,
            file=self.job_file_path,
            result_file=self.job_result_path,
        )
        self.legacy_job_path = "import_jobs/2026/07/legacy.pdf"
        self.legacy_job = TextExtractionJob.objects.create(
            user=self.creator,
            organization=None,
            file=self.legacy_job_path,
        )

    def test_private_prefixes_have_exactly_one_registered_checker(self):
        """Every private prefix must retain an explicit checker."""
        from core.media_views import _ACCESS_CHECKERS, _PRIVATE_PREFIXES

        self.assertEqual(set(_PRIVATE_PREFIXES), set(_ACCESS_CHECKERS))
        self.assertTrue(all(callable(checker) for checker in _ACCESS_CHECKERS.values()))

    def test_bank_media_allows_creator_and_active_same_org_teacher(self):
        from core.media_views import _ACCESS_CHECKERS

        checker = _ACCESS_CHECKERS["bank_media/"]
        self.assertTrue(checker(self.creator, self.bank_path))
        self.assertTrue(checker(self.teacher, self.bank_path))
        self.assertFalse(checker(self.member, self.bank_path))

    def test_bank_media_denies_inactive_cross_org_and_malformed_access(self):
        from core.media_views import _ACCESS_CHECKERS

        checker = _ACCESS_CHECKERS["bank_media/"]
        self.assertFalse(checker(self.inactive_teacher, self.bank_path))
        self.assertFalse(checker(self.outsider, self.bank_path))
        self.assertFalse(checker(self.member, "bank_media/bank_bad/q_1/image.png"))
        self.assertFalse(checker(self.member, "bank_media/bank_999999/q_1/image.png"))

    def test_private_bank_media_is_creator_only_inside_same_tenant(self):
        from core.media_views import _ACCESS_CHECKERS

        checker = _ACCESS_CHECKERS["bank_media/"]
        path = f"bank_media/bank_{self.private_bank.pk}/q_1/image.png"
        self.assertTrue(checker(self.creator, path))
        self.assertFalse(checker(self.teacher, path))

    def test_legacy_bank_media_is_creator_only(self):
        from core.media_views import _ACCESS_CHECKERS

        checker = _ACCESS_CHECKERS["bank_media/"]
        self.assertTrue(checker(self.creator, self.legacy_bank_path))
        self.assertFalse(checker(self.member, self.legacy_bank_path))
        self.assertFalse(checker(self.teacher, self.legacy_bank_path))

    def test_import_job_owner_can_access_source_and_result(self):
        from core.media_views import _ACCESS_CHECKERS

        checker = _ACCESS_CHECKERS["import_jobs/"]
        self.assertTrue(checker(self.creator, self.job_file_path))
        self.assertTrue(checker(self.creator, self.job_result_path))

    def test_import_job_is_owner_only_even_inside_same_organization(self):
        from core.media_views import _ACCESS_CHECKERS

        checker = _ACCESS_CHECKERS["import_jobs/"]
        self.assertFalse(checker(self.teacher, self.job_file_path))
        self.assertFalse(checker(self.member, self.job_file_path))
        self.assertFalse(checker(self.inactive_teacher, self.job_file_path))
        self.assertFalse(checker(self.outsider, self.job_file_path))

    def test_organizationless_import_job_is_owner_only(self):
        from core.media_views import _ACCESS_CHECKERS

        checker = _ACCESS_CHECKERS["import_jobs/"]
        self.assertTrue(checker(self.creator, self.legacy_job_path))
        self.assertFalse(checker(self.teacher, self.legacy_job_path))
        self.assertFalse(checker(self.outsider, "import_jobs/2026/07/missing.pdf"))

    def test_question_imports_are_denied_over_http(self):
        from django.test import RequestFactory

        from core.media_views import protected_media

        path = "question_imports/token/question.png"
        request = RequestFactory().get(f"/media/{path}")
        request.user = self.creator

        with override_settings(MEDIA_ROOT=tempfile.mkdtemp()):
            with self.assertRaises(Http404):  # icazəsiz → 404 (mövcudluq sızmasın)
                protected_media(request, path=path)

    def test_path_normalization_cannot_disguise_private_import_as_public(self):
        from django.test import RequestFactory

        from core.media_views import protected_media

        path = "post_images/../question_imports/token/question.png"
        request = RequestFactory().get(f"/media/{path}")
        request.user = self.creator

        with override_settings(MEDIA_ROOT=tempfile.mkdtemp()):
            with self.assertRaises(Http404):  # icazəsiz → 404 (mövcudluq sızmasın)
                protected_media(request, path=path)
