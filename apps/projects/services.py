"""
Business logic layer for projects app.
This module contains service functions that encapsulate business operations.
"""

from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import Project, ProjectSubmission

User = get_user_model()


def _merge_submission_content(submission_text="", submission_url=""):
    parts = []
    if submission_text:
        parts.append(str(submission_text).strip())
    if submission_url:
        parts.append(str(submission_url).strip())
    return "\n".join(part for part in parts if part)


# ════════════════════════════════════════════════════════════════════════════
# Project Submission Services
# ════════════════════════════════════════════════════════════════════════════


@transaction.atomic
def create_project_submission(project, student, submission_file=None, submission_text="", submission_url=""):
    """
    Create a project submission.

    Args:
        project: Project instance
        student: User instance
        submission_file: Optional uploaded file
        submission_text: Optional submission text
        submission_url: Optional submission URL

    Returns:
        ProjectSubmission: Created submission
    """
    submission = ProjectSubmission.objects.create(
        project=project,
        student=student,
        content=_merge_submission_content(submission_text, submission_url),
    )

    if submission_file:
        submission.file = submission_file
        submission.save(update_fields=["file"])

    return submission


@transaction.atomic
def update_project_submission(submission, submission_file=None, submission_text=None, submission_url=None):
    """
    Update a project submission.

    Args:
        submission: ProjectSubmission instance
        submission_file: Optional new file
        submission_text: Optional new text
        submission_url: Optional new URL

    Returns:
        ProjectSubmission: Updated submission
    """
    update_fields = ["submitted_at", "status"]

    if submission_file is not None:
        submission.file = submission_file
        update_fields.append("file")

    if submission_text is not None:
        submission.content = _merge_submission_content(submission_text, submission_url or "")
        update_fields.append("content")
    elif submission_url is not None:
        submission.content = _merge_submission_content(submission.content, submission_url)
        update_fields.append("content")

    submission.submitted_at = timezone.now()
    submission.status = "pending"
    submission.save(update_fields=update_fields)

    return submission


# ════════════════════════════════════════════════════════════════════════════
# Project Grading Services
# ════════════════════════════════════════════════════════════════════════════


@transaction.atomic
def grade_project_submission(submission, score, feedback, graded_by):
    """
    Grade a project submission.

    Args:
        submission: ProjectSubmission instance
        score: Score value (Decimal or string)
        feedback: Feedback text
        graded_by: User grading the submission

    Returns:
        ProjectSubmission: Graded submission
    """
    if isinstance(score, str):
        score = Decimal(score)

    submission.grade = score
    submission.feedback = feedback
    submission.graded_by = graded_by
    submission.graded_at = timezone.now()
    submission.status = "graded"
    submission.save(update_fields=["grade", "feedback", "graded_by", "graded_at", "status"])

    return submission


@transaction.atomic
def bulk_grade_project_submissions(submission_ids, scores, feedback_list, graded_by):
    """
    Grade multiple project submissions at once.

    Args:
        submission_ids: List of submission IDs
        scores: List of scores
        feedback_list: List of feedback texts
        graded_by: User grading the submissions

    Returns:
        int: Number of submissions graded
    """
    submissions = ProjectSubmission.objects.filter(id__in=submission_ids)
    count = 0

    for submission, score, feedback in zip(submissions, scores, feedback_list):
        grade_project_submission(submission, score, feedback, graded_by)
        count += 1

    return count


# ════════════════════════════════════════════════════════════════════════════
# Project Assignment Services
# ════════════════════════════════════════════════════════════════════════════


@transaction.atomic
def assign_project_to_students(project, student_ids):
    """
    Assign project to multiple students.

    Args:
        project: Project instance
        student_ids: List of student user IDs

    Returns:
        int: Number of students assigned
    """
    users = User.objects.filter(id__in=student_ids)
    count = 0

    for user in users:
        if not project.assigned_students.filter(id=user.id).exists():
            project.assigned_students.add(user)
            count += 1

    return count


@transaction.atomic
def assign_project_to_group(project, student_group):
    """
    Assign project to all students in a group.

    Args:
        project: Project instance
        student_group: StudentGroup instance

    Returns:
        int: Number of students assigned
    """
    students = student_group.students.all()
    count = 0

    for student in students:
        if not project.assigned_students.filter(id=student.id).exists():
            project.assigned_students.add(student)
            count += 1

    return count


# ════════════════════════════════════════════════════════════════════════════
# Project Query Services
# ════════════════════════════════════════════════════════════════════════════


def get_project_submissions(project, status=None, group_name=None):
    """
    Get submissions for a project.

    Args:
        project: Project instance
        status: Optional status filter
        group_name: Optional group filter

    Returns:
        QuerySet: Submission queryset
    """
    qs = ProjectSubmission.objects.filter(
        project=project
    ).select_related(
        "student",
        "student__profile",
        "graded_by"
    )

    if status:
        qs = qs.filter(status=status)

    if group_name:
        from apps.courses.models import CourseMembership
        student_ids = CourseMembership.objects.filter(
            course=project.course,
            role="student",
            group_name=group_name,
        ).values_list("user_id", flat=True)
        qs = qs.filter(student_id__in=student_ids)

    return qs.order_by("-submitted_at")


def get_pending_project_submissions(teacher, organization=None):
    """
    Get pending project submissions for teacher.

    Args:
        teacher: User instance
        organization: Optional organization filter

    Returns:
        QuerySet: Submission queryset
    """
    qs = ProjectSubmission.objects.filter(
        project__course__owner=teacher,
        status="pending",
    ).select_related("project", "student")

    if organization is not None:
        qs = qs.filter(project__course__organization=organization)

    return qs.order_by("submitted_at")


def can_student_submit_project(project, student):
    """
    Check if student can submit to a project.

    Args:
        project: Project instance
        student: User instance

    Returns:
        tuple: (can_submit: bool, reason: str)
    """
    # Check if project is published
    if project.status != "active":
        return False, "project_not_published"

    # Check if student is allowed
    if not project.assigned_students.filter(id=student.id).exists():
        # Check if student is in course
        from apps.courses.models import CourseMembership
        if not CourseMembership.objects.filter(
            course=project.course,
            user=student,
            role="student",
        ).exists():
            return False, "not_allowed"

    # Check deadline if exists
    if project.deadline and timezone.now() > project.deadline:
        return False, "deadline_passed"

    return True, "ok"


# ════════════════════════════════════════════════════════════════════════════
# Score Parsing Services
# ════════════════════════════════════════════════════════════════════════════


def parse_score_value(value, *, default=None):
    """
    Parse a score value to Decimal.

    Args:
        value: Value to parse
        default: Default value if parsing fails

    Returns:
        Decimal or default
    """
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value

    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return default
