"""
Business logic layer for labs app.
This module contains service functions that encapsulate business operations.
"""

from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import Lab, LabAssignment, LabSubmission, LabAnswer

User = get_user_model()


# ════════════════════════════════════════════════════════════════════════════
# Lab Submission Services
# ════════════════════════════════════════════════════════════════════════════


@transaction.atomic
def create_lab_submission(assignment, uploaded_file=None):
    """
    Create a lab submission for an assignment.

    Args:
        assignment: LabAssignment instance
        uploaded_file: Optional uploaded file

    Returns:
        LabSubmission: Created submission
    """
    submission = LabSubmission.objects.create(
        assignment=assignment,
        submitted_at=timezone.now(),
        status="submitted",
    )

    if uploaded_file:
        submission.submission_file = uploaded_file
        submission.save()

    return submission


@transaction.atomic
def update_lab_submission(submission, uploaded_file=None):
    """
    Update a lab submission with new file.

    Args:
        submission: LabSubmission instance
        uploaded_file: New uploaded file

    Returns:
        LabSubmission: Updated submission
    """
    if uploaded_file:
        submission.submission_file = uploaded_file

    submission.submitted_at = timezone.now()
    submission.status = "submitted"
    submission.save()

    return submission


@transaction.atomic
def auto_save_lab_answers(assignment, answers_data):
    """
    Auto-save lab answers for an assignment.

    Args:
        assignment: LabAssignment instance
        answers_data: Dict of {question_id: answer_text}

    Returns:
        int: Number of answers saved
    """
    count = 0
    active_submission = assignment.submissions.order_by("-attempt_number", "-submitted_at").first()
    attempt_number = getattr(active_submission, "attempt_number", None) or 1

    for question_id, answer_text in answers_data.items():
        LabAnswer.objects.update_or_create(
            lab=assignment.lab,
            question_id=question_id,
            student=assignment.student,
            attempt_number=attempt_number,
            defaults={
                "submission": active_submission,
                "answer": answer_text,
                "is_draft": True,
            },
        )
        count += 1

    return count


# ════════════════════════════════════════════════════════════════════════════
# Lab Grading Services
# ════════════════════════════════════════════════════════════════════════════


@transaction.atomic
def grade_lab_submission(submission, score, feedback, graded_by):
    """
    Grade a lab submission.

    Args:
        submission: LabSubmission instance
        score: Score value (Decimal or string)
        feedback: Feedback text
        graded_by: User grading the submission

    Returns:
        LabSubmission: Graded submission
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
def grade_lab_answer(answer, score, feedback=None):
    """
    Grade a single lab answer.

    Args:
        answer: LabAnswer instance
        score: Score value
        feedback: Optional feedback

    Returns:
        LabAnswer: Graded answer
    """
    if isinstance(score, str):
        score = Decimal(score)

    answer.score = score
    if feedback is not None:
        answer.feedback = feedback
    answer.save()

    return answer


def calculate_lab_total_score(assignment):
    """
    Calculate total score for a lab assignment.

    Args:
        assignment: LabAssignment instance

    Returns:
        Decimal: Total score
    """
    answers = assignment.answers.all()
    total_score = Decimal("0")

    for answer in answers:
        if answer.score is not None:
            total_score += answer.score

    # Add submission score if exists
    submission = assignment.submissions.filter(status="graded").first()
    if submission and submission.score:
        total_score += submission.score

    return total_score


# ════════════════════════════════════════════════════════════════════════════
# Lab Assignment Services
# ════════════════════════════════════════════════════════════════════════════


@transaction.atomic
def create_lab_assignments_for_students(lab, student_ids):
    """
    Create lab assignments for multiple students.

    Args:
        lab: Lab instance
        student_ids: List of student user IDs

    Returns:
        tuple: (created_count, existing_count)
    """
    users = User.objects.filter(id__in=student_ids)
    created_count = 0
    existing_count = 0

    for user in users:
        assignment, created = LabAssignment.objects.get_or_create(
            lab=lab,
            student=user,
            defaults={
                "assigned_at": timezone.now(),
            },
        )

        if created:
            created_count += 1
        else:
            existing_count += 1

    return created_count, existing_count


def get_lab_assignment_for_student(lab, student):
    """
    Get or create lab assignment for student.

    Args:
        lab: Lab instance
        student: User instance

    Returns:
        LabAssignment: Assignment instance
    """
    assignment, created = LabAssignment.objects.get_or_create(
        lab=lab,
        student=student,
        defaults={
            "assigned_at": timezone.now(),
        },
    )

    return assignment


# ════════════════════════════════════════════════════════════════════════════
# Lab Query Services
# ════════════════════════════════════════════════════════════════════════════


def get_lab_submissions(lab, status=None, group_name=None):
    """
    Get submissions for a lab.

    Args:
        lab: Lab instance
        status: Optional status filter
        group_name: Optional group filter

    Returns:
        QuerySet: Submission queryset
    """
    qs = LabSubmission.objects.filter(
        assignment__lab=lab
    ).select_related(
        "assignment__student",
        "assignment__student__profile",
        "graded_by"
    )

    if status:
        qs = qs.filter(status=status)

    if group_name:
        from apps.courses.models import CourseMembership
        student_ids = CourseMembership.objects.filter(
            course=lab.course,
            role="student",
            group_name=group_name,
        ).values_list("user_id", flat=True)
        qs = qs.filter(assignment__student_id__in=student_ids)

    return qs.order_by("-submitted_at")


def get_pending_lab_submissions(teacher, organization=None):
    """
    Get pending lab submissions for teacher.

    Args:
        teacher: User instance
        organization: Optional organization filter

    Returns:
        QuerySet: Submission queryset
    """
    qs = LabSubmission.objects.filter(
        assignment__lab__created_by=teacher,
        status="submitted",
    ).select_related("assignment__lab", "assignment__student")

    if organization is not None:
        qs = qs.filter(assignment__lab__course__organization=organization)

    return qs.order_by("submitted_at")


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
