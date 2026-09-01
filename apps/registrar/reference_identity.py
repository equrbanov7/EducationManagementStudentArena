"""Parent/reference identity validation and controlled group-transfer context."""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import connection

_ALWAYS_IMMUTABLE = {
    "registrar.enrollment": ("offering_id",),
    "registrar.lesson": ("offering_id",),
    "registrar.lessonmark": ("lesson_id", "enrollment_id"),
    "registrar.assessmentscheme": ("offering_id",),
    "registrar.scheduleslot": ("offering_id",),
    "registrar.componentscore": ("component_id", "enrollment_id"),
    "registrar.criterionscore": ("component_id", "criterion_id", "enrollment_id"),
    "registrar.selfworktopic": ("offering_id",),
    "registrar.selfworkmark": ("topic_id", "enrollment_id"),
    "registrar.coursework": ("enrollment_id",),
    "registrar.finalgrade": ("enrollment_id",),
    "registrar.resitrecord": ("enrollment_id",),
    "registrar.rubriccriterion": ("rubric_id",),
    # Təhvil qeydi hansı açılışa aid olduğunu SONRADAN dəyişə bilməz —
    # əks halda audit sətri başqa fənnin tarixçəsinə köçürülə bilərdi.
    "registrar.teachinghandover": ("offering_id",),
}

_CONDITIONAL_FIELDS = {
    "registrar.courseoffering": ("subject_id", "period_id", "group_id"),
    "registrar.assessmentcomponent": ("offering_id", "rubric_id"),
    "registrar.curriculum": ("program_id",),
}


@dataclass(frozen=True)
class _TransferBinding:
    record_id: str
    old_group: str
    new_group: str
    actor_id: str


_TRANSFER_BINDING: ContextVar[_TransferBinding | None] = ContextVar(
    "registrar_group_transfer_binding",
    default=None,
)
_TRANSFER_GUCS = (
    "app.registrar_group_transfer_evidence",
    "app.registrar_group_transfer_record",
    "app.registrar_group_transfer_old_group",
    "app.registrar_group_transfer_new_group",
    "app.registrar_group_transfer_actor",
    "app.registrar_group_transfer_txid",
)


def _identity(value) -> str:
    return str(value) if value is not None else "<null>"


def _requested(field: str, update_fields) -> bool:
    if update_fields is None:
        return True
    names = set(update_fields)
    return field in names or field.removesuffix("_id") in names


def _changed_fields(instance, candidates, update_fields=None):
    fields = tuple(field for field in candidates if _requested(field, update_fields))
    if instance._state.adding or not instance.pk or not fields:
        return {}, {}
    previous = type(instance)._base_manager.filter(pk=instance.pk).values(*fields).first()
    if previous is None:
        return {}, {}
    changed = {
        field: (previous[field], getattr(instance, field))
        for field in fields
        if previous[field] != getattr(instance, field)
    }
    return previous, changed


def _has_conditional_evidence(instance) -> bool:
    label = instance._meta.label_lower
    pk = instance.pk
    if label == "registrar.courseoffering":
        links = (
            ("Enrollment", "offering_id"),
            ("Lesson", "offering_id"),
            ("AssessmentScheme", "offering_id"),
            ("ScheduleSlot", "offering_id"),
            ("AssessmentComponent", "offering_id"),
            ("SelfWorkTopic", "offering_id"),
        )
    elif label == "registrar.assessmentcomponent":
        links = (
            ("ComponentScore", "component_id"),
            ("CriterionScore", "component_id"),
            ("ComponentScoreCorrection", "component_id"),
        )
    elif label == "registrar.curriculum":
        links = (
            ("CurriculumSubject", "curriculum_id"),
            ("StudentAcademicRecord", "curriculum_id"),
        )
    else:
        return False
    for model_name, field in links:
        model = django_apps.get_model("registrar", model_name)
        if model._base_manager.filter(**{field: pk}).exists():
            return True
    return False


def _transfer_matches(record_id, old_group, new_group) -> bool:
    binding = _TRANSFER_BINDING.get()
    return binding is not None and (
        binding.record_id,
        binding.old_group,
        binding.new_group,
    ) == (
        _identity(record_id),
        _identity(old_group),
        _identity(new_group),
    )


