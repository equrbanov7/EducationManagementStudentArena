"""Fixed recovery audit locator shared by strict recovery and metadata diagnostics."""

from django.apps import apps

from .four_cell_history_spec import ORG
from .history_reference_locator import reference_locator


def audit_locator(cases, *, referenced_ids=(), source_points=()):
    from .four_cell_history import mark_ids

    ids = {c[k] for c in cases.values() for k in ("offering_id", "lesson_id", "enrollment_id")}
    ids |= set(mark_ids(_cases=cases).values())
    return reference_locator(
        apps.get_model("audit.AuditLog")._meta.db_table,
        insensitive_ids=ids,
        literal_ids=referenced_ids,
        source_points=source_points,
    )


def audit_queryset(cases):
    return (
        apps.get_model("audit.AuditLog")
        .objects.filter(organization_id=ORG)
        .filter(audit_locator(cases))
        .order_by("created_at", "pk")
    )
