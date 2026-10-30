"""Exact, source-reviewed catalogue creation without fuzzy aliases or imports."""

from django.apps import apps as django_apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from .models import Subject
from .subject_duplicates import normalized_subject_key


def exact_title_candidates(organization_id, names):
    keys = {normalized_subject_key(name) for name in names}
    return [
        row
        for row in Subject.objects.filter(organization_id=organization_id).values("id", "code", "name", "is_active")
        if normalized_subject_key(row["name"]) in keys
    ]


@transaction.atomic
def create_reviewed_subject(*, organization, user, identity, reason):
    """Create an explicitly pinned identity only when its exact title is absent."""
    chair = (
        django_apps.get_model("organizations", "OrgUnit")
        .objects.filter(organization=organization, pk=identity["chair_unit_id"], is_active=True)
        .first()
    )
    scope = django_apps.get_model("organizations", "OrgUnit").user_permission_scope(
        user, organization, "catalog.manage"
    )
    if (
        chair is None
        or not scope.has_structure_access
        or not (scope.is_org_wide or type(chair).objects.filter(pk=chair.pk).filter(scope.unit_subtree_q()).exists())
    ):
        raise PermissionDenied("reviewed_catalog_manage_scope_required")
    if (
        Subject.objects.filter(pk=identity["id"]).exists()
        or Subject.objects.filter(organization=organization, code__iexact=identity["code"]).exists()
    ):
        raise ValidationError("reviewed_catalog_identity_already_exists")
    if exact_title_candidates(organization.pk, [identity["name"]]):
        raise ValidationError("reviewed_catalog_exact_title_already_exists")
    subject = Subject(organization=organization, **identity)
    subject.full_clean()
    subject.save(force_insert=True)
    log_action(
        AuditAction.CREATE,
        user=user,
        organization=organization,
        obj=subject,
        reason=reason,
        new_values={key: identity[key] for key in ("code", "name", "ects", "kind")},
    )
    return subject