def validate_reference_identity(instance, *, update_fields=None) -> None:
    """Reject identity changes while allowing ordinary mutable-field updates."""

    label = instance._meta.label_lower
    fields = _ALWAYS_IMMUTABLE.get(label) or _CONDITIONAL_FIELDS.get(label) or ()
    if label == "registrar.studentacademicrecord":
        fields = ("group_id",)
    _previous, changed = _changed_fields(instance, fields, update_fields)
    if not changed:
        return
    if label == "registrar.studentacademicrecord":
        old_group, new_group = changed["group_id"]
        if _transfer_matches(instance.pk, old_group, new_group):
            return
        raise ValidationError({"group": "Qrup yalnız rəsmi köçürmə xidməti ilə dəyişdirilə bilər."})
    if label in _CONDITIONAL_FIELDS and not _has_conditional_evidence(instance):
        return
    errors = {field.removesuffix("_id"): "Tarixi sübutdan sonra bağlı obyekt dəyişdirilə bilməz." for field in changed}
    raise ValidationError(errors)


class ReferenceIdentityValidationMixin:
    """Mirror PostgreSQL identity guards in Django model validation and save."""

    def clean(self):
        super().clean()
        validate_reference_identity(self)

    def save(self, *args, **kwargs):
        validate_reference_identity(self, update_fields=kwargs.get("update_fields"))
        return super().save(*args, **kwargs)


def _clear_transfer_gucs() -> None:
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT " + ", ".join("set_config(%s, '', true)" for _name in _TRANSFER_GUCS),
            list(_TRANSFER_GUCS),
        )


def begin_authorized_group_transfer(*, record, new_group, period, actor_id):
    """Apply one transition and create pending, transaction-bound evidence."""

    if not connection.in_atomic_block:
        raise RuntimeError("registrar_group_transfer_requires_atomic_transaction")
    if actor_id is None:
        raise ValidationError({"by_user": "Qrup köçürməsi üçün icraçı tələb olunur."})
    evidence_id = uuid.uuid4()
    binding = _TransferBinding(
        record_id=_identity(record.pk),
        old_group=_identity(record.group_id),
        new_group=_identity(new_group.pk),
        actor_id=_identity(actor_id),
    )
    token = _TRANSFER_BINDING.set(binding)
    try:
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT public.registrar_begin_student_group_transfer(%s, %s, %s, %s, %s, %s)",
                    [
                        str(evidence_id),
                        str(record.pk),
                        str(record.group_id) if record.group_id else None,
                        str(new_group.pk),
                        str(period.pk) if period is not None else None,
                        actor_id,
                    ],
                )
            record.group = new_group
        else:
            old_group_id = record.group_id
            record.group = new_group
            record.save(update_fields=["group", "updated_at"])
            evidence_model = django_apps.get_model("registrar", "GroupTransferEvidence")
            evidence_model.objects.create(
                id=evidence_id,
                organization_id=record.organization_id,
                record_id=record.pk,
                old_group_id=old_group_id,
                new_group_id=new_group.pk,
                period_id=getattr(period, "pk", None),
                actor_ref=actor_id,
                transaction_id=f"sqlite-{evidence_id}",
                expected_enrollment_ids=[],
            )
    finally:
        _TRANSFER_BINDING.reset(token)
        if connection.vendor == "postgresql" and not connection.needs_rollback:
            _clear_transfer_gucs()
    return evidence_id


def finalize_authorized_group_transfer(*, evidence_id, audit_id) -> None:
    """Finalize pending evidence only after enrollment lineage and audit exist."""

    if not connection.in_atomic_block:
        raise RuntimeError("registrar_group_transfer_requires_atomic_transaction")
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT public.registrar_finalize_student_group_transfer(%s, %s)",
                [str(evidence_id), str(audit_id)],
            )
        return
    evidence_model = django_apps.get_model("registrar", "GroupTransferEvidence")
    updated = evidence_model.objects.filter(pk=evidence_id, is_finalized=False).update(
        audit_ref=audit_id,
        is_finalized=True,
    )
    if updated != 1:
        raise ValidationError("Qrup köçürmə sübutu yekunlaşdırıla bilmədi.")
