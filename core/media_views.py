"""
Protected media download view.

Private media files (submissions, exam uploads, lab files) must only be
accessible to authenticated users with verified ownership or organization
membership. This view enforces authentication and tenant/ownership checks
before serving files from MEDIA_ROOT.

In production with a properly configured nginx/caddy, set the X-Accel-Redirect
header and serve files from an internal location (e.g. ``/internal_media/``).
Set ``MEDIA_ACCEL_REDIRECT_URL`` to that internal prefix (e.g. ``/internal_media``).

Access-control model
--------------------
* Unauthenticated users are redirected to login for private paths.
* Superusers and Django staff may access all private files.
* For all other authenticated users access is verified by looking up the
  owning model record in the database and checking that the requester is
  either the file owner or has an active membership in the resource's
  organization at an appropriate role level.
* If ownership cannot be determined the request is **denied** (HTTP 403).
"""

from __future__ import annotations

import mimetypes
import posixpath

from django.conf import settings
from django.core.exceptions import PermissionDenied, SuspiciousFileOperation
from django.http import FileResponse, Http404, HttpResponse
from django.utils._os import safe_join
from django.views.decorators.http import require_GET

# Paths that are considered public and do not require authentication.
# These are served openly (blog images, course covers, etc.).
_PUBLIC_PREFIXES: tuple[str, ...] = (
    "post_images/",
    "course_covers/",
    "question_media/",
)

# Paths that always require authentication.
_PRIVATE_PREFIXES: tuple[str, ...] = (
    "avatars/",
    "course_resources/",
    "projects/submissions/",
    "exam_uploads/",
    "exam_paints/",
    "labs/",
)

# Minimum role level considered "teacher-level" for access to sensitive files
# (lab_assistant = 50, teacher = 60; using 50 to include lab assistants).
_TEACHER_MIN_LEVEL = 50


def _is_private(path: str) -> bool:
    """Return True if the path prefix belongs to sensitive private storage."""
    clean = path.lstrip("/")
    return clean.startswith(_PRIVATE_PREFIXES)


def _user_has_org_membership(user, organization, *, min_level: int = 0) -> bool:
    """Return True if *user* has an active membership in *organization*."""
    return user.memberships.filter(
        organization=organization,
        is_active=True,
        role__level__gte=min_level,
    ).exists()


def _check_exam_upload_access(user, path: str) -> bool:
    """
    Verify access to ``exam_uploads/`` files.

    The student who submitted the file or any teacher-level member of the
    exam's organization may access it.
    """
    try:
        from apps.exams.domain.attempts import ExamAnswerFile

        af = ExamAnswerFile.objects.select_related(
            "answer__attempt__user",
            "answer__attempt__exam__organization",
        ).get(file=path)
        attempt = af.answer.attempt
        if attempt.user_id == user.id:
            return True
        org = attempt.exam.organization
        return _user_has_org_membership(user, org, min_level=_TEACHER_MIN_LEVEL)
    except ExamAnswerFile.DoesNotExist:
        return False


def _check_exam_paint_access(user, path: str) -> bool:
    """
    Verify access to ``exam_paints/`` files.

    The student whose answer painting it is, or any teacher-level member of
    the exam's organization, may access it.
    """
    try:
        from apps.exams.domain.attempts import ExamAnswer

        answer = ExamAnswer.objects.select_related(
            "attempt__user",
            "attempt__exam__organization",
        ).get(paint_image=path)
        attempt = answer.attempt
        if attempt.user_id == user.id:
            return True
        org = attempt.exam.organization
        return _user_has_org_membership(user, org, min_level=_TEACHER_MIN_LEVEL)
    except ExamAnswer.DoesNotExist:
        return False


def _check_project_submission_access(user, path: str) -> bool:
    """
    Verify access to ``projects/submissions/`` files.

    The student who submitted, or any teacher-level member of the project's
    course organization, may access it.
    """
    try:
        from apps.projects.models import ProjectSubmission

        sub = ProjectSubmission.objects.select_related(
            "student",
            "project__course__organization",
        ).get(file=path)
        if sub.student_id == user.id:
            return True
        org = sub.project.course.organization
        return _user_has_org_membership(user, org, min_level=_TEACHER_MIN_LEVEL)
    except ProjectSubmission.DoesNotExist:
        return False


