"""Qrup köçürmə (group transfer, U6.1) — audited, history-preserving.

Moving a student to a new group updates their :class:`StudentAcademicRecord`
group and creates current-period enrollments for the new group's offerings.
Old group-specific enrollments are marked ``dropped`` and linked to their
successors; their journal, final-grade and correction provenance remains
queryable as history and is excluded from normal grade-write services.
All-specialty offerings (``group=None``) are left untouched.  Audit is
fail-closed inside the same database transaction.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.registrar import integrity, services
from apps.registrar.models import Enrollment, StudentAcademicRecord
from apps.registrar.reference_identity import (
    begin_authorized_group_transfer,
    finalize_authorized_group_transfer,
)
from core import audit as audit_service
from core.constants import AuditAction, OrgUnitType


def _validate_scope(record, new_group, period):
    """Reject cross-tenant references before any academic row is changed."""
    organization_id = record.organization_id
    if getattr(new_group, "organization_id", None) != organization_id:
        raise ValidationError("Yeni qrup tələbənin təşkilatına aid deyil.")
    if getattr(new_group, "unit_type", None) != OrgUnitType.GROUP:
        raise ValidationError("Yeni struktur vahidi akademik qrup olmalıdır.")
    if period is not None and getattr(period, "organization_id", None) != organization_id:
        raise ValidationError("Akademik dövr tələbənin təşkilatına aid deyil.")
    if period is None:
        if record.organization.academic_periods.filter(is_current=True, is_active=True).exists():
            raise ValidationError("Aktiv cari akademik dövr qrup köçürməsində göstərilməlidir.")
    elif not getattr(period, "is_current", False) or not getattr(period, "is_active", False):
        raise ValidationError("Qrup köçürməsi yalnız aktiv cari akademik dövr üçün aparıla bilər.")


def _audit(record, old_group, new_group, moved, created, by_user, reason, old_ids, new_ids):
    return audit_service.log_action(
        user=by_user if getattr(by_user, "pk", None) else None,
        organization=record.organization,
        obj=record,
        action=AuditAction.UPDATE,
        resource_type="registrar.group_transfer",
        resource_id=str(record.pk),
        resource_repr=f"{record.student_id} · {record.program.display_label}",
        old_values={"group_id": str(getattr(old_group, "pk", "") or "")},
        new_values={"group_id": str(new_group.pk)},
        changes={
            "moved_enrollment_ids": [str(value) for value in old_ids],
            "successor_enrollment_ids": [str(value) for value in new_ids],
            "created_count": created,
        },
        reason=reason
        or f"Qrup köçürmə: {getattr(old_group, 'name', '—')} → {new_group.name} "
        f"({moved} qeydiyyat tarixçəyə keçirildi)",
    )


@transaction.atomic
def transfer_student_group(*, record, new_group, period, by_user=None, reason=""):
    """Move a student without deleting or reactivating enrollment history.

    Returns ``{"moved": <historical old enrollments>, "created": <new enrollments>,
    "record": record}``. A no-op (moved=0) when the group is unchanged or None."""
    if new_group is None:
        return {"moved": 0, "created": 0, "record": record}
    _validate_scope(record, new_group, period)

    # Serialise concurrent/retried transfers and use the database's current
    # group rather than a potentially stale caller instance.
    record = (
        StudentAcademicRecord.objects.select_for_update(of=("self",))
        .select_related("organization", "student", "program", "group")
        .get(pk=record.pk, organization_id=record.organization_id)
    )
    old_group = record.group
    if new_group is None or (old_group is not None and new_group.id == old_group.id):
        return {"moved": 0, "created": 0, "record": record}
    integrity.validate_same_organization_actor(
        organization=record.organization,
        user=by_user,
        field_name="by_user",
        require_active=True,
    )
    if by_user is None:
        raise ValidationError({"by_user": "Qrup köçürməsi üçün icraçı tələb olunur."})

    old_enrollments = []
    if old_group is not None and period is not None:
        old_enrollments = list(
            Enrollment.objects.select_for_update(of=("self",))
            .filter(
                organization=record.organization,
                student=record.student,
                offering__period=period,
                offering__group=old_group,
                status=Enrollment.Status.ENROLLED,
            )
            .select_related("offering__subject")
        )

    evidence_id = begin_authorized_group_transfer(
        record=record,
        new_group=new_group,
        period=period,
        actor_id=by_user.pk,
    )

    created = 0
    successors = []
    for enrollment in old_enrollments:
        successor, was_created = services.enroll_student_in_subject(
            record=record,
            subject=enrollment.offering.subject,
            period=period,
            kind=enrollment.kind,
        )
        if successor.status != Enrollment.Status.ENROLLED:
            raise ValidationError(
                "Yeni qrupun açılışında bu tələbəyə aid tarixi qeydiyyat var; "
                "tarixçəni yenidən aktivləşdirmədən əvvəl inzibati yoxlama tələb olunur."
            )
        enrollment.status = Enrollment.Status.DROPPED
        enrollment.superseded_by = successor
        enrollment.full_clean(validate_unique=False, validate_constraints=False)
        enrollment.save(update_fields=["status", "superseded_by", "updated_at"])
        successors.append(successor)
        created += int(was_created)

    moved = len(old_enrollments)
    audit = _audit(
        record,
        old_group,
        new_group,
        moved,
        created,
        by_user,
        reason,
        [enrollment.pk for enrollment in old_enrollments],
        [enrollment.pk for enrollment in successors],
    )
    finalize_authorized_group_transfer(
        evidence_id=evidence_id,
        audit_id=audit.pk,
    )
    return {"moved": moved, "created": created, "record": record}
