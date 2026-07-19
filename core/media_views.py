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

Access-checker registry (``_ACCESS_CHECKERS``)
-----------------------------------------------
Each private path prefix maps to a dedicated checker callable with the
signature ``(user, path: str) -> bool``.  Adding a new private prefix is a
two-step operation:

1. Register the path prefix in ``_PRIVATE_PREFIXES``.
2. Register a checker under the **same** prefix key in ``_ACCESS_CHECKERS``.

``_check_private_media_access`` iterates ``_ACCESS_CHECKERS`` in order and
dispatches to the first matching checker.  Unknown private prefixes are denied
by default.
"""

from __future__ import annotations

import mimetypes
import posixpath

from django.apps import apps as django_apps
from django.conf import settings
from django.core.exceptions import PermissionDenied, SuspiciousFileOperation
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import redirect
from django.utils._os import safe_join
from django.views.decorators.http import require_GET

# Paths that are considered public and do not require authentication.
# These are served openly (blog images, course covers, etc.).
_PUBLIC_PREFIXES: tuple[str, ...] = (
    "post_images/",
    "course_covers/",
)

# Paths that always require authentication.
_PRIVATE_PREFIXES: tuple[str, ...] = (
    "avatars/",
    "course_resources/",
    "projects/submissions/",
    "exam_uploads/",
    "exam_paints/",
    "labs/",
    "question_media/",
    "trial_exams/",
    "journal_corrections/",
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
        ExamAnswerFile = django_apps.get_model("exams", "ExamAnswerFile")

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
        ExamAnswer = django_apps.get_model("exams", "ExamAnswer")

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
        ProjectSubmission = django_apps.get_model("projects", "ProjectSubmission")

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
            Lab = django_apps.get_model("labs", "Lab")

            lab = Lab.objects.select_related("course__organization").get(teacher_files=path)
            return _user_has_org_membership(user, lab.course.organization, min_level=_TEACHER_MIN_LEVEL)
        except Lab.DoesNotExist:
            return False

    if clean.startswith("labs/questions/"):
        try:
            LabQuestion = django_apps.get_model("labs", "LabQuestion")

            lq = LabQuestion.objects.select_related("block__lab__course__organization").get(attachment=path)
            # Students who are members of the org may view question attachments.
            return _user_has_org_membership(user, lq.block.lab.course.organization, min_level=0)
        except LabQuestion.DoesNotExist:
            return False

    if clean.startswith("labs/submissions/"):
        try:
            LabSubmission = django_apps.get_model("labs", "LabSubmission")

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
            LabAnswer = django_apps.get_model("labs", "LabAnswer")

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


def _check_question_media_access(user, path: str) -> bool:
    """
    Verify access to ``question_media/`` files.

    Question images and videos belong to an ``Exam`` that is scoped to an
    ``Organization``.  Access is granted to any user who holds an **active
    membership** in that organization (students, teachers, and admins alike).

    Path format: ``question_media/exam_{exam_id}/q_{question_id}/{filename}``
    The ``exam_{exam_id}`` segment is used to resolve the owning Exam and its
    Organization; all other path segments are ignored for access purposes.

    Returns ``False`` (deny) when:
    * the path does not contain a recognisable ``exam_*`` segment, or
    * the exam does not exist in the database, or
    * the user has no active membership in the exam's organization.
    """
    clean = path.lstrip("/")
    # Expected format: question_media/exam_{exam_id}/...
    parts = clean.split("/")
    if len(parts) < 2:
        return False
    exam_segment = parts[1]  # e.g. "exam_42"
    if not exam_segment.startswith("exam_"):
        return False
    exam_id_str = exam_segment[len("exam_") :]
    if not exam_id_str.isdigit():
        return False

    try:
        Exam = django_apps.get_model("exams", "Exam")
        ExamAttempt = django_apps.get_model("exams", "ExamAttempt")

        exam = Exam.objects.select_related("organization").get(pk=int(exam_id_str))
        if exam.organization is None:
            return False

        # Active org members (teachers, admins, enrolled students) may view.
        if _user_has_org_membership(user, exam.organization, min_level=0):
            return True

        # The exam's author always has access to its own question media.
        if getattr(exam, "author_id", None) == user.id:
            return True

        # A student legitimately tied to THIS exam — even without a formal
        # Membership row — must be able to see the question's image/video:
        #   * they have (or had) an attempt on the exam, or
        #   * they are individually allowed, or in an allowed group.
        # Scope stays strict: access is bound to this one exam, not the org.
        if ExamAttempt.objects.filter(exam=exam, user=user).exists():
            return True
        if exam.allowed_users.filter(pk=user.id).exists():
            return True
        if exam.allowed_groups.filter(students=user).exists():
            return True

        return False
    except (Exam.DoesNotExist, ValueError):
        return False


def _check_course_resource_access(user, path: str) -> bool:
    """
    Verify access to ``course_resources/`` files.

    Any active member of the resource's course organization may access it.
    """
    try:
        CourseResource = django_apps.get_model("courses", "CourseResource")

        resource = CourseResource.objects.select_related("course__organization").get(file=path)
        return _user_has_org_membership(user, resource.course.organization, min_level=0)
    except CourseResource.DoesNotExist:
        return False


def _check_avatar_access(user, path: str) -> bool:  # noqa: ARG001
    """Profile avatars are low-risk; any authenticated user may access them."""
    return True


def _check_trial_exam_access(user, path: str) -> bool:
    """
    Verify access to ``trial_exams/`` uploaded question PDFs.

    Only the student who submitted the request may download their own file.
    Staff/superusers are already granted earlier in
    ``_check_private_media_access`` (they review submissions via the admin).
    """
    try:
        TrialExamRequest = django_apps.get_model("trial_exams", "TrialExamRequest")

        req = TrialExamRequest.objects.only("user_id").get(questions_file=path)
        return req.user_id is not None and req.user_id == user.id
    except TrialExamRequest.DoesNotExist:
        return False


# Təşkilat-admin səviyyəsi (org_admin=80) — jurnal düzəliş sənədləri həssasdır
# (tibbi arayış və s.), yalnız korrektorlar (admin) + sənədin aid olduğu tələbə.
_ORG_ADMIN_MIN_LEVEL = 80


def _check_journal_correction_access(user, path: str) -> bool:
    """Verify access to ``journal_corrections/`` PDFs (medical/official docs).

    Superusers/staff are granted earlier. Here: the student whose corrected mark
    it is, OR an admin-level member of the correction's organization."""
    try:
        JournalCorrection = django_apps.get_model("registrar", "JournalCorrection")
        correction = JournalCorrection.objects.select_related("organization", "lesson_mark__enrollment").get(
            document=path
        )
    except JournalCorrection.DoesNotExist:
        return False
    student_id = getattr(correction.lesson_mark.enrollment, "student_id", None)
    if student_id is not None and student_id == user.id:
        return True
    return _user_has_org_membership(user, correction.organization, min_level=_ORG_ADMIN_MIN_LEVEL)


