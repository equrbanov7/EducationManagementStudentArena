"""
Apellyasiya pəncərəsi — imtahan bitdikdən sonra yalnız N gün ərzində.
"""

from datetime import timedelta

from django.utils import timezone

from apps.appeals.constants import APPEAL_WINDOW_DAYS

# Apellyasiyaya icazə verilən attempt statusları (bitmiş cəhdlər).
APPEAL_ELIGIBLE_ATTEMPT_STATUSES = frozenset({"submitted", "expired", "graded"})


def _finished_at(attempt):
    return getattr(attempt, "finished_at", None)


def appeal_deadline(attempt):
    """Apellyasiya üçün son tarix (finished_at + APPEAL_WINDOW_DAYS) və ya None."""
    finished = _finished_at(attempt)
    if not finished:
        return None
    return finished + timedelta(days=APPEAL_WINDOW_DAYS)


def is_within_appeal_window(attempt, *, at_time=None):
    """Attempt bitibsə VƏ son tarix keçməyibsə True."""
    if getattr(attempt, "status", None) not in APPEAL_ELIGIBLE_ATTEMPT_STATUSES:
        return False
    deadline = appeal_deadline(attempt)
    if deadline is None:
        return False
    return (at_time or timezone.now()) <= deadline


def remaining_window_seconds(attempt, *, at_time=None):
    """Pəncərənin bitməsinə qalan saniyə (keçibsə 0)."""
    deadline = appeal_deadline(attempt)
    if deadline is None:
        return 0
    delta = deadline - (at_time or timezone.now())
    return max(0, int(delta.total_seconds()))


__all__ = [
    "APPEAL_ELIGIBLE_ATTEMPT_STATUSES",
    "appeal_deadline",
    "is_within_appeal_window",
    "remaining_window_seconds",
]
