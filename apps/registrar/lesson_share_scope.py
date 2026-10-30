"""Parallel level lessons are allowed only for proven disjoint student shares."""

from .journal_shares import visible_lessons
from .models import JournalShare, LessonMark


def has_slot_collision(*, offering, date, start_time, instructor_id, kind, exclude=None):
    candidates = offering.lessons.filter(date=date, start_time=start_time)
    if exclude is not None:
        candidates = candidates.exclude(pk=exclude)
    lessons = list(candidates)
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
