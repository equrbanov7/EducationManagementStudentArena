"""Fixed recovery audit locator shared by strict recovery and metadata diagnostics."""

from django.apps import apps
from django.db.models import Q

from .four_cell_history_spec import ORG


def audit_locator(cases):
    from .four_cell_history import mark_ids

    ids = {c[k] for c in cases.values() for k in ("offering_id", "lesson_id", "enrollment_id")}
    ids |= set(mark_ids(_cases=cases).values())
    query = Q(resource_id__in=ids)
    for field in ("changes", "old_values", "new_values"):
        for pk in ids:
            query |= Q(**{field + "__icontains": pk})
    return query


def audit_queryset(cases):
    return (
        apps.get_model("audit.AuditLog")
        .objects.filter(organization_id=ORG)
        .filter(audit_locator(cases))
        .order_by("created_at", "pk")
    )
