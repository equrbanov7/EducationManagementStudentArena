"""Fail-closed, append-only reversal services for documented corrections."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction
from core.rls import journal_unlock

from . import grade_audit, journal_extras
from .gradebook import recompute_absence_hours
from .models import (
    ComponentScore,
    ComponentScoreCorrection,
    CorrectionField,
    CorrectionReversal,
    CourseWorkCorrection,
    JournalCorrection,
    Lesson,
    LessonCorrection,
    SelfWorkCorrection,
)

_ATTENDANCE_LABELS = {"present": "iə", "absent": "qb", "excused": "üq"}


def _stale_error():
    return ValidationError(
        pgettext(
            "registrar.correction",
            "The correction is no longer the active latest change; reload the journal and try again.",
        )
    )


def _real_actor(by_user, request=None):
    actor = None
    if request is not None and getattr(request, "is_view_as", False):
        candidate = getattr(request, "real_user", None)
        if candidate is not None and getattr(candidate, "is_authenticated", False):
            actor = candidate
    actor = actor or by_user
    if actor is None or not getattr(actor, "pk", None):
        raise ValidationError(pgettext("registrar.correction", "A reversal actor is required."))
    return actor


def _select_active(model, target_field, filters, correction_id):
    queryset = model.objects.select_for_update(of=("self",)).filter(**filters)
    if correction_id:
        correction = queryset.filter(pk=correction_id).first()
        if correction is None:
            raise _stale_error()
        if CorrectionReversal.objects.filter(**{target_field: correction}).exists():
            return correction, True
        latest = queryset.filter(reversal__isnull=True).order_by("-created_at", "-id").first()
        if latest is None or latest.pk != correction.pk:
            raise _stale_error()
        return correction, False
    correction = queryset.filter(reversal__isnull=True).order_by("-created_at", "-id").first()
    return correction, False


def _select_grade_correction(*, mark, correction_id, offering=None):
    if correction_id:
        correction = JournalCorrection.objects.select_for_update(of=("self",)).filter(pk=correction_id).first()
        if correction is None:
            raise _stale_error()
        if mark is not None and correction.lesson_mark_ref != mark.pk:
            raise _stale_error()
        if offering is not None:
            if correction.organization_id != offering.organization_id:
                raise _stale_error()
            if not Lesson.objects.filter(pk=correction.lesson_ref, offering=offering).exists():
                raise _stale_error()
        if CorrectionReversal.objects.filter(journal_correction=correction).exists():
            return correction, True
        if mark is None or correction.lesson_mark_id != mark.pk:
            raise _stale_error()
        latest = (
            JournalCorrection.objects.select_for_update(of=("self",))
            .filter(lesson_mark=mark, reversal__isnull=True)
            .order_by("-created_at", "-id")
            .first()
        )
        if latest is None or latest.pk != correction.pk:
            raise _stale_error()
        return correction, False
    if mark is None:
        raise _stale_error()
    correction = (
        JournalCorrection.objects.select_for_update(of=("self",))
        .filter(lesson_mark=mark, reversal__isnull=True)
        .order_by("-created_at", "-id")
        .first()
    )
    return correction, False


def _create_reversal(*, correction, target_field, actor):
    from .integrity import validate_same_organization_actor

    validate_same_organization_actor(
        organization=correction.organization,
        user=actor,
        field_name="reverted_by",
        require_active=True,
    )
    reversal = CorrectionReversal(
        organization=correction.organization,
        reverted_by=actor,
        reverted_by_ref=str(actor.pk),
        **{target_field: correction},
    )
    reversal.full_clean()
    reversal.save()
    return reversal


def _write_audit(*, offering, actor, request, reversal, kind, item, old, new, enrollment_id=""):
    changes = [
        {
            "student": f"enrollment:{enrollment_id}" if enrollment_id else "academic-record",
            "item": str(item),
            "old": str(old),
            "new": str(new),
        }
    ]
    grade_audit.log_grade_changes(
        offering=offering,
        by_user=actor,
        kind=kind,
        changes=changes,
        fail_closed=True,
    )
    log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=offering.organization,
        obj=reversal,
        reason=kind,
        request=request,
        changes=[{"field": str(item), "old": str(old), "new": str(new)}],
    )


@transaction.atomic
def revert_last_grade_correction(*, mark=None, by_user, request=None, correction_id=None, offering=None) -> bool:
    """Reverse exactly one active grade correction without deleting evidence."""
    correction, already_reversed = _select_grade_correction(
        mark=mark,
        correction_id=correction_id,
        offering=offering,
    )
    if correction is None:
        return False
    if already_reversed:
        return True
    from .correction_target_locks import lock_grade_for_reversal

    mark, lesson, enrollment = lock_grade_for_reversal(correction)
    actor = _real_actor(by_user, request)
    if correction.field == CorrectionField.ATTENDANCE:
        if mark.status != correction.new_status:
            raise _stale_error()
        old_repr = _ATTENDANCE_LABELS.get(correction.new_status, correction.new_status)
        new_repr = _ATTENDANCE_LABELS.get(correction.old_status, correction.old_status) or "—"
    else:
        if mark.score != correction.new_score:
            raise _stale_error()
        old_repr = correction.new_score
        new_repr = correction.old_score if correction.old_score is not None else "—"

    reversal = _create_reversal(
        correction=correction,
        target_field="journal_correction",
        actor=actor,
    )
    if correction.created_mark and not mark.corrections.filter(reversal__isnull=True).exists():
        with journal_unlock():
            mark.delete()
    else:
        if correction.field == CorrectionField.ATTENDANCE:
            mark.status = correction.old_status
        else:
            mark.score = correction.old_score
        with journal_unlock():
            mark.save(update_fields=["status", "score", "updated_at"])
    recompute_absence_hours(enrollment=enrollment)
    _write_audit(
        offering=lesson.offering,
        actor=actor,
        request=request,
        reversal=reversal,
        kind="correction-revert",
        item=f"{lesson.date} · {str(lesson.get_kind_display())}",
        old=old_repr,
        new=new_repr,
        enrollment_id=enrollment.pk,
    )

    from apps.registrar import journal_notifications as notifications

    transaction.on_commit(
        lambda: notifications.send_journal_events(
            offering=lesson.offering,
            events=[{"enrollment": enrollment, "kind": notifications.EVENT_CORRECTED}],
        )
    )
    return True


def _lesson_time(lesson):
    if lesson.start_time and lesson.end_time:
        return f"{lesson.start_time.strftime('%H:%M')}–{lesson.end_time.strftime('%H:%M')}"
    return ""


@transaction.atomic
def revert_last_lesson_correction(*, lesson, by_user, request=None, correction_id=None) -> bool:
    """Reverse the selected latest lesson correction and retain both records."""
    from .gradebook import update_lesson

    correction, already_reversed = _select_active(
        LessonCorrection,
        "lesson_correction",
        {"lesson": lesson, "is_deletion": False},
        correction_id,
    )
    if correction is None:
        return False
    if already_reversed:
        return True
    from .correction_target_locks import lock_lesson

    lesson = lock_lesson(lesson)
    current = (
        lesson.date,
        lesson.kind,
        lesson.hours,
        _lesson_time(lesson),
        lesson.topic or "",
        lesson.instructor_id,
    )
    expected = (
        correction.new_date,
        correction.new_kind,
        correction.new_hours,
        correction.new_time,
        correction.new_topic,
        correction.new_instructor_id,
    )
    if current != expected:
        raise _stale_error()
    actor = _real_actor(by_user, request)
    reversal = _create_reversal(
        correction=correction,
        target_field="lesson_correction",
        actor=actor,
    )
    start = end = None
    if correction.old_time and "–" in correction.old_time:
        from apps.registrar import schedule as schedule_service

        start, end = schedule_service.parse_time_slot(correction.old_time.replace("–", "|"))
    ok = update_lesson(
        lesson=lesson,
        date=correction.old_date,
        kind=correction.old_kind or None,
        topic=correction.old_topic,
        hours=correction.old_hours,
        start_time=start or "",
        end_time=end or "",
        instructor=correction.old_instructor,
        allow_past=True,
        allow_locked=True,
    )
    if not ok:
        raise ValidationError(pgettext("registrar.correction", "The published journal cannot be changed."))
    if correction.old_instructor_id is None and lesson.instructor_id is not None:
        with journal_unlock():
            lesson.instructor = None
            lesson.save(update_fields=["instructor"])
    _write_audit(
        offering=lesson.offering,
        actor=actor,
        request=request,
        reversal=reversal,
        kind="lesson-correction-revert",
        item="lesson",
        old="correction",
        new="reverted",
    )
    return True


@transaction.atomic
def revert_last_selfwork_correction(*, topic, enrollment, by_user, request=None, correction_id=None) -> bool:
    correction, already_reversed = _select_active(
        SelfWorkCorrection,
        "selfwork_correction",
        {"topic": topic, "enrollment": enrollment},
        correction_id,
    )
    if correction is None:
        return False
    if already_reversed:
        return True
    from .correction_target_locks import lock_selfwork

    topic, enrollment, mark = lock_selfwork(topic, enrollment)
    if bool(mark and mark.done) != correction.new_done:
        raise _stale_error()
    actor = _real_actor(by_user, request)
    reversal = _create_reversal(
        correction=correction,
        target_field="selfwork_correction",
        actor=actor,
    )
    ok = journal_extras.set_selfwork_mark(
        offering=topic.offering,
        topic_id=topic.id,
        enrollment_id=enrollment.id,
        done=correction.old_done,
        by_user=actor,
        allow_locked=True,
    )
    if not ok:
        raise ValidationError(pgettext("registrar.correction", "The published journal cannot be changed."))
    _write_audit(
        offering=topic.offering,
        actor=actor,
        request=request,
        reversal=reversal,
        kind="selfwork-correction-revert",
        item="self-work",
        old=correction.new_done,
        new=correction.old_done,
        enrollment_id=enrollment.pk,
    )
    return True


@transaction.atomic
def revert_last_coursework_correction(*, enrollment, by_user, request=None, correction_id=None) -> bool:
    correction, already_reversed = _select_active(
        CourseWorkCorrection,
        "coursework_correction",
        {"enrollment": enrollment},
        correction_id,
    )
    if correction is None:
        return False
    if already_reversed:
        return True
    from .correction_target_locks import lock_coursework

    enrollment, current = lock_coursework(enrollment)
    if current is None or (
        current.score,
        current.topic,
        current.submitted_on,
    ) != (correction.new_score, correction.new_topic, correction.new_date):
        raise _stale_error()
    actor = _real_actor(by_user, request)
    reversal = _create_reversal(
        correction=correction,
        target_field="coursework_correction",
        actor=actor,
    )
    empty = correction.old_score is None and not correction.old_topic and correction.old_date is None
    if empty:
        with journal_unlock():
            current.delete()
    else:
        ok = journal_extras.save_course_work(
            enrollment=enrollment,
            topic=correction.old_topic,
            score=correction.old_score,
            submitted_on=correction.old_date,
            by_user=actor,
            allow_locked=True,
        )
        if not ok:
            raise ValidationError(pgettext("registrar.correction", "The published journal cannot be changed."))
    _write_audit(
        offering=enrollment.offering,
        actor=actor,
        request=request,
        reversal=reversal,
        kind="coursework-correction-revert",
        item="course-work",
        old=grade_audit.score_repr(correction.new_score),
        new=grade_audit.score_repr(correction.old_score),
        enrollment_id=enrollment.pk,
    )
    return True


@transaction.atomic
def revert_last_component_correction(*, component, enrollment, by_user, request=None, correction_id=None) -> bool:
    correction, already_reversed = _select_active(
        ComponentScoreCorrection,
        "component_correction",
        {"component": component, "enrollment": enrollment},
        correction_id,
    )
    if correction is None:
        return False
    if already_reversed:
        return True
    from .correction_target_locks import lock_component

    component, enrollment, score = lock_component(component, enrollment)
    current = score.score if score else None
    if current != correction.new_score:
        raise _stale_error()
    actor = _real_actor(by_user, request)
    reversal = _create_reversal(
        correction=correction,
        target_field="component_correction",
        actor=actor,
    )
    with journal_unlock():
        if correction.old_score is None:
            ComponentScore.objects.filter(component=component, enrollment=enrollment).delete()
        else:
            ComponentScore.objects.update_or_create(
                organization=component.offering.organization,
                component=component,
                enrollment=enrollment,
                defaults={"score": Decimal(correction.old_score), "entered_by": actor},
            )
    _write_audit(
        offering=component.offering,
        actor=actor,
        request=request,
        reversal=reversal,
        kind="component-correction-revert",
        item="component",
        old=grade_audit.score_repr(correction.new_score),
        new=grade_audit.score_repr(correction.old_score),
        enrollment_id=enrollment.pk,
    )
    return True
