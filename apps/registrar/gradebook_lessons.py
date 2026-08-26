"""Dərs (Lesson) CRUD — gradebook-un davamı.

``gradebook.py`` modul-ölçü büdcəsinə görə bölünüb (``gradebook_components.py``
ilə eyni nümunə): dərs sütununun yaradılması / redaktəsi / silinməsi buradadır.
Bütün ictimai adlar ``gradebook``-dan re-eksport olunur — çağıranlar üçün API
dəyişməyib.

Otaq (``room``) sahəsi opsionaldır: köhnə dərslərdə yoxdur, boş qala bilər.
Redaktədə ``None`` MƏNALI dəyərdir ("otağı təmizlə"), ona görə "verilməyib"
halı ``UNSET`` sentineli ilə ayrılır.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.registrar import grade_audit
from apps.registrar.models import Lesson, LessonKind, LessonMark

from .gradebook import (  # noqa: F401
    DEFAULT_LESSON_HOURS,
    UNSET,
    LessonRuleError,
    can_edit_lesson,
    ensure_assessment_scheme,
    journal_is_locked,
    recompute_absence_hours,
)

# ── Lesson (dərs) CRUD ───────────────────────────────────────────────────────


def _coerce_date(value):
    import datetime

    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


@transaction.atomic
def create_lesson(
    *,
    offering,
    date,
    kind=LessonKind.LECTURE,
    topic="",
    hours=None,
    start_time=None,
    end_time=None,
    created_by=None,
    instructor=None,
    room=None,
    allow_past=False,
):
    """Add a held session. ``instructor`` bu dərsin müəllimi (boşdursa açılışınkı);
    ``room`` dərsin otağı (opsional — köhnə dərslərdə yoxdur);
    ``allow_past`` İKT rəhbəri/seed üçün keçmiş tarixi keçir."""
    if journal_is_locked(offering):
        raise LessonRuleError("Jurnal kilidlidir — dərs əlavə etmək olmaz.")
    parsed = _coerce_date(date)
    if parsed is None:
        raise LessonRuleError("Dərs tarixi düzgün deyil.")
    if not allow_past and parsed < timezone.localdate():
        raise LessonRuleError("Keçmiş tarixə dərs əlavə etmək olmaz.")
    new_hours = hours or DEFAULT_LESSON_HOURS
    if start_time and Lesson.objects.filter(offering=offering, date=parsed, start_time=start_time).exists():
        raise LessonRuleError("Eyni gündə eyni dərs saatına artıq dərs var — üst-üstə düşür.")
    ensure_assessment_scheme(offering=offering)
    return Lesson.objects.create(
        organization=offering.organization,
        offering=offering,
        date=parsed,
        kind=kind,
        topic=topic or "",
        hours=new_hours,
        start_time=start_time,
        end_time=end_time,
        created_by=created_by,
        instructor=instructor or offering.instructor,
        room=room,
    )


@transaction.atomic
def update_lesson(
    *,
    lesson,
    date=None,
    kind=None,
    topic=None,
    hours=None,
    start_time=None,
    end_time=None,
    instructor=None,
    room=UNSET,
    allow_past=False,
    allow_locked=False,
) -> bool:
    """Səhv açılmış dərsi düzəlt (2 saat içində). ``allow_locked``/``allow_past``
    pəncərəni + keçmiş-tarixi keçir (İKT/superuser); yayımlanmış jurnal yenə kilidli."""
    if journal_is_locked(lesson.offering) or (not can_edit_lesson(lesson) and not allow_locked):
        return False
    fields = []
    if date is not None:
        parsed = _coerce_date(date)
        if parsed is None:
            raise LessonRuleError("Dərs tarixi düzgün deyil.")
        if parsed < timezone.localdate() and not allow_past:
            raise LessonRuleError("Dərs tarixi bu gündən əvvəl ola bilməz.")
        lesson.date = parsed
        fields.append("date")
    if kind is not None and kind in dict(LessonKind.choices):
        lesson.kind = kind
        fields.append("kind")
    if topic is not None:
        lesson.topic = topic
        fields.append("topic")
    if hours is not None:
        lesson.hours = hours
        fields.append("hours")
    if start_time is not None:
        lesson.start_time = start_time or None
        fields.append("start_time")
    if end_time is not None:
        lesson.end_time = end_time or None
        fields.append("end_time")
    if instructor is not None:
        lesson.instructor = instructor
        fields.append("instructor")
    # Otaq TƏMİZLƏNƏ də bilər (None = "otaq seçilməyib"), ona görə "verilməyib"
    # halı ayrıca sentinel ilə fərqləndirilir — None-u "dəyişmə" saymırıq.
    if room is not UNSET:
        lesson.room = room
        fields.append("room")
    if fields:
        lesson.save(update_fields=fields)
    return True


@transaction.atomic
def delete_lesson(*, lesson, by_user=None, allow_locked=False) -> bool:
    """Səhv açılmış dərsi sil (2 saat içində; ``allow_locked`` İKT/superuser üçün keçir).
    İşarələr kaskadla silinir; əməliyyat audit tarixçəsinə düşür."""
    if journal_is_locked(lesson.offering) or (not can_edit_lesson(lesson) and not allow_locked):
        return False
    offering = lesson.offering
    label = f"{lesson.date} · {lesson.get_kind_display()}"
    touched = [m.enrollment for m in LessonMark.objects.filter(lesson=lesson).select_related("enrollment")]
    lesson.delete()
    for enrollment in touched:
        recompute_absence_hours(enrollment=enrollment)
    grade_audit.log_grade_changes(
        offering=offering,
        by_user=by_user,
        kind="mark",
        changes=[{"student": "—", "item": label, "old": "dərs sütunu", "new": "silindi"}],
    )
    return True


# Köhnə ad — mövcud çağırışlar üçün (yalnız tarix dəyişən variant).
def update_lesson_date(*, lesson, date) -> bool:
    try:
        return update_lesson(lesson=lesson, date=date)
    except LessonRuleError:
        return False
