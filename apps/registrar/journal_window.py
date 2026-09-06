"""Jurnal grid-inin DƏRS PƏNCƏRƏSİ (QA 2026-09-05 P1-8).

555 tələbə × 226 dərs olan açılışda bütün xanalar bir səhifəyə render olunurdu:
41.5 MB HTML, 6.3 s (düzəliş rejimində 17.8 s) — brauzer donurdu. Həll: qrid
eyni anda yalnız bir DƏRS PƏNCƏRƏSİ (sütun dilimi) göstərir.

VACİB: pəncərə YALNIZ göstərişə aiddir. Qayıb saatı, giriş balı, buraxılış
qərarı və q/b sayğacı `gradebook.get_offering_journal` içində HƏMİŞƏ bütün
dərslər üzrə hesablanır — əks halda pəncərə rəqəmləri təhrif edərdi.
"""

from __future__ import annotations

#: Bir səhifədə göstərilən dərs sütunlarının default sayı.
DEFAULT_LESSON_WINDOW = 20

#: İstifadəçiyə təklif olunan pəncərə ölçüləri («hamısı» üçün 0).
WINDOW_CHOICES = (10, 20, 50, 0)


def resolve_window(total: int, *, limit, offset) -> tuple[int, int]:
    """(window_size, window_offset) — hədləri təhlükəsiz normallaşdırır."""
    window_offset = max(0, int(offset or 0))
    if not limit:
        return (total or 1), 0
    window_size = max(1, int(limit))
    if window_offset >= total:
        window_offset = max(0, total - window_size)
    return window_size, window_offset


def window_meta(*, total: int, shown: int, size: int, offset: int, newest_first: bool) -> dict:
    """Şablondakı naviqasiya zolağı üçün meta."""
    return {
        "enabled": total > shown,
        "size": size,
        "offset": offset,
        "total": total,
        "shown": shown,
        "has_prev": offset > 0,
        "has_next": offset + shown < total,
        "prev_offset": max(0, offset - size),
        "next_offset": offset + size,
        # Göstərilən aralığın xronoloji nömrələri (köhnədən yeniyə sabit nömrələmə).
        # Sütun sırası tərs olsa da etiket ARTAN oxunur: «13–32 / 32 dərs».
        "first_seq": (total - offset - shown + 1) if newest_first else (offset + 1),
        "last_seq": (total - offset) if newest_first else (offset + shown),
        "choices": WINDOW_CHOICES,
    }


def lesson_summaries(lessons, enrollments, mark_map, total_students: int) -> dict:
    """Sütun başlığındakı gün özəti (i/e · q/b · üq · bal) — əlavə SORĞU YOX.

    Yalnız GÖRÜNƏN dərslər üçün hesablanır: əvvəl 226 dərs × 555 tələbə = 125 min
    iterasiya hər səhifə yükündə gedirdi (QA 2026-09-05 P1-8).
    """
    from apps.registrar.models.grading_choices import AttendanceStatus

    summary: dict = {}
    for lesson in lessons:
        ie = qb = uq = scored = 0
        for enrollment in enrollments:
            mark = mark_map.get((enrollment.id, lesson.id))
            if mark is None:
                continue
            if mark.status == AttendanceStatus.ABSENT:
                qb += 1
            elif mark.status == AttendanceStatus.EXCUSED:
                uq += 1
            else:
                ie += 1
            if mark.score is not None:
                scored += 1
        summary[lesson.id] = {
            "ie": ie,
            "qb": qb,
            "uq": uq,
            "scored": scored,
            "total": total_students,
            "marked": ie + qb + uq,
        }
    return summary


def resolve_request_window(request):
    """`?lw=` (pəncərə ölçüsü) və `?lo=` (başlanğıc) — təhlükəsiz oxunuş.

    Naməlum ölçü default-a düşür (`?lw=0` = «hamısını göstər»), zibil dəyər
    istisna vermir. View-dan ayrıdır ki, jurnal görünüşü modul büdcəsini
    aşmasın (QA 2026-09-05 P1-8).
    """
    try:
        size = int(request.GET.get("lw", DEFAULT_LESSON_WINDOW))
    except (TypeError, ValueError):
        size = DEFAULT_LESSON_WINDOW
    if size and size not in WINDOW_CHOICES:
        size = DEFAULT_LESSON_WINDOW
    try:
        offset = int(request.GET.get("lo", 0))
    except (TypeError, ValueError):
        offset = 0
    return size, offset


__all__ = [
    "DEFAULT_LESSON_WINDOW",
    "WINDOW_CHOICES",
    "lesson_summaries",
    "resolve_request_window",
    "resolve_window",
    "window_meta",
]
