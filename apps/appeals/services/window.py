"""
Apellyasiya pəncərəsi — imtahan bitdikdən sonra yalnız N gün ərzində.
"""

from datetime import datetime, time, timedelta

from django.utils import timezone

from apps.appeals.constants import APPEAL_WINDOW_DAYS
from apps.exams.public import ATTEMPT_FINISHED_STATUSES

# Apellyasiyaya icazə verilən attempt statusları (bitmiş cəhdlər) — exams
# fasadındakı tək mənbədən törədilir.
APPEAL_ELIGIBLE_ATTEMPT_STATUSES = frozenset(ATTEMPT_FINISHED_STATUSES)


def _finished_at(attempt):
    return getattr(attempt, "finished_at", None)


def appeal_deadline(attempt):
    """Apellyasiya üçün son tarix və ya None.

    Qayda date-based-dir: tələbə imtahanı 7-də bitiribsə, 8/9/10-da müraciət
    edə bilər; 11-də həmin fənn üzrə apellyasiya bağlanır.
    """
    finished = _finished_at(attempt)
    if not finished:
        return None
    local_finished = timezone.localtime(finished)
    deadline_date = local_finished.date() + timedelta(days=APPEAL_WINDOW_DAYS)
    return timezone.make_aware(
        datetime.combine(deadline_date, time.max),
        timezone.get_current_timezone(),
    )


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
