"""
Business logic layer for assignments app.
This module contains service functions that encapsulate business operations.
"""

from django.utils import timezone

from apps.task_submission_core.services import (  # noqa: F401
    apply_grade,
    assign_task_to_group,
    assign_task_to_students,
    bulk_grade_submissions,
    create_submission,
    get_pending_task_submissions,
    get_task_submissions,
    parse_score_value,
    update_submission,
)

from .models import Submission

# ════════════════════════════════════════════════════════════════════════════
# Assignment Submission Services
# ════════════════════════════════════════════════════════════════════════════


def create_assignment_submission(
    assignment,
    student,
    submission_file=None,
    submission_text="",
    submission_url="",
    *,
    original_file_name="",
    attempt_number=None,
):
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
    extra_create_fields = {}
    if attempt_number is not None:
        extra_create_fields["attempt_number"] = attempt_number

    return create_submission(
        submission_model=Submission,
        task_field_name="assignment",
        task=assignment,
        student_field_name="user",
        student=student,
        submitted_status="submitted",
        submission_file=submission_file,
        submission_text=submission_text,
        submission_url=submission_url,
        original_file_name=original_file_name,
        extra_create_fields=extra_create_fields or None,
    )


def update_assignment_submission(
    submission,
    submission_file=None,
    submission_text=None,
    submission_url=None,
    *,
    original_file_name="",
):
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
    return update_submission(
        submission,
        submitted_status="submitted",
        submission_file=submission_file,
        submission_text=submission_text,
        submission_url=submission_url,
        original_file_name=original_file_name,
    )


# ════════════════════════════════════════════════════════════════════════════
# Assignment Grading Services
# ════════════════════════════════════════════════════════════════════════════


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
    return apply_grade(submission, score, feedback, graded_by, graded_status="graded")


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
    return bulk_grade_submissions(submissions, scores, feedback_list, graded_by, graded_status="graded")


# ════════════════════════════════════════════════════════════════════════════
# Assignment to Students Services
# ════════════════════════════════════════════════════════════════════════════


def assign_to_students(assignment, student_ids):
    """
    Assign assignment to multiple students.

    Args:
        assignment: Assignment instance
        student_ids: List of student user IDs

    Returns:
        int: Number of students assigned
    """
    return assign_task_to_students(assignment, student_ids)


def assign_to_group(assignment, student_group):
    """
    Assign assignment to all students in a group.

    Args:
        assignment: Assignment instance
        student_group: StudentGroup instance

    Returns:
        int: Number of students assigned
    """
    return assign_task_to_group(assignment, student_group)


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
    return get_task_submissions(
        submission_model=Submission,
        task_field_name="assignment",
        task=assignment,
        student_field_name="user",
        status=status,
        group_name=group_name,
    )


def get_pending_assignment_submissions(teacher, organization=None):
    """
    Get pending assignment submissions for teacher.

    Args:
        teacher: User instance
        organization: Optional organization filter

    Returns:
        QuerySet: Submission queryset
    """
    return get_pending_task_submissions(
        submission_model=Submission,
        task_field_name="assignment",
        student_field_name="user",
        teacher_lookup="assignment__created_by",
        teacher=teacher,
        pending_status="submitted",
        organization=organization,
    )


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
    if not assignment.assigned_students.filter(id=student.id).exists():
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
