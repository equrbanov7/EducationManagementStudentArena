"""Qrup köçürmə (group transfer, U6.1) — audited, enrollment-aware.

Moving a student to a new group updates their :class:`StudentAcademicRecord`
group and re-points the current period's **group-specific** enrollments to the
new group's offerings (same subject). The old group-specific enrollments are
dropped (their journal marks cascade), so the student starts fresh in the new
group's sections — the realistic behaviour for a mid-semester transfer.
All-specialty offerings (``group=None``) are left untouched. The transition is
audited (best-effort, via the app registry → no static audit import).
"""

from __future__ import annotations

from django.db import transaction

from apps.registrar import services
from apps.registrar.models import Enrollment


def _audit(record, old_group, new_group, dropped, created, by_user, reason):
    try:
        from django.apps import apps as django_apps

        from core.constants import AuditAction

        AuditLog = django_apps.get_model("audit", "AuditLog")
        AuditLog.objects.create(
            user=by_user if getattr(by_user, "pk", None) else None,
            organization=record.organization,
            action=AuditAction.UPDATE,
            resource_type="registrar.group_transfer",
            resource_id=str(record.pk),
            resource_repr=f"{record.student_id} · {record.program.code}",
            reason=reason
            or f"Qrup köçürmə: {getattr(old_group, 'name', '—')} → {getattr(new_group, 'name', '—')} "
            f"({dropped} bağlantı köçürüldü)",
        )
    except Exception:  # noqa: BLE001 — audit must never block the transfer
        pass


@transaction.atomic
def transfer_student_group(*, record, new_group, period, by_user=None, reason=""):
    """Move *record*'s student to *new_group* and re-point current-period enrollments.

    Returns ``{"moved": <dropped old enrollments>, "created": <new enrollments>,
    "record": record}``. A no-op (moved=0) when the group is unchanged or None."""
    old_group = record.group
    if new_group is None or (old_group is not None and new_group.id == old_group.id):
        return {"moved": 0, "created": 0, "record": record}

    old_enrollments = list(
        Enrollment.objects.filter(
            organization=record.organization,
            student=record.student,
            offering__period=period,
            offering__group=old_group,
        ).select_related("offering__subject")
    )
    # Capture (subject, kind) before dropping so we can re-enroll into the new group.
    pairs = [(e.offering.subject, e.kind) for e in old_enrollments]
    dropped = len(old_enrollments)
    for enrollment in old_enrollments:
        enrollment.delete()  # cascades this enrollment's lesson marks

    record.group = new_group
    record.save(update_fields=["group"])

    created = 0
    for subject, kind in pairs:
        _, was_created = services.enroll_student_in_subject(record=record, subject=subject, period=period, kind=kind)
        created += int(was_created)

    _audit(record, old_group, new_group, dropped, created, by_user, reason)
    return {"moved": dropped, "created": created, "record": record}
