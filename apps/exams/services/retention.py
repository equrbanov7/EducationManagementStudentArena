"""Academic-history retention guards for destructive exam operations."""

from dataclasses import dataclass

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils.translation import pgettext_lazy


class AcademicHistoryProtected(ValidationError):
    """Raised when a destructive action would erase an academic record."""


@dataclass(frozen=True)
class AttemptDeletionOutcome:
    selected_count: int
    deleted_count: int
    protected_ids: tuple[int, ...]


def _protected_history_error():
    return AcademicHistoryProtected(
        pgettext_lazy(
            "exams.service.retention",
            "Akademik cəhd tarixçəsi daimi silinə bilməz. İmtahanı arxivdə saxlayın.",
        ),
        code="academic_history_protected",
    )


def _locked_attempts_with_history(exam, attempt_ids):
    """Lock selected rows and annotate cross-app history without deep imports."""
    from apps.exams.models import ExamGradeEvent

    appeal_model = django_apps.get_model("appeals", "Appeal")
    adjustment_model = django_apps.get_model("appeals", "ScoreAdjustment")
    return list(
        exam.attempts.select_for_update()
        .filter(pk__in=attempt_ids)
        .annotate(
            has_grade_events=Exists(ExamGradeEvent.objects.filter(attempt_id=OuterRef("pk"))),
            has_appeals=Exists(appeal_model.objects.filter(attempt_id=OuterRef("pk"))),
            has_score_adjustments=Exists(adjustment_model.objects.filter(attempt_id=OuterRef("pk"))),
        )
        .order_by("pk")
    )


def _trial_attempt_can_be_deleted(attempt) -> bool:
    """Only disposable, unreviewed trial attempts may be physically removed."""
    return bool(
        attempt.is_trial
        and not attempt.checked_by_teacher
        and attempt.teacher_score is None
        and attempt.graded_by_id is None
        and not attempt.has_grade_events
        and not attempt.has_appeals
        and not attempt.has_score_adjustments
    )


@transaction.atomic
def delete_retention_safe_attempts(exam, attempt_ids, *, actor=None, request=None) -> AttemptDeletionOutcome:
    """Delete only disposable trial attempts; preserve every academic attempt.

    The exam row is the lock-order root.  This serializes the operation with
    exam lifecycle/destructive actions, while attempt row locks prevent a
    concurrent grade/appeal writer from turning a checked row into a delete.
    """
    exam_model = type(exam)
    locked_exam = exam_model.objects.select_for_update().get(pk=exam.pk)
    normalized_ids = sorted({int(attempt_id) for attempt_id in attempt_ids})
    attempts = _locked_attempts_with_history(locked_exam, normalized_ids)
    deletable_ids = [attempt.pk for attempt in attempts if _trial_attempt_can_be_deleted(attempt)]
    protected_ids = tuple(attempt.pk for attempt in attempts if attempt.pk not in deletable_ids)

    if deletable_ids:
        from apps.audit.public import log_action
        from core.constants import AuditAction

        log_action(
            action=AuditAction.DELETE,
            user=actor,
            organization=locked_exam.organization,
            obj=locked_exam,
            old_values={"trial_attempt_ids": deletable_ids},
            reason="trial_exam_attempts_permanently_deleted",
            request=request,
        )
        locked_exam.attempts.filter(pk__in=deletable_ids).delete()

    return AttemptDeletionOutcome(
        selected_count=len(attempts),
        deleted_count=len(deletable_ids),
        protected_ids=protected_ids,
    )


@transaction.atomic
def permanently_delete_exam_without_history(exam, *, actor=None, request=None) -> int:
    """Delete an already-soft-deleted exam only when it has no attempts."""
    exam_model = type(exam)
    locked_exam = exam_model.objects.select_for_update().get(pk=exam.pk)
    # Lock any extant attempt rows before deciding.  The PROTECT FK migration
    # is the final ORM/database backstop if a future caller skips this service.
    if locked_exam.attempts.select_for_update().order_by("pk").exists():
        raise _protected_history_error()

    from apps.audit.public import log_action
    from core.constants import AuditAction

    exam_pk = locked_exam.pk
    log_action(
        action=AuditAction.DELETE,
        user=actor,
        organization=locked_exam.organization,
        obj=locked_exam,
        old_values={"title": locked_exam.title, "slug": locked_exam.slug},
        reason="empty_exam_permanently_deleted",
        request=request,
    )
    locked_exam.delete()
    return exam_pk


__all__ = [
    "AcademicHistoryProtected",
    "AttemptDeletionOutcome",
    "delete_retention_safe_attempts",
    "permanently_delete_exam_without_history",
]
