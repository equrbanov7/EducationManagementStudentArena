"""
Business logic layer for exams app.
This module contains service functions that encapsulate business operations.
"""

from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import ProfileRole

from .models import Exam, ExamAttempt, ExamQuestion, ExamAnswer

User = get_user_model()


# ════════════════════════════════════════════════════════════════════════════
# Exam Attempt Management Services
# ════════════════════════════════════════════════════════════════════════════


def get_active_attempt_for_user(exam, user):
    """
    Get active (draft or in_progress) attempt for user.

    Args:
        exam: Exam instance
        user: User instance

    Returns:
        ExamAttempt or None
    """
    return exam.attempts.filter(
        user=user,
        status__in=["draft", "in_progress"]
    ).order_by("-started_at").first()


def get_finished_attempts_for_user(exam, user):
    """
    Get finished (submitted or expired) attempts for user.

    Args:
        exam: Exam instance
        user: User instance

    Returns:
        QuerySet: Finished attempts
    """
    return exam.attempts.filter(
        user=user,
        status__in=["submitted", "expired"]
    ).order_by("-started_at")


def can_user_start_new_attempt(exam, user):
    """
    Check if user can start a new attempt.

    Args:
        exam: Exam instance
        user: User instance

    Returns:
        tuple: (can_start: bool, reason: str)
    """
    # Check if there's an active attempt
    active_attempt = get_active_attempt_for_user(exam, user)
    if active_attempt:
        return False, "active_attempt_exists"

    # Check max attempts limit
    max_attempts = exam.max_attempts_per_user
    if max_attempts:
        finished_count = get_finished_attempts_for_user(exam, user).count()
        if finished_count >= max_attempts:
            return False, "max_attempts_reached"

    return True, "ok"


@transaction.atomic
def create_exam_attempt(exam, user):
    """
    Create a new exam attempt for user.

    Args:
        exam: Exam instance
        user: User instance

    Returns:
        ExamAttempt: Created attempt
    """
    # Calculate next attempt number
    last_attempt = exam.attempts.filter(user=user).order_by("-attempt_number").first()
    next_attempt_number = (last_attempt.attempt_number + 1) if last_attempt else 1

    # Create attempt
    attempt = ExamAttempt.objects.create(
        user=user,
        exam=exam,
        attempt_number=next_attempt_number,
        status="in_progress",
    )

    return attempt


@transaction.atomic
def submit_exam_attempt(attempt):
    """
    Submit an exam attempt.

    Args:
        attempt: ExamAttempt instance

    Returns:
        ExamAttempt: Updated attempt
    """
    attempt.status = "submitted"
    attempt.submitted_at = timezone.now()
    attempt.save()

    return attempt


# ════════════════════════════════════════════════════════════════════════════
# Exam Grading Services
# ════════════════════════════════════════════════════════════════════════════


def calculate_attempt_score(attempt):
    """
    Calculate total score for an attempt.

    Args:
        attempt: ExamAttempt instance

    Returns:
        Decimal: Total score
    """
    answers = attempt.answers.all()
    total_score = Decimal("0")

    for answer in answers:
        if answer.score is not None:
            total_score += answer.score

    return total_score


@transaction.atomic
def grade_exam_answer(answer, score, graded_by):
    """
    Grade an exam answer.

    Args:
        answer: ExamAnswer instance
        score: Score value (Decimal or string)
        graded_by: User grading the answer

    Returns:
        ExamAnswer: Graded answer
    """
    if isinstance(score, str):
        score = Decimal(score)

    answer.score = score
    answer.graded_by = graded_by
    answer.graded_at = timezone.now()
    answer.save()

    return answer


@transaction.atomic
def bulk_grade_answers(answer_ids, scores, graded_by):
    """
    Grade multiple answers at once.

    Args:
        answer_ids: List of answer IDs
        scores: List of scores (same order as answer_ids)
        graded_by: User grading the answers

    Returns:
        int: Number of answers graded
    """
    answers = ExamAnswer.objects.filter(id__in=answer_ids)
    count = 0

    for answer, score in zip(answers, scores):
        grade_exam_answer(answer, score, graded_by)
        count += 1

    return count


# ════════════════════════════════════════════════════════════════════════════
# Exam Access Control Services
# ════════════════════════════════════════════════════════════════════════════


def is_teacher_user(user):
    """Check if user has teacher role."""
    if user.is_superuser or getattr(user, "is_superadmin", False):
        return True

    if hasattr(user, "has_role"):
        return user.has_role(ProfileRole.TEACHER) or user.has_role(ProfileRole.ASSISTANT_TEACHER)

    profile = getattr(user, "profile", None)
    role = getattr(profile, "role", None)
    return role in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}


def can_user_access_exam(exam, user):
    """
    Check if user can access an exam.

    Args:
        exam: Exam instance
        user: User instance

    Returns:
        bool: True if user can access
    """
    # Teachers and authors can always access
    if is_teacher_user(user) or exam.author == user:
        return True

    # Check if exam is active
    if not exam.is_active:
        return False

    # Check if user is in allowed users
    if exam.allowed_users.filter(id=user.id).exists():
        return True

    # Check if user is in allowed groups
    if exam.allowed_groups.filter(students=user).exists():
        return True

    # Check if user is enrolled in course
    if exam.course:
        from apps.courses.models import CourseMembership
        if CourseMembership.objects.filter(
            course=exam.course,
            user=user,
            role="student",
        ).exists():
            return True

    return False


def can_user_view_attempt(attempt, user):
    """
    Check if user can view an attempt.

    Args:
        attempt: ExamAttempt instance
        user: User instance

    Returns:
        bool: True if user can view
    """
    # Own attempts
    if attempt.user == user:
        return True

    # Teacher/author can view all attempts
    if is_teacher_user(user) or attempt.exam.author == user:
        return True

    return False


# ════════════════════════════════════════════════════════════════════════════
# Exam Query Services
# ════════════════════════════════════════════════════════════════════════════


def get_exams_for_teacher(teacher, organization=None):
    """
    Get exams created by teacher.

    Args:
        teacher: User instance
        organization: Optional organization filter

    Returns:
        QuerySet: Exam queryset
    """
    qs = Exam.objects.filter(author=teacher)

    if organization is not None:
        qs = qs.filter(organization=organization)

    return qs.select_related("author", "course").order_by("-created_at")


def get_attempts_for_exam(exam, status=None):
    """
    Get attempts for an exam.

    Args:
        exam: Exam instance
        status: Optional status filter

    Returns:
        QuerySet: Attempt queryset
    """
    qs = exam.attempts.select_related("user", "user__profile")

    if status:
        qs = qs.filter(status=status)

    return qs.order_by("-started_at")


def get_pending_grading_attempts(teacher, organization=None):
    """
    Get attempts pending grading for teacher.

    Args:
        teacher: User instance
        organization: Optional organization filter

    Returns:
        QuerySet: Attempt queryset
    """
    qs = ExamAttempt.objects.filter(
        exam__author=teacher,
        status="submitted",
    ).select_related("user", "exam")

    if organization is not None:
        qs = qs.filter(exam__organization=organization)

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
