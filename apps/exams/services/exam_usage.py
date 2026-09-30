"""İmtahan hazırda istifadədədirmi — avtomatik deaktivasiyadan əvvəl yoxlama.

QB 2026-09-30 (sahib): canlı imtahandan sonra müəllim sual bankında bütün aktiv
sualları seçib silə bilmirdi («Aktiv imtahanın son aktiv sualı …» xətası). İndi
belə seçimdə imtahan müəllimin təsdiqi ilə deaktiv edilir və suallar silinir —
amma YALNIZ imtahanı hazırda heç kim işlətmirsə. «İşlədir» deməkdir:

* başlanmış, bitməmiş real cəhd (sınaq cəhdi sayılmır) — yazı pəncərəsi hələ
  açıqdır, yəni tələbə imtahanı YAZIR;
* bitməmiş canlı (live) sessiya — son ``LIVE_SESSION_ACTIVITY_WINDOW`` ərzində
  aktivliyi olan; hostun bağlamadan tərk etdiyi köhnə lobbi/sessiya müəllimi
  əbədi bloklamasın deyə daha köhnələri nəzərə alınmır;
* açıq final zal oturumu — biletli tələbə zalda gözləyir və ya yazır.

Qaytarılan mətn SƏBƏBİ adlandırır (müəllim nə edəcəyini bilsin).
"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import pgettext

from apps.exams.domain.attempt_deadline import lazy_expiry_cutoff, write_window_closed
from apps.exams.domain.final_center.states import (
    ROOM_SESSION_STATE_ACTIVE,
    ROOM_SESSION_STATE_ENTRY_OPEN,
    TICKET_STATUS_ACTIVE,
    TICKET_STATUS_READY,
    TICKET_STATUS_WAITING,
)

# Canlı sessiya bu müddətdə heç bir aktivlik göstərməyibsə «tərk edilmiş» sayılır.
LIVE_SESSION_ACTIVITY_WINDOW = timedelta(hours=3)

# ``apps.live_exam.models.LiveSession.STATE_FINISHED`` — modul sərhədi səbəbindən
# live_exam import edilmir; sessiyalara ``exam.live_sessions`` reverse əlaqəsi ilə baxırıq.
_LIVE_SESSION_STATE_FINISHED = "finished"

_OPEN_ATTEMPT_STATUSES = ("draft", "in_progress")
_OPEN_HALL_SESSION_STATES = (ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE)
_OPEN_TICKET_STATUSES = (TICKET_STATUS_WAITING, TICKET_STATUS_READY, TICKET_STATUS_ACTIVE)


def open_attempt_count(exam) -> int:
    """Yazı pəncərəsi hələ açıq olan real (sınaq olmayan) cəhdlərin sayı."""
    cutoff = lazy_expiry_cutoff()
    attempts = exam.attempts.filter(status__in=_OPEN_ATTEMPT_STATUSES, is_trial=False)
    return sum(1 for attempt in attempts if not write_window_closed(attempt, at_time=cutoff))


def active_live_session(exam):
    """Bitməmiş və yaxın vaxtda aktivliyi olan canlı sessiya (yoxdursa ``None``)."""
    cutoff = timezone.now() - LIVE_SESSION_ACTIVITY_WINDOW
    recent = Q(created_at__gte=cutoff) | Q(question_started_at__gte=cutoff) | Q(question_ends_at__gte=cutoff)
    return (
        exam.live_sessions.exclude(state=_LIVE_SESSION_STATE_FINISHED)
        .filter(recent)
        .order_by("-created_at", "-id")
        .first()
    )


def open_final_hall_ticket_count(exam) -> int:
    """Açıq zal oturumunda gözləyən/hazır/yazan biletli tələbələrin sayı."""
    return exam.final_tickets.filter(
        session__state__in=_OPEN_HALL_SESSION_STATES,
        status__in=_OPEN_TICKET_STATUSES,
    ).count()


def exam_in_use_error(exam) -> str:
    """İmtahan hazırda istifadədədirsə səbəbi adlandıran mesaj, əks halda ``""``."""
    attempt_count = open_attempt_count(exam)
    if attempt_count:
        return pgettext(
            "exams.service.exam_usage",
            "İmtahanı hazırda {count} tələbə yazır (başlanmış, bitməmiş cəhd). Onlar bitirənə qədər "
            "imtahan deaktiv edilə və bütün aktiv sualları silinə bilməz.",
        ).format(count=attempt_count)

    live_session = active_live_session(exam)
    if live_session is not None:
        return pgettext(
            "exams.service.exam_usage",
            "Bu imtahan üzrə canlı sessiya hələ bitməyib (PIN: {pin}). Əvvəl canlı sessiyanı bitirin, "
            "sonra sualları silin.",
        ).format(pin=live_session.pin)

    ticket_count = open_final_hall_ticket_count(exam)
    if ticket_count:
        return pgettext(
            "exams.service.exam_usage",
            "Bu imtahan üzrə final zal oturumu davam edir ({count} tələbə zalda). Oturum bitənə qədər "
            "imtahan deaktiv edilə bilməz.",
        ).format(count=ticket_count)

    return ""


__all__ = [
    "LIVE_SESSION_ACTIVITY_WINDOW",
    "active_live_session",
    "exam_in_use_error",
    "open_attempt_count",
    "open_final_hall_ticket_count",
]
