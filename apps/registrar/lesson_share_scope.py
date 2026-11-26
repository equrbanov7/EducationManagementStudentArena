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


#: Bir dərs saatı (cütlük, 90 dəqiqə) = 2 akademik saat. Sahib 2026-11-27 (Lalə Qurbanova): o saatda 1 saatlıq dərs
#: varsa, ikinci 1 saatlıq dərs (məs. seminar + laboratoriya) da əlavə oluna bilər — cəmi 90 dəqiqədir.
SLOT_HOURS = 2


def slot_has_room(lessons, hours) -> bool:
    """O saatdakı dərslərin saatı + yeni dərsin saatı cütlüyə (:data:`SLOT_HOURS`) sığırmı."""
    if not hours:
        return False
    return sum(int(lesson.hours or 0) for lesson in lessons) + int(hours) <= SLOT_HOURS


def has_slot_collision(
    *, offering, date, start_time, instructor_id, kind, exclude=None, lab_group=None, seminar_group=None, hours=None
):
    """Eyni jurnalda eyni gün + saatda dərs var və yeni dərs ona sığmır.

    ``hours`` verilibsə (yeni / redaktə olunan dərsin saatı) və o saatdakı dərslərlə birlikdə cütlüyə sığırsa
    (1 + 1 ≤ 2 — sahib 2026-11-27) toqquşma yoxdur."""
    candidates = offering.lessons.filter(date=date, start_time=start_time)
    if exclude is not None:
        candidates = candidates.exclude(pk=exclude)
    lessons = [lesson for lesson in candidates if not _other_subgroup(lesson, kind, lab_group, seminar_group)]
    if not lessons or slot_has_room(lessons, hours):
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


def match_slots(slots, lessons) -> dict:
    """``{slot.pk: dərs}`` — günün cədvəl slotlarını həmin günün dərsləri ilə TƏK-TƏK cütləşdirir (sahib 2026-11-15).

    Əvvəl slot «başlanğıc saatında dərs varmı» ilə yoxlanırdı: bir jurnalda EYNİ saatda iki slot (patok / birləşmiş
    qrup, Lab-1 + Lab-2, mühazirə + lab) olanda birinci dərs açılan kimi ikinci slot da «açılıb» sayılırdı — «Yeni
    dərs» başqa saatın (məs. 13:35) slotunu doldurur, «Aktivləşdir» ikinci dərsi «artıq aktivləşdirilib» deyə rədd
    edirdi. İndi hər dərs yalnız BİR slotu bağlayır: əvvəl eyni saat + eyni növ, sonra eyni saat (növü dəyişmiş dərs).
    """
    free = [lesson for lesson in lessons if getattr(lesson, "start_time", None) is not None]
    matched: dict = {}
    for same_kind in (True, False):
        for slot in slots:
            if slot.pk in matched:
                continue
            kind = slot.kind if slot.kind in LessonKind.values else LessonKind.LECTURE
            hit = next(
                (
                    lesson
                    for lesson in free
                    if lesson.start_time == slot.start_time and (not same_kind or lesson.kind == kind)
                ),
                None,
            )
            if hit is not None:
                free.remove(hit)
                matched[slot.pk] = hit
    return matched


def scoped_lessons(offering, lessons, scope=None):
    if scope is None or scope.full:
        return lessons
    marks = LessonMark.objects.filter(
        organization_id=offering.organization_id,
        lesson__offering=offering,
        lesson_id__in=[lesson.pk for lesson in lessons],
    ).values_list("enrollment_id", "lesson_id")
    return visible_lessons(scope, lessons, dict.fromkeys(marks))
