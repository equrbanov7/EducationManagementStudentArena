"""Server-authoritative per-question timer (EXAM-P1-04, Seq4).

Köhnə model YALNIZ client idi: deadline ``Date.now() + limit`` ilə brauzerdə
hesablanırdı — devtools ilə timer silinib vaxtlı sualda sonsuz oturmaq olurdu.

İndi sual İLK dəfə göstəriləndə server ``attempt.question_timing``-də
``{question_id: started_at}`` qeyd edir (ilk yazı qalır — yenidən baxış/reload
timer-i sıfırlamır) və countdown server qalığından hesablanır. Saxlama yolunda
müddəti (limit + grace) keçmiş sualın POST sahələri saxlanmır.

Geriyə-uyğunluq: limitsiz sual/imtahan üçün heç nə yazılmır və heç nə bloklanmır;
``question_timing`` boş köhnə cəhdlər əvvəlki kimi işləyir (yalnız client limit).
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.exams.question_timer_protocol import uses_strict_question_timer


def _grace_seconds() -> int:
    """Şəbəkə gecikməsi/son-saniyə autosave üçün server tərəfi güzəşt."""
    return int(getattr(settings, "EXAM_QUESTION_TIMER_GRACE_SECONDS", 10))


def question_time_limit_seconds(question) -> int:
    return int(getattr(question, "effective_time_limit", 0) or 0)


def _parse_started_at(raw):
    if not isinstance(raw, str):
        return None
    try:
        value = parse_datetime(raw)
    except (TypeError, ValueError):
        return None
    if value is not None and timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _question_started_at(attempt, question):
    raw = (attempt.question_timing or {}).get(str(question.id))
    if not raw:
        return None
    return _parse_started_at(raw)


def question_timer_start_required(attempt, question) -> bool:
    """Yeni-protokol attempt-də vaxtlı sual hələ başlanmayıb?"""
    return bool(
        question_time_limit_seconds(question)
        and uses_strict_question_timer(attempt.question_timing)
        and _question_started_at(attempt, question) is None
    )


def mark_question_seen(attempt, question) -> dict:
    """Sualın İLK göstərilməsini qeyd et; server countdown məlumatını qaytar.

    İdempotentdir: təkrar çağırışlar (slide-a qayıdış, reload, ikinci tab)
    İLK ``started_at``-ı saxlayır — timer yenidən BAŞLAMIR.
    """
    limit = question_time_limit_seconds(question)

    key = str(question.id)
    # Eyni attempt-in iki slide/tab siqnalı paralel gələndə JSON read-modify-
    # write bir-birinin key-ini itirməsin və eyni sualın ilk timestamp-ı
    # daha gec request tərəfindən üstə yazılmasın.
    with transaction.atomic():
        locked_attempt = type(attempt).objects.select_for_update().only("question_timing", "status").get(pk=attempt.pk)
        timing = dict(locked_attempt.question_timing or {})
        if locked_attempt.is_finished:
            attempt.status = locked_attempt.status
            attempt.question_timing = timing
            return {
                "limit_seconds": limit or None,
                "remaining_seconds": 0 if limit else None,
                "attempt_finished": True,
            }
        if not limit:
            attempt.question_timing = timing
            return {"limit_seconds": None, "remaining_seconds": None, "attempt_finished": False}
        if key not in timing or _parse_started_at(timing.get(key)) is None:
            timing[key] = timezone.now().isoformat()
            locked_attempt.question_timing = timing
            locked_attempt.save(update_fields=["question_timing"])

    # Caller eyni instance-dan dərhal deadline hesablayır; lock-lanmış state-i
    # ona da ötür ki, ayrı refresh/query lazım olmasın.
    attempt.question_timing = timing

    started_at = _parse_started_at(timing[key])
    elapsed = (timezone.now() - started_at).total_seconds()
    remaining = max(0, int(limit - elapsed))
    return {"limit_seconds": limit, "remaining_seconds": remaining, "attempt_finished": False}


def question_timer_expired(attempt, question) -> bool:
    """Server deadline (started_at + limit + grace) keçibsə True.

    Limitsiz sual və ya heç göstərilməmiş (started_at yox) sual üçün False —
    köhnə cəhdlər və signal göndərməyən köhnə client geriyə-uyğun qalır.
    """
    limit = question_time_limit_seconds(question)
    if not limit:
        return False
    started_at = _question_started_at(attempt, question)
    if started_at is None:
        return False
    deadline = started_at + timedelta(seconds=limit + _grace_seconds())
    return timezone.now() > deadline


__all__ = [
    "mark_question_seen",
    "question_timer_expired",
    "question_timer_start_required",
    "question_time_limit_seconds",
]
