"""
Tests for core.media_views – protected media serving.
"""

from __future__ import annotations

import os
import tempfile

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

User = get_user_model()


class ProtectedMediaViewTest(TestCase):
    """
    Verify that private media files are only accessible to authenticated users,
    and that public files are freely accessible.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="media_test_user",
            email="media@example.com",
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
        from core.media_views import protected_media
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

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

    def test_private_file_accessible_to_authenticated_user(self):
        """Authenticated users can access private media files that exist on disk."""
        from core.media_views import protected_media
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/media/projects/submissions/sample.txt")
        request.user = self.user

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
        from core.media_views import protected_media
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

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
        from core.media_views import protected_media
        from django.contrib.auth.models import AnonymousUser
        from django.core.exceptions import SuspiciousFileOperation
        from django.http import Http404
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/media/../../etc/passwd")
        request.user = self.user  # authenticated, so auth check passes

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
        self.assertFalse(_is_private("question_media/exam_1/q_1/image.jpg"))

    def test_public_file_accessible_without_login(self):
        """Blog post images (post_images/) must be accessible without authentication."""
        from core.media_views import protected_media
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

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
        """When MEDIA_ACCEL_REDIRECT_URL is set, response uses X-Accel-Redirect."""
        from core.media_views import protected_media
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/media/projects/submissions/sample.txt")
        request.user = self.user  # authenticated

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
        # When SERVE_MEDIA is False (the production default), the /media/ URL
        # pattern is not registered at all, so requests return 404.
        with override_settings(
            MEDIA_ROOT=self.media_tmp,
            SERVE_MEDIA=False,
            DEBUG=False,
        ):
            response = self.client.get("/media/projects/submissions/sample.txt")
            self.assertEqual(response.status_code, 404)
