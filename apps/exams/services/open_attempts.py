"""Tələbənin «hazırda imtahan yazır» vəziyyəti — imtahandan kənar səthlər üçün.

Təhlükəsizlik auditi 2026-10-07: AI köməkçinin vidceti ``take_exam`` səhifəsində
gizlədilirdi, amma çat endpoint-i cəhd açıq ikən başqa tabdan işləyirdi. Bu modul
çağırana (``apps.ai_assistant``) cəhdin YAZI PƏNCƏRƏSİ hələ açıqdırmı sualına cavab
verir — qayda imtahanın öz yazı yolu ilə eynidir (``attempt_deadline``):

* müddətli cəhd — ``deadline + təhvil grace``-ə qədər;
* müddətsiz cəhd — imtahanın ``end_datetime``-ına qədər; o da yoxdursa başlanğıcdan
  ``UNTIMED_OPEN_ATTEMPT_HOURS`` saat (tərk edilmiş müddətsiz cəhd tələbəni əbədi
  bloklamasın);
* müəllimin sınaq cəhdi (``is_trial``), deaktiv/silinmiş imtahan sayılmır.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.exams.domain.attempt_deadline import submit_grace

#: Müddətsiz və bitmə vaxtı olmayan açıq cəhdin «aktiv» sayıldığı tavan.
UNTIMED_OPEN_ATTEMPT_HOURS = 6

_OPEN_STATUSES = ("draft", "in_progress")


def _write_window_open(attempt, now) -> bool:
    deadline = attempt.deadline_at
    if deadline is not None:
        return now < deadline + submit_grace()
    end = getattr(attempt.exam, "end_datetime", None)
    started = attempt.started_at
    if end and (not started or end > started):
        return now <= end + submit_grace()
    return bool(started) and now - started < timedelta(hours=UNTIMED_OPEN_ATTEMPT_HOURS)


def user_has_open_exam_attempt(user, *, now=None) -> bool:
    """İstifadəçinin yazı pəncərəsi açıq rəsmi (sınaq olmayan) imtahan cəhdi varmı."""
    if not getattr(user, "is_authenticated", False):
        return False
    from apps.exams.models import ExamAttempt

    now = now or timezone.now()
    attempts = (
        ExamAttempt.objects.filter(
            user=user,
            status__in=_OPEN_STATUSES,
            is_trial=False,
            exam__is_active=True,
            exam__is_deleted=False,
        )
        .select_related("exam")
        .order_by("-started_at")[:10]
    )
    return any(_write_window_open(attempt, now) for attempt in attempts)


__all__ = ["UNTIMED_OPEN_ATTEMPT_HOURS", "user_has_open_exam_attempt"]
