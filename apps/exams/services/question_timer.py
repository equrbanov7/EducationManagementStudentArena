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
from django.utils import timezone
from django.utils.dateparse import parse_datetime


def _grace_seconds() -> int:
    """Şəbəkə gecikməsi/son-saniyə autosave üçün server tərəfi güzəşt."""
    return int(getattr(settings, "EXAM_QUESTION_TIMER_GRACE_SECONDS", 10))


def question_time_limit_seconds(question) -> int:
    return int(getattr(question, "effective_time_limit", 0) or 0)


def _question_started_at(attempt, question):
    raw = (attempt.question_timing or {}).get(str(question.id))
    if not raw:
        return None
    return parse_datetime(raw)


def mark_question_seen(attempt, question) -> dict:
    """Sualın İLK göstərilməsini qeyd et; server countdown məlumatını qaytar.

    İdempotentdir: təkrar çağırışlar (slide-a qayıdış, reload, ikinci tab)
    İLK ``started_at``-ı saxlayır — timer yenidən BAŞLAMIR.
    """
    limit = question_time_limit_seconds(question)
    if not limit:
        return {"limit_seconds": None, "remaining_seconds": None}

    key = str(question.id)
    attempt.refresh_from_db(fields=["question_timing"])
    timing = dict(attempt.question_timing or {})
    if key not in timing:
        timing[key] = timezone.now().isoformat()
        attempt.question_timing = timing
        attempt.save(update_fields=["question_timing"])

    started_at = parse_datetime(timing[key])
    elapsed = (timezone.now() - started_at).total_seconds()
    remaining = max(0, int(limit - elapsed))
    return {"limit_seconds": limit, "remaining_seconds": remaining}


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


__all__ = ["mark_question_seen", "question_timer_expired", "question_time_limit_seconds"]
