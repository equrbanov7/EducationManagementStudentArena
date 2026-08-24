"""Qiymət dəyişikliyi audit izi — grade-change audit trail (U7.3).

Records *who* changed *which* grade, *when*, and *old → new* into the shared
``audit`` app (``AuditLog``, which already carries ``changes``/``old_values``/
``new_values`` JSON fields). Design goals:

* **Low noise** — one aggregated entry per save operation, not per cell.
* **Only real changes** — a cell is logged only when ``old != new`` (re-saving an
  unchanged grid produces zero audit entries).
* **Configurable failure policy** — ordinary grade entry remains best-effort,
  while formal correction workflows opt into fail-closed auditing so their
  domain mutation and audit evidence commit or roll back together.

The trail is queryable by ``resource_type`` (``registrar.grade.*``) +
``resource_id`` (the offering id) and is surfaced on the journal page
(:func:`get_grade_history`) so corrections are transparent to teachers/approvers.
"""

from __future__ import annotations

from decimal import Decimal

# resource_type prefix — all grade-change kinds share it for a single-filter fetch.
_RESOURCE_PREFIX = "registrar.grade"


def student_label(enrollment) -> str:
    student = getattr(enrollment, "student", None)
    if student is None:
        return str(getattr(enrollment, "id", "?"))
    return student.get_full_name() or student.username


def score_repr(score) -> str:
    """Human/JSON-safe representation of a score cell (Decimal → str)."""
    if score is None or score == "":
        return "—"
    if isinstance(score, Decimal):
        return f"{score:.2f}".rstrip("0").rstrip(".")
    return str(score)


def log_grade_changes(*, offering, by_user, kind, changes, fail_closed=False):
    """Write one aggregated grade-change audit entry.

    ``kind``  — short slug (``mark`` / ``component`` / ``final`` / ``resit``).
    ``changes`` — list of ``{"student", "item", "old", "new"}`` (already filtered
    to actual changes; all values JSON-serialisable strings).
    ``fail_closed`` — re-raise storage errors for formal, transaction-bound
    workflows such as documented corrections.
    """
    if not changes:
        return
    try:
        from django.apps import apps as django_apps

        from core.constants import AuditAction

        AuditLog = django_apps.get_model("audit", "AuditLog")
        AuditLog.objects.create(
            user=by_user if getattr(by_user, "pk", None) else None,
            organization=offering.organization,
            action=AuditAction.UPDATE,
            resource_type=f"{_RESOURCE_PREFIX}.{kind}",
            resource_id=str(offering.pk),
            resource_repr=f"{offering.subject.code} — qiymət dəyişikliyi ({len(changes)})",
            changes=changes,
            new_values={"count": len(changes)},
            reason=f"{len(changes)} qiymət dəyişikliyi ({kind}).",
        )
    except Exception:  # noqa: BLE001 — caller chooses the transaction policy
        if fail_closed:
            raise


_KIND_LABELS = {
    "mark": "Davamiyyət/bal",
    "component": "Komponent balı",
    "final": "Yekun imtahan",
    "resit": "Təkrar imtahan",
}


def get_grade_history(*, offering, limit=20):
    """Recent grade-change entries for this offering (newest first)."""
    try:
        from django.apps import apps as django_apps

        AuditLog = django_apps.get_model("audit", "AuditLog")
        rows = (
            AuditLog.objects.filter(
                organization=offering.organization,
                resource_type__startswith=_RESOURCE_PREFIX,
                resource_id=str(offering.pk),
            )
            .select_related("user")
            .order_by("-created_at")[:limit]
        )
    except Exception:  # noqa: BLE001
        return []
    history = []
    for row in rows:
        kind = (row.resource_type or "").rsplit(".", 1)[-1]
        history.append(
            {
                "when": row.created_at,
                "user": row.user,
                "kind": kind,
                "kind_label": _KIND_LABELS.get(kind, kind),
                "changes": row.changes or [],
                "count": len(row.changes or []),
            }
        )
    return history
