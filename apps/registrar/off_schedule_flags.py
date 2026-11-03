"""«Cədvəldən kənar» işarəsinin yenidən qiymətləndirilməsi (2026-11-03).

``Lesson.off_schedule_reason`` yalnız dərs YARADILANDA yazılır (``journal_activation.check_manual_lesson``):
o an seçilmiş tarix + saat heç bir cədvəl slotuna uyğun gəlmirsə. Əvvəl işarə sonra heç vaxt
təmizlənmirdi — dərs düzəldiləndə və ya cədvəl (slot) sonradan əlavə/düzəliş olunanda belə «cədvəldən
kənar» kimi qalırdı (nümunə: dərs 21.10 Çərşənbə 11:50 «Data bərpası» ilə açılıb, o vaxt slot yox idi;
indi slot var, işarə qalıb).

Qayda yaradılma ilə EYNİDİR (:func:`journal_activation.slot_matches`): dərsin tarixində (həftə günü +
üst/alt paritet + dövr) bu açılışın cədvəldə DURAN slotlarından birinin başlanğıc saatı dərsin saatıdır
→ dərs cədvələ uyğundur və işarə TƏMİZLƏNİR. Yalnız təmizlənir — yeni işarə qoyulmur (səbəbi müəllim
yazır). Hər təmizlənmə açılışın «Dəyişiklik tarixçəsi»nə düşür (köhnə səbəb + mənbə).

Çağıranlar:

* ``gradebook_lessons.update_lesson`` — işarəli dərs düzəldiləndə (:func:`reevaluate_lesson`);
* ``ScheduleSlot`` ``post_save`` siqnalı (``apps.RegistrarConfig.ready``) — slot yaradılanda / düzəldiləndə
  həmin açılışın işarəli dərsləri (:func:`slot_saved`);
* ``schedule_publish`` toplu dərci (``bulk_create`` siqnal göndərmir) — :func:`reevaluate_offerings`;
* ``clear_stale_off_schedule_flags`` əmri — mövcud data üçün bir dəfəlik keçid.
"""

from __future__ import annotations

from . import grade_audit
from .models import CourseOffering, Lesson

#: Avtomatik yolların audit mənbəyi (``source``) — tarixçədə «nə təmizlədi» görünsün.
SOURCE_LESSON_EDIT = "lesson_edit"
SOURCE_SCHEDULE = "schedule_change"
SOURCE_COMMAND = "clear_stale_off_schedule_flags"


def _fresh_slots(offering) -> None:
    """``journal_activation.offering_slots`` memosu offering obyektində qalır — yeni slot görünsün."""
    from .journal_activation import _SLOTS_ATTR

    offering.__dict__.pop(_SLOTS_ATTR, None)


def is_on_schedule(offering, lesson) -> bool:
    from .journal_activation import offering_slots, slot_matches

    return bool(offering_slots(offering)) and slot_matches(offering, lesson.date, lesson.start_time)


def stale_lessons(offering, lessons=None) -> list:
    """İşarəli, amma indi cədvələ UYĞUN olan dərslər (yazmadan)."""
    flagged = [
        lesson
        for lesson in (
            lessons
            if lessons is not None
            else Lesson.objects.filter(offering=offering).exclude(off_schedule_reason="").order_by("date", "start_time")
        )
        if lesson.off_schedule_reason
    ]
    if not flagged:
        return []
    _fresh_slots(offering)
    return [lesson for lesson in flagged if is_on_schedule(offering, lesson)]


def clear(offering, lessons, *, by_user=None, source="") -> int:
    """İşarəni təmizlə + açılışın tarixçəsinə bir audit sətri. Yarış: yalnız səbəb DƏYİŞMƏYİBSƏ yazılır."""
    changes = []
    for lesson in lessons:
        old = lesson.off_schedule_reason
        if not Lesson.objects.filter(pk=lesson.pk, off_schedule_reason=old).update(off_schedule_reason=""):
            continue
        lesson.off_schedule_reason = ""
        changes.append(
            {
                "student": "—",
                "item": f"{lesson.date} · {lesson.get_kind_display()}",
                "old": f"cədvəldən kənar dərs — {old}",
                "new": "cədvələ uyğundur — işarə təmizləndi",
            }
        )
    if changes:
        grade_audit.log_grade_changes(
            offering=offering,
            by_user=by_user,
            kind="mark",
            changes=changes,
            reason=f"off_schedule_reevaluated:{source}" if source else "off_schedule_reevaluated",
        )
    return len(changes)


def reevaluate(offering, *, lessons=None, by_user=None, source="") -> int:
    """Açılışın (və ya verilmiş) işarəli dərsləri — cədvələ uyğun olanların işarəsi təmizlənir. Təmizlənən say."""
    return clear(offering, stale_lessons(offering, lessons), by_user=by_user, source=source)


def reevaluate_lesson(lesson, *, by_user=None) -> int:
    if not lesson.off_schedule_reason:
        return 0
    return reevaluate(lesson.offering, lessons=[lesson], by_user=by_user, source=SOURCE_LESSON_EDIT)


def reevaluate_offerings(offering_ids, *, by_user=None, source=SOURCE_SCHEDULE) -> int:
    """Bir neçə açılış — yalnız işarəli dərsi OLANLAR oxunur (bir sorğu ilə süzülür)."""
    ids = set(
        Lesson.objects.filter(offering_id__in=[pk for pk in offering_ids if pk])
        .exclude(off_schedule_reason="")
        .values_list("offering_id", flat=True)
    )
    total = 0
    for offering in CourseOffering.objects.filter(pk__in=ids).select_related("period", "organization", "subject"):
        total += reevaluate(offering, by_user=by_user, source=source)
    return total


def slot_saved(sender, instance, **kwargs) -> None:
    """``ScheduleSlot`` ``post_save`` — cədvəldə DURAN slot (parklanmamış, silinməmiş) yarandı / düzəldi."""
    if kwargs.get("raw") or instance.is_parked or getattr(instance, "is_deleted", False):
        return
    # Redaktorun kim olduğu siqnalda yoxdur — tarixçədə mənbə (``schedule_change``) görünür.
    reevaluate_offerings([instance.offering_id])


__all__ = [
    "SOURCE_COMMAND",
    "SOURCE_LESSON_EDIT",
    "SOURCE_SCHEDULE",
    "clear",
    "is_on_schedule",
    "reevaluate",
    "reevaluate_lesson",
    "reevaluate_offerings",
    "slot_saved",
    "stale_lessons",
]
