"""Akademik status state-machine (U5+) — audited transitions.

A student's :class:`StudentAcademicRecord` carries an ``status`` (enrolled /
academic leave / expelled / graduated). Changing it keeps the legacy
``is_active`` flag consistent (only *enrolled* students are active) and writes a
best-effort audit entry so the transition is traceable. Any transition is
permitted (registrars correct mistakes); the value is validated against the
enum. This layer is additive and never blocks the domain action.
"""

from __future__ import annotations

from apps.registrar.models import AcademicStatus


def is_active_for(status_value) -> bool:
    """Only an *enrolled* student counts as academically active."""
    return status_value == AcademicStatus.ENROLLED


def audit_status_change(*, record, previous, by_user=None, reason="") -> None:
    """Write an audit entry when the record's status actually changed.

    Resolved via the app registry so registrar keeps no static import of the
    audit module (module-boundary safe). Never raises — auditing must not block
    the status change."""
    if previous is None or previous == record.status:
        return
    try:
        from django.apps import apps as django_apps

        from core.constants import AuditAction

        AuditLog = django_apps.get_model("audit", "AuditLog")
        AuditLog.objects.create(
            user=by_user if getattr(by_user, "pk", None) else None,
            organization=record.organization,
            action=AuditAction.UPDATE,
            resource_type="registrar.student_status",
            resource_id=str(record.pk),
            resource_repr=f"{record.student_id} · {record.program.display_label}",
            reason=reason or f"Akademik status: {previous} → {record.status}",
        )
    except Exception:  # noqa: BLE001 — audit must never block the domain action
        pass