# ---------------------------------------------------------------------------
# Access-checker registry
# ---------------------------------------------------------------------------
# Maps a private path prefix to the callable that decides whether *user* may
# access a file under that prefix.  The dict is ordered (Python 3.7+) so the
# iteration in ``_check_private_media_access`` is deterministic.
#
# To add a new private prefix:
#   1. Add the prefix to ``_PRIVATE_PREFIXES`` above.
#   2. Register a checker here under the same prefix key.
# ---------------------------------------------------------------------------

_ACCESS_CHECKERS: dict[str, object] = {
    "avatars/": _check_avatar_access,
    "exam_uploads/": _check_exam_upload_access,
    "exam_paints/": _check_exam_paint_access,
    "projects/submissions/": _check_project_submission_access,
    "labs/": _check_lab_file_access,
    "course_resources/": _check_course_resource_access,
    "question_media/": _check_question_media_access,
    "trial_exams/": _check_trial_exam_access,
    "journal_corrections/": _check_journal_correction_access,
}


def _check_private_media_access(request, path: str) -> bool:
    """
    Return True if the requesting user is authorised to access the private
    media file at *path*.

    Access is **denied by default** when the owning record cannot be found
    in the database or the path prefix is not registered in ``_ACCESS_CHECKERS``.

    Dispatches to the appropriate checker via the ``_ACCESS_CHECKERS`` registry
    so that every private prefix has an explicit, auditable access rule.
    """
    user = request.user
    if not user.is_authenticated:
        return False

    # Superusers and Django staff have unrestricted access to private files.
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True

    clean = path.lstrip("/")

    for prefix, checker in _ACCESS_CHECKERS.items():
        if clean.startswith(prefix):
            return checker(user, path)

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

    clean_path = posixpath.normpath(path).lstrip("/")
    if clean_path == ".." or clean_path.startswith("../"):
        raise Http404("Invalid media path.")

    if getattr(settings, "OBJECT_STORAGE_ENABLED", False):
        if not default_storage.exists(clean_path):
            raise Http404("Media file not found.")

        response = redirect(default_storage.url(clean_path))
        if _is_private(path):
            response["Cache-Control"] = "private, no-store"
        else:
            response["Cache-Control"] = "public, max-age=3600"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    # Support X-Accel-Redirect for production nginx setups
    accel_url = (getattr(settings, "MEDIA_ACCEL_REDIRECT_URL", None) or "").rstrip("/")
    if accel_url:
        # Delegate file serving to nginx via internal redirect.
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
