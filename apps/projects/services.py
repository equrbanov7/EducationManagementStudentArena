"""
Business logic layer for projects app.
This module contains service functions that encapsulate business operations.
"""

from django.utils import timezone

from apps.task_submission_core.services import parse_score_value  # noqa: F401 – re-exported
from apps.task_submission_core.services import (
    apply_grade,
    assign_task_to_group,
    assign_task_to_students,
    bulk_grade_submissions,
    create_submission,
    get_pending_task_submissions,
    get_task_submissions,
    update_submission,
)

from .models import ProjectSubmission

# ════════════════════════════════════════════════════════════════════════════
# Project Submission Services
# ════════════════════════════════════════════════════════════════════════════


def create_project_submission(
    project,
    student,
    submission_file=None,
    submission_text="",
    submission_url="",
    *,
    original_file_name="",
):
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
    return create_submission(
        submission_model=ProjectSubmission,
        task_field_name="project",
        task=project,
        student_field_name="student",
        student=student,
        submitted_status="pending",
        submission_file=submission_file,
        submission_text=submission_text,
        submission_url=submission_url,
        original_file_name=original_file_name,
    )


def update_project_submission(
    submission,
    submission_file=None,
    submission_text=None,
    submission_url=None,
    *,
    original_file_name="",
):
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
    return update_submission(
        submission,
        submitted_status="pending",
        submission_file=submission_file,
        submission_text=submission_text,
        submission_url=submission_url,
        original_file_name=original_file_name,
    )


# ════════════════════════════════════════════════════════════════════════════
# Project Grading Services
# ════════════════════════════════════════════════════════════════════════════


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
    return apply_grade(submission, score, feedback, graded_by, graded_status="graded")


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
    return bulk_grade_submissions(submissions, scores, feedback_list, graded_by, graded_status="graded")


# ════════════════════════════════════════════════════════════════════════════
# Project Assignment Services
# ════════════════════════════════════════════════════════════════════════════


def assign_project_to_students(project, student_ids):
    """
    Assign project to multiple students.

    Args:
        project: Project instance
        student_ids: List of student user IDs

    Returns:
        int: Number of students assigned
    """
    return assign_task_to_students(project, student_ids)


def assign_project_to_group(project, student_group):
    """
    Assign project to all students in a group.

    Args:
        project: Project instance
        student_group: StudentGroup instance

    Returns:
        int: Number of students assigned
    """
    return assign_task_to_group(project, student_group)


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
    return get_task_submissions(
        submission_model=ProjectSubmission,
        task_field_name="project",
        task=project,
        student_field_name="student",
        status=status,
        group_name=group_name,
    )


def get_pending_project_submissions(teacher, organization=None):
    """
    Get pending project submissions for teacher.

    Args:
        teacher: User instance
        organization: Optional organization filter

    Returns:
        QuerySet: Submission queryset
    """
    return get_pending_task_submissions(
        submission_model=ProjectSubmission,
        task_field_name="project",
        student_field_name="student",
        teacher_lookup="project__course__owner",
        teacher=teacher,
        pending_status="pending",
        organization=organization,
    )


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
