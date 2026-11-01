"""Internal fixed-four fresh SELECT evidence in an existing recovery transaction."""

from django.apps import apps
from django.db import connection
from django.db.models import Q

from .scoped_snapshot.four_cell_history import collect_available_history
from .scoped_snapshot.four_cell_history_spec import ORG
from .syllabus_content_export.limits import query_budget


def fixed_four_recovery_history(*, actor, organization):
    """No input selector or writes; caller's outer atomic owns recovery and rollback."""
    if (
        connection.vendor != "postgresql"
        or not connection.in_atomic_block
        or str(organization.pk) != ORG
        or not actor.is_active
        or not actor.is_superuser
    ):
        raise ValueError("fixed_four_tenant_atomic_actor_required")
    User = apps.get_model("auth.User")
    if not User.objects.filter(
        Q(profile__organization_id=ORG)
        | Q(memberships__organization_id=ORG, memberships__is_active=True)
        | Q(owned_organizations__pk=ORG),
        pk=actor.pk,
        is_active=True,
        is_superuser=True,
    ).exists():
        raise ValueError("fixed_four_actor_tenant_required")
    if (
        not apps.get_model("organizations.Organization")
        .objects.filter(pk=ORG, is_active=True, status="active")
        .exists()
    ):
        raise ValueError("fixed_four_tenant_inactive")
    with query_budget():
        return collect_available_history()
