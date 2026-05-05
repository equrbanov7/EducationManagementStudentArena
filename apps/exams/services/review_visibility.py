from django.utils import timezone

from core.helpers import REVIEW_EDIT_LOCK_WINDOW


def resolve_exam_attempt_name_visibility(attempt, *, current_time=None):
    now = current_time or timezone.now()

    if attempt.exam.exam_type in {"test", "coding"}:
        return True, 0

    organization = getattr(attempt.exam, "organization", None)
    if organization is not None and organization.written_exam_identity_reveal_enabled:
        return True, 0

    if not attempt.checked_by_teacher:
        return False, 0

    if not attempt.teacher_checked_at:
        return True, 0

    reveal_at = attempt.teacher_checked_at + REVIEW_EDIT_LOCK_WINDOW
    if now >= reveal_at:
        return True, 0

    seconds_remaining = max(0, int((reveal_at - now).total_seconds()))
    return False, seconds_remaining


def resolve_exam_attempt_review_window_seconds(attempt, *, current_time=None):
    if attempt.exam.exam_type in {"test", "coding"}:
        return 0

    if not attempt.checked_by_teacher or not attempt.teacher_checked_at:
        return 0

    now = current_time or timezone.now()
    reveal_at = attempt.teacher_checked_at + REVIEW_EDIT_LOCK_WINDOW
    if now >= reveal_at:
        return 0

    return max(0, int((reveal_at - now).total_seconds()))


def attempt_review_window_locked(attempt, *, current_time=None):
    if attempt.exam.exam_type in {"test", "coding"}:
        return False

    if not attempt.checked_by_teacher:
        return False

    return resolve_exam_attempt_review_window_seconds(attempt, current_time=current_time) == 0 and bool(
        attempt.teacher_checked_at
    )
