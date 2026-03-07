"""
Business logic layer for assignments app.
This module contains service functions that encapsulate business operations.
"""

from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import Assignment, Submission

User = get_user_model()


# ════════════════════════════════════════════════════════════════════════════
# Assignment Submission Services
# ════════════════════════════════════════════════════════════════════════════


@transaction.atomic
def create_assignment_submission(assignment, student, submission_file=None, submission_text="", submission_url=""):
    """
    Create an assignment submission.

    Args:
        assignment: Assignment instance
        student: User instance
        submission_file: Optional uploaded file
        submission_text: Optional submission text
        submission_url: Optional submission URL

    Returns:
        Submission: Created submission
    """
    submission = Submission.objects.create(
        assignment=assignment,
        student=student,
        submission_text=submission_text,
        submission_url=submission_url,
        submitted_at=timezone.now(),
        status="submitted",
    )

    if submission_file:
        submission.submission_file = submission_file
        submission.save()

    return submission


@transaction.atomic
def update_assignment_submission(submission, submission_file=None, submission_text=None, submission_url=None):
    """
    Update an assignment submission.

    Args:
        submission: Submission instance
        submission_file: Optional new file
        submission_text: Optional new text
        submission_url: Optional new URL

    Returns:
        Submission: Updated submission
    """
    if submission_file is not None:
        submission.submission_file = submission_file

    if submission_text is not None:
        submission.submission_text = submission_text

    if submission_url is not None:
        submission.submission_url = submission_url

    submission.submitted_at = timezone.now()
    submission.status = "submitted"
    submission.save()

    return submission


# ════════════════════════════════════════════════════════════════════════════
# Assignment Grading Services
# ════════════════════════════════════════════════════════════════════════════


@transaction.atomic
def grade_assignment_submission(submission, score, feedback, graded_by):
    """
    Grade an assignment submission.

    Args:
        submission: Submission instance
        score: Score value (Decimal or string)
        feedback: Feedback text
        graded_by: User grading the submission

    Returns:
        Submission: Graded submission
    """
    if isinstance(score, str):
        score = Decimal(score)

    submission.score = score
    submission.feedback = feedback
    submission.graded_by = graded_by
    submission.graded_at = timezone.now()
    submission.status = "graded"
    submission.save()

    return submission


@transaction.atomic
def bulk_grade_assignment_submissions(submission_ids, scores, feedback_list, graded_by):
    """
    Grade multiple assignment submissions at once.

    Args:
        submission_ids: List of submission IDs
        scores: List of scores
        feedback_list: List of feedback texts
        graded_by: User grading the submissions

    Returns:
        int: Number of submissions graded
    """
    submissions = Submission.objects.filter(id__in=submission_ids)
    count = 0

    for submission, score, feedback in zip(submissions, scores, feedback_list):
        grade_assignment_submission(submission, score, feedback, graded_by)
        count += 1

    return count


# ════════════════════════════════════════════════════════════════════════════
# Assignment to Students Services
# ════════════════════════════════════════════════════════════════════════════


@transaction.atomic
def assign_to_students(assignment, student_ids):
    """
    Assign assignment to multiple students.

    Args:
        assignment: Assignment instance
        student_ids: List of student user IDs

    Returns:
        int: Number of students assigned
    """
    users = User.objects.filter(id__in=student_ids)
    count = 0

    for user in users:
        if not assignment.allowed_students.filter(id=user.id).exists():
            assignment.allowed_students.add(user)
            count += 1

    return count


@transaction.atomic
def assign_to_group(assignment, student_group):
    """
    Assign assignment to all students in a group.

    Args:
        assignment: Assignment instance
        student_group: StudentGroup instance

    Returns:
        int: Number of students assigned
    """
    students = student_group.students.all()
    count = 0

    for student in students:
        if not assignment.allowed_students.filter(id=student.id).exists():
            assignment.allowed_students.add(student)
            count += 1

    return count


# ════════════════════════════════════════════════════════════════════════════
# Assignment Query Services
# ════════════════════════════════════════════════════════════════════════════


def get_assignment_submissions(assignment, status=None, group_name=None):
    """
    Get submissions for an assignment.

    Args:
        assignment: Assignment instance
        status: Optional status filter
        group_name: Optional group filter

    Returns:
        QuerySet: Submission queryset
    """
    qs = Submission.objects.filter(
        assignment=assignment
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
            course=assignment.course,
            role="student",
            group_name=group_name,
        ).values_list("user_id", flat=True)
        qs = qs.filter(student_id__in=student_ids)

    return qs.order_by("-submitted_at")


def get_pending_assignment_submissions(teacher, organization=None):
    """
    Get pending assignment submissions for teacher.

    Args:
        teacher: User instance
        organization: Optional organization filter

    Returns:
        QuerySet: Submission queryset
    """
    qs = Submission.objects.filter(
        assignment__created_by=teacher,
        status="submitted",
    ).select_related("assignment", "student")

    if organization is not None:
        qs = qs.filter(assignment__course__organization=organization)

    return qs.order_by("submitted_at")


def can_student_submit_assignment(assignment, student):
    """
    Check if student can submit to an assignment.

    Args:
        assignment: Assignment instance
        student: User instance

    Returns:
        tuple: (can_submit: bool, reason: str)
    """
    # Check if assignment is published
    if assignment.status != "published":
        return False, "assignment_not_published"

    # Check if student is allowed
    if not assignment.allowed_students.filter(id=student.id).exists():
        # Check if student is in course
        from apps.courses.models import CourseMembership
        if not CourseMembership.objects.filter(
            course=assignment.course,
            user=student,
            role="student",
        ).exists():
            return False, "not_allowed"

    # Check deadline if exists
    if assignment.deadline and timezone.now() > assignment.deadline:
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
