"""Dərsin vaxt məlumatı — YALNIZ əməkdaşa (sahib 2026-11-17).

Laborant / tyutor / kafedra / dekanlıq / RİM jurnalı açanda:

* sütun başlığında tarix ilə «i/e · q/b» arasında dərsin SAAT ARALIĞI (``start_time–end_time``) və neçə saatlıq
  əlavə olunduğu (``hours``; passiv dərs öz «Passiv · N saat» nişanı ilə);
* gün özəti pəncərəsində dərsin BAŞLADILDIĞI an — dərs sətrinin yaradılma vaxtı (``Lesson.created_at``, Bakı vaxtı);
* xlsx ixracında hər dərs üçün eyni sahələr («Dərslər» vərəqi + başlıqda saat).

Jurnalın ÖZ müəllimi (açılışın müəllimi / bölünmüş jurnalın pay sahibi / bu jurnalda dərs keçən / təhvil vermiş köhnə
müəllim) bunu GÖRMÜR — sahib: «qarışıqdır». Qərar HTML-də verilir: müəllimə gedən səhifədə bu data-atributlar yoxdur.
"""

from __future__ import annotations

from django.utils import timezone


def is_journal_teacher(user, offering) -> bool:
    """İstifadəçi bu jurnalın öz müəllimidirmi (rolundan asılı olmayaraq — RİM əməkdaşı da öz jurnalında müəllimdir)."""
    user_id = getattr(user, "pk", None)
    if user_id is None or not getattr(user, "is_authenticated", False):
        return False
    if offering.instructor_id == user_id:
        return True
    from .journal_shares import active_shares

    if any(share.teacher_id == user_id for share in active_shares(offering)):
        return True
    from .handover import is_handover_observer

    if is_handover_observer(user, offering):
        return True
    from .models import Lesson

    return Lesson.objects.filter(offering_id=offering.pk, instructor_id=user_id).exists()


def show_lesson_timing(user, offering) -> bool:
    """Saat aralığı / saat sayı / başladılma vaxtı göstərilsinmi — əməkdaşa bəli, jurnalın müəlliminə yox."""
    return bool(getattr(user, "is_authenticated", False)) and not is_journal_teacher(user, offering)


def time_range(lesson) -> str:
    """``10:10–11:40`` / yalnız başlanğıc ``10:10`` / saat yoxdursa boş."""
    start, end = lesson.start_time, lesson.end_time
    if not start:
        return ""
    text = start.strftime("%H:%M")
    return f"{text}–{end.strftime('%H:%M')}" if end else text


def started_at(lesson):
    """Dərsin başladıldığı an (yerli vaxt). Köhnə sistemdən bərpa olunan dərsdə yoxdur (idxal anıdır, mənasızdır)."""
    if getattr(lesson, "is_legacy_synthesised", False) or not getattr(lesson, "created_at", None):
        return None
    return timezone.localtime(lesson.created_at)


def started_at_text(lesson) -> str:
    moment = started_at(lesson)
    return moment.strftime("%d.%m.%Y %H:%M") if moment else ""


def page_context(user, offering) -> dict:
    return {"show_lesson_timing": show_lesson_timing(user, offering)}


__all__ = ["is_journal_teacher", "page_context", "show_lesson_timing", "started_at", "started_at_text", "time_range"]