def _check_lab_file_access(user, path: str) -> bool:
    """
    Verify access to ``labs/`` files.

    Handles four storage sub-paths:
    * ``labs/teacher_files/`` – teacher-level org membership only.
    * ``labs/questions/``     – any member of the org (students may view).
    * ``labs/submissions/``   – student owner or teacher-level org membership.
    * ``labs/answers/``       – student owner or teacher-level org membership.
    """
    clean = path.lstrip("/")

    if clean.startswith("labs/teacher_files/"):
        try:
            from apps.labs.models import Lab

            lab = Lab.objects.select_related("course__organization").get(teacher_files=path)
            return _user_has_org_membership(user, lab.course.organization, min_level=_TEACHER_MIN_LEVEL)
        except Lab.DoesNotExist:
            return False

    if clean.startswith("labs/questions/"):
        try:
            from apps.labs.models import LabQuestion

            lq = LabQuestion.objects.select_related("block__lab__course__organization").get(attachment=path)
            # Students who are members of the org may view question attachments.
            return _user_has_org_membership(user, lq.block.lab.course.organization, min_level=0)
        except LabQuestion.DoesNotExist:
            return False

    if clean.startswith("labs/submissions/"):
        try:
            from apps.labs.models import LabSubmission

            sub = LabSubmission.objects.select_related(
                "assignment__student",
                "assignment__lab__course__organization",
            ).get(submission_file=path)
            if sub.assignment.student_id == user.id:
                return True
            org = sub.assignment.lab.course.organization
            return _user_has_org_membership(user, org, min_level=_TEACHER_MIN_LEVEL)
        except LabSubmission.DoesNotExist:
            return False

    if clean.startswith("labs/answers/"):
        try:
            from apps.labs.models import LabAnswer

            ans = LabAnswer.objects.select_related(
                "student",
                "lab__course__organization",
            ).get(answer_file=path)
            if ans.student_id == user.id:
                return True
            return _user_has_org_membership(user, ans.lab.course.organization, min_level=_TEACHER_MIN_LEVEL)
        except LabAnswer.DoesNotExist:
            return False

    # Unknown labs/ sub-path — deny
    return False


def _check_course_resource_access(user, path: str) -> bool:
    """
    Verify access to ``course_resources/`` files.

    Any active member of the resource's course organization may access it.
    """
    try:
        from apps.courses.models import CourseResource

        resource = CourseResource.objects.select_related("course__organization").get(file=path)
        return _user_has_org_membership(user, resource.course.organization, min_level=0)
    except CourseResource.DoesNotExist:
        return False


def _check_private_media_access(request, path: str) -> bool:
    """
    Return True if the requesting user is authorised to access the private
    media file at *path*.

    Access is **denied by default** when the owning record cannot be found
    in the database.
    """
    user = request.user
    if not user.is_authenticated:
        return False

    # Superusers and Django staff have unrestricted access to private files.
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True

    clean = path.lstrip("/")

    # Profile avatars are low-risk and needed across the system.
    if clean.startswith("avatars/"):
        return True

    if clean.startswith("exam_uploads/"):
        return _check_exam_upload_access(user, path)

    if clean.startswith("exam_paints/"):
        return _check_exam_paint_access(user, path)

    if clean.startswith("projects/submissions/"):
        return _check_project_submission_access(user, path)

    if clean.startswith("labs/"):
        return _check_lab_file_access(user, path)

    if clean.startswith("course_resources/"):
        return _check_course_resource_access(user, path)

    # Unknown private path — deny by default.
    return False


@require_GET
def protected_media(request, path: str):
    """
    Serve a media file, requiring authentication and ownership/tenant checks
    for private paths.

    Supports X-Accel-Redirect for nginx: set ``MEDIA_ACCEL_REDIRECT_URL``
    in settings to the internal location prefix (e.g. ``/internal_media``).
    """
    # Sanitize to prevent path traversal
    try:
        abs_path = safe_join(str(settings.MEDIA_ROOT), path)
    except SuspiciousFileOperation:
        raise Http404("Invalid media path.")

    if _is_private(path):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())
        if not _check_private_media_access(request, path):
            raise PermissionDenied

    # Support X-Accel-Redirect for production nginx setups
    accel_url = (getattr(settings, "MEDIA_ACCEL_REDIRECT_URL", None) or "").rstrip("/")
    if accel_url:
        # Delegate file serving to nginx via internal redirect.
        clean_path = posixpath.normpath(path).lstrip("/")
        response = HttpResponse()
        response["X-Accel-Redirect"] = f"{accel_url}/{clean_path}"
        response["Content-Type"] = mimetypes.guess_type(path)[0] or "application/octet-stream"
        response["X-Content-Type-Options"] = "nosniff"
        if _is_private(path):
            response["Cache-Control"] = "private, no-store"
        return response

    # Fall back to Django-based file serving (development / simple deployments)
    import os

    if not os.path.isfile(abs_path):
        raise Http404("Media file not found.")

    content_type = mimetypes.guess_type(abs_path)[0] or "application/octet-stream"
    response = FileResponse(open(abs_path, "rb"), content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    if _is_private(path):
        response["Cache-Control"] = "private, no-store"
    else:
        response["Cache-Control"] = "public, max-age=3600"
    return response
