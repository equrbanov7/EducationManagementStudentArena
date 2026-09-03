"""Canonical row-lock ordering for correction apply/reversal transactions."""

from django.core.exceptions import ValidationError

from .models import (
    AssessmentComponent,
    ComponentScore,
    CourseWork,
    Enrollment,
    Lesson,
    LessonMark,
    SelfWorkMark,
    SelfWorkTopic,
)


def _changed():
    return ValidationError("The correction target changed concurrently; reload and try again.")


def lock_grade_for_apply(mark, *, expected_empty):
    """Lock stable parents first, then resolve the authoritative mark row."""
    lesson = Lesson.objects.select_for_update().get(pk=mark.lesson_id)
    enrollment = Enrollment.objects.select_for_update().get(pk=mark.enrollment_id)
    persisted = LessonMark.objects.select_for_update().filter(lesson=lesson, enrollment=enrollment).first()
    if persisted is None:
        if not expected_empty:
            raise _changed()
        mark.lesson = lesson
        mark.enrollment = enrollment
        return mark, lesson, enrollment
    if expected_empty or persisted.pk != mark.pk:
        raise _changed()
    return persisted, lesson, enrollment


def lock_grade_for_reversal(correction):
    lesson = Lesson.objects.select_for_update().get(pk=correction.lesson_ref)
    enrollment = Enrollment.objects.select_for_update().get(pk=correction.enrollment_ref)
    mark = (
        LessonMark.objects.select_for_update()
        .filter(
            pk=correction.lesson_mark_id,
            lesson=lesson,
            enrollment=enrollment,
        )
        .first()
    )
    if mark is None:
        raise _changed()
    return mark, lesson, enrollment


def lock_lesson(lesson):
    return Lesson.objects.select_for_update().get(pk=lesson.pk)


def lock_selfwork(topic, enrollment):
    locked_topic = SelfWorkTopic.objects.select_for_update().get(pk=topic.pk)
    locked_enrollment = Enrollment.objects.select_for_update().get(pk=enrollment.pk)
    mark = SelfWorkMark.objects.select_for_update().filter(topic=locked_topic, enrollment=locked_enrollment).first()
    return locked_topic, locked_enrollment, mark


def lock_coursework(enrollment):
    locked_enrollment = Enrollment.objects.select_for_update().get(pk=enrollment.pk)
    work = CourseWork.objects.select_for_update().filter(enrollment=locked_enrollment).first()
    return locked_enrollment, work


def lock_component(component, enrollment):
    locked_component = AssessmentComponent.objects.select_for_update().get(pk=component.pk)
    locked_enrollment = Enrollment.objects.select_for_update().get(pk=enrollment.pk)
    score = (
        ComponentScore.objects.select_for_update()
        .filter(component=locked_component, enrollment=locked_enrollment)
        .first()
    )
    return locked_component, locked_enrollment, score
