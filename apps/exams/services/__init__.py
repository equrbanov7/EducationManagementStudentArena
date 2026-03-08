from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.accounts.models import ProfileRole
from apps.exams.models import ExamAnswer, ExamAttempt


def get_active_attempt_for_user(exam, user):
    return exam.attempts.filter(user=user, status__in=["draft", "in_progress"]).order_by("-started_at").first()


def get_finished_attempts_for_user(exam, user):
    return exam.attempts.filter(user=user, status__in=["submitted", "expired"]).order_by("-started_at")


def can_user_start_new_attempt(exam, user):
    active_attempt = get_active_attempt_for_user(exam, user)
    if active_attempt:
        return False, "active_attempt_exists"

    max_attempts = exam.max_attempts_per_user
    if max_attempts and get_finished_attempts_for_user(exam, user).count() >= max_attempts:
        return False, "max_attempts_reached"

    return True, "ok"


@transaction.atomic
def create_exam_attempt(exam, user):
    last_attempt = exam.attempts.filter(user=user).order_by("-attempt_number").first()
    next_attempt_number = (last_attempt.attempt_number + 1) if last_attempt else 1
    return ExamAttempt.objects.create(
        user=user,
        exam=exam,
        attempt_number=next_attempt_number,
        status="in_progress",
    )


@transaction.atomic
def submit_exam_attempt(attempt):
    attempt.mark_finished(status="submitted")
    return attempt


def calculate_attempt_score(attempt):
    total_score = Decimal("0")
    for answer in attempt.answers.select_related("question"):
        if answer.teacher_score is not None:
            total_score += Decimal(str(answer.teacher_score))
        elif answer.question.exam.exam_type == "test" and answer.is_correct:
            total_score += Decimal(str(answer.question.points))
    return total_score


@transaction.atomic
def grade_exam_answer(answer, score, graded_by=None, feedback=None):
    if isinstance(score, str):
        score = Decimal(score)
    answer.teacher_score = int(Decimal(score))
    if feedback is not None:
        answer.teacher_feedback = feedback
        answer.save(update_fields=["teacher_score", "teacher_feedback"])
    else:
        answer.save(update_fields=["teacher_score"])
    return answer


@transaction.atomic
def bulk_grade_answers(answer_ids, scores, graded_by=None):
    answers = ExamAnswer.objects.filter(id__in=answer_ids)
    count = 0
    for answer, score in zip(answers, scores):
        grade_exam_answer(answer, score, graded_by)
        count += 1
    return count


def is_teacher_user(user):
    if user.is_superuser or getattr(user, "is_superadmin", False):
        return True

    if hasattr(user, "has_role"):
        return user.has_role(ProfileRole.TEACHER) or user.has_role(ProfileRole.ASSISTANT_TEACHER)

    profile = getattr(user, "profile", None)
    return getattr(profile, "role", None) in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}


def can_user_access_exam(exam, user):
    if is_teacher_user(user) or exam.author == user:
        return True

    if not exam.is_active:
        return False

    if exam.allowed_users.filter(id=user.id).exists():
        return True

    if exam.allowed_groups.filter(students=user).exists():
        return True

    if exam.course:
        from apps.courses.models import CourseMembership

        return CourseMembership.objects.filter(course=exam.course, user=user, role="student").exists()

    return False


def parse_score_value(value, *, default=None):
    if value in (None, ""):
        return default

    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return default


__all__ = [
    "bulk_grade_answers",
    "calculate_attempt_score",
    "can_user_access_exam",
    "can_user_start_new_attempt",
    "create_exam_attempt",
    "get_active_attempt_for_user",
    "get_finished_attempts_for_user",
    "grade_exam_answer",
    "is_teacher_user",
    "parse_score_value",
    "submit_exam_attempt",
]
