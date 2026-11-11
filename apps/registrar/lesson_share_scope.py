"""Parallel level lessons are allowed only for proven disjoint student shares.

Bir jurnal daxilində eyni gün + eyni başlanğıc saatı İKİNCİ dərs ancaq tələbə dəstləri SÜBUTLA ayrı olanda
yazılır: (1) bölünmüş jurnalın ayrı payları (``JournalShare``); (2) sahib 2026-11-11 (patok — «eyni saatda ikinci
qrupun dərsi yazılmır»): FƏRQLİ alt qrupların dərsi — Lab-1 / Lab-2 (``lab_group``) və ya seminar alt qrupları
(``seminar_group``); müəllim eyni ola da bilər (alt qruplar birgə oturur). Qrupsuz (bütün qrup) dərs hər alt
qrupla toqquşur. Patokun BAŞQA qrupunun dərsi öz jurnalındadır (başqa açılış) — bura heç vaxt düşmür.
"""

from .journal_shares import visible_lessons
from .models import JournalShare, LessonKind, LessonMark


def _other_subgroup(lesson, kind, lab_group, seminar_group) -> bool:
    """``lesson`` başqa alt qrupun dərsidir (tələbələri kəsişmir)."""
    if kind == LessonKind.LAB and lesson.kind == LessonKind.LAB:
        return bool(lab_group and lesson.lab_group and lab_group != lesson.lab_group)
    if kind == LessonKind.SEMINAR and lesson.kind == LessonKind.SEMINAR:
        return bool(seminar_group and lesson.seminar_group and seminar_group != lesson.seminar_group)
    return False


def has_slot_collision(
    *, offering, date, start_time, instructor_id, kind, exclude=None, lab_group=None, seminar_group=None
):
    candidates = offering.lessons.filter(date=date, start_time=start_time)
    if exclude is not None:
        candidates = candidates.exclude(pk=exclude)
    lessons = [lesson for lesson in candidates if not _other_subgroup(lesson, kind, lab_group, seminar_group)]
    if not lessons:
        return False
    if not instructor_id or any(
        not lesson.instructor_id or lesson.instructor_id == instructor_id for lesson in lessons
    ):
        return True
    shares = list(
        JournalShare.objects.select_for_update()
        .filter(organization_id=offering.organization_id, offering=offering, is_active=True)
        .prefetch_related("enrollments")
    )
    rows = {}
    kinds = {}
    for share in shares:
        rows[share.teacher_id] = {
            str(enrollment.pk)
            for enrollment in share.enrollments.all()
            if enrollment.organization_id == offering.organization_id and enrollment.offering_id == offering.pk
        }
        kinds[share.teacher_id] = set(share.kinds or [])
    own = rows.get(instructor_id)
    if not own or (kinds[instructor_id] and kind not in kinds[instructor_id]):
        return True
    for lesson in lessons:
        other = rows.get(lesson.instructor_id)
        if not other or own & other or (kinds[lesson.instructor_id] and lesson.kind not in kinds[lesson.instructor_id]):
            return True
    # Existing records win even if a later share edit made the current sets disjoint.
    return LessonMark.objects.filter(
        organization_id=offering.organization_id, lesson__in=lessons, enrollment_id__in=own
    ).exists()


def scoped_lessons(offering, lessons, scope=None):
    if scope is None or scope.full:
        return lessons
    marks = LessonMark.objects.filter(
        organization_id=offering.organization_id,
        lesson__offering=offering,
        lesson_id__in=[lesson.pk for lesson in lessons],
    ).values_list("enrollment_id", "lesson_id")
    return visible_lessons(scope, lessons, dict.fromkeys(marks))
