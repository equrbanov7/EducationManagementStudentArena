"""Application guardrails for the append-only exam grade ledger."""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import pgettext_lazy


def _immutable_error():
    return ValidationError(
        pgettext_lazy(
            "exams.model.grade_event.error",
            "Qiymətləndirmə tarixçəsi append-only-dir və dəyişdirilə/silinilə bilməz.",
        )
    )


class ExamGradeEventQuerySet(models.QuerySet):
    """Reject ordinary ORM mutation paths; PostgreSQL trigger is authoritative."""

    def update(self, **kwargs):
        raise _immutable_error()

    def delete(self):
        raise _immutable_error()


class ExamGradeEventManager(models.Manager.from_queryset(ExamGradeEventQuerySet)):
    pass


__all__ = ["ExamGradeEventManager", "_immutable_error"]
