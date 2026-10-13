"""
Apellyasiya pəncərəsi — imtahan bitdikdən sonra yalnız N gün ərzində.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.utils import timezone

from apps.appeals.constants import APPEAL_WINDOW_DAYS
from apps.exams.public import ATTEMPT_FINISHED_STATUSES, exam_answers_release_locked

# Apellyasiyaya icazə verilən attempt statusları (bitmiş cəhdlər) — exams
# fasadındakı tək mənbədən törədilir.
APPEAL_ELIGIBLE_ATTEMPT_STATUSES = frozenset(ATTEMPT_FINISHED_STATUSES)


def appeal_window_days():
    """Pəncərənin uzunluğu (təqvim günü) — «Sistem tənzimləmələri» → ``settings.APPEAL_WINDOW_DAYS`` → 3.

    2026-10-13 (gecə): sahib «3 gün ərzində» dedi; rəqəm koddan çıxarılıb tənzimlənən edildi ki,
    qayda dəyişəndə deploy lazım olmasın. Yararsız dəyər heç vaxt tətbiq olunmur (defolta düşür)."""
    try:
        from core import runtime_settings

        days = int(runtime_settings.get_int("exam.appeal_window_days"))
    except Exception:  # noqa: BLE001 — tənzimləmə oxunmasa da pəncərə işləməlidir
        days = int(getattr(settings, "APPEAL_WINDOW_DAYS", APPEAL_WINDOW_DAYS) or APPEAL_WINDOW_DAYS)
    return max(1, days)


def appeal_window_timezone():
    """Son günün «sonu» hansı vaxt qurşağı ilə sayılır — defolt Asia/Baku (istifadəçinin aktiv tz-indən asılı deyil)."""
    try:
        return ZoneInfo(getattr(settings, "APPEAL_WINDOW_TIMEZONE", "Asia/Baku") or "Asia/Baku")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Asia/Baku")


def _finished_at(attempt):
    return getattr(attempt, "finished_at", None)


def _is_auto_graded(attempt):
    return getattr(getattr(attempt, "exam", None), "exam_type", None) == "test"


def attempt_awaiting_grading(attempt):
    """Əl ilə yoxlanan (yazılı/praktiki) cəhd hələ yoxlanmayıbmı."""
    return not _is_auto_graded(attempt) and not getattr(attempt, "checked_by_teacher", False)


def appeal_window_start(attempt):
    """Apellyasiya pəncərəsinin başlanğıcı və ya None (hələ açılmayıb).

    Audit 2026-09-28 EXA-02: əvvəl pəncərə HƏMİŞƏ ``finished_at``-dan sayılırdı —
    yoxlanmamış yazılı cəhdə apellyasiya verilə bilirdi (qəbul yarımçıq F
    yazırdı), yoxlama 3 gündən uzun çəkəndə isə tələbə heç vaxt müraciət edə
    bilmirdi. İndi:

    * avtomatik qiymətlənən test → nəticə dərhal dərc olunur (``result_release``
      siyasəti) → ``finished_at``;
    * yazılı/praktiki → YALNIZ ``checked_by_teacher`` olduqda, ``teacher_checked_at``-dan
      (köhnə sətirdə boşdursa ``finished_at``-dan).
    """
    finished = _finished_at(attempt)
    if not finished:
        return None
    exam = getattr(attempt, "exam", None)
    # 2026-10-13 (gecə): müəllim nəticəni tələbədən GİZLƏDİBSƏ tələbə nəyə etiraz edəcəyini görmür —
    # pəncərə açılmır (əvvəl 3 gün gizli nəticə dövründə «yanırdı»).
    if getattr(exam, "results_hidden_from_students", False):
        return None
    if _is_auto_graded(attempt):
        if exam_answers_release_locked(exam):
            return None
        start = finished
    elif not getattr(attempt, "checked_by_teacher", False):
        return None
    else:
        start = getattr(attempt, "teacher_checked_at", None) or finished
    # Nəticə sonradan açılıbsa (gizli → görünən) pəncərə AÇILMA anından sayılır, bitmə anından yox.
    published = getattr(exam, "results_published_at", None)
    if published and published > start:
        start = published
    return start


def appeal_deadline(attempt):
    """Apellyasiya üçün son tarix və ya None.

    Qayda date-based-dir: nəticə 7-də dərc olunubsa (test bitib / yazılı iş
    yoxlanıb), 8/9/10-da müraciət edə bilər; 11-də həmin fənn üzrə apellyasiya
    bağlanır.
    """
    start = appeal_window_start(attempt)
    if not start:
        return None
    # 2026-10-13 (gecə): gün sərhədi HƏMİŞƏ Bakı vaxtı ilə (əvvəl aktiv tz — istifadəçi tz-i
    # aktivləşəndə son tarix sürüşə bilirdi).
    tz = appeal_window_timezone()
    deadline_date = timezone.localtime(start, tz).date() + timedelta(days=appeal_window_days())
    return datetime.combine(deadline_date, time.max).replace(tzinfo=tz)


def is_within_appeal_window(attempt, *, at_time=None):
    """Attempt bitib, nəticə dərc olunub (EXA-02) VƏ son tarix keçməyibsə True."""
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
    "appeal_window_days",
    "appeal_window_start",
    "appeal_window_timezone",
    "attempt_awaiting_grading",
    "is_within_appeal_window",
    "remaining_window_seconds",
]
