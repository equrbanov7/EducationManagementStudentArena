"""
Shared helpers for request-scoped tenant filtering.
"""

from django.db.models import Q

INT32_MAX = 2_147_483_647


def get_request_organization(request):
    """
    Resolve active organization from middleware/session, then profile fallback.
    """
    if request is None:
        return None

    request_org = getattr(request, "organization", None)
    if request_org is not None:
        return request_org

    user = getattr(request, "user", None)
    profile = getattr(user, "profile", None) if user is not None else None
    return getattr(profile, "organization", None)


def get_organization_int_id(organization):
    """
    Return int-compatible organization id for legacy IntegerField storage.
    """
    if organization is None:
        return None

    org_pk = getattr(organization, "pk", None)
    if isinstance(org_pk, int) and org_pk <= INT32_MAX:
        return org_pk
    return None


def scoped_by_organization_id(queryset, request, org_id_field, fallback_org_field=None):
    """
    Apply active-organization filtering for models using an integer org id field.

    Args:
        queryset: Base queryset to scope.
        request: Django request object (for active org lookup).
        org_id_field: Integer org id field on model (e.g. ``organization_id``).
        fallback_org_field: Optional FK path to organization for legacy rows where
            org_id is NULL (e.g. ``owner__profile__organization``).
    """
    organization = get_request_organization(request)
    if organization is None:
        return queryset

    org_int_id = get_organization_int_id(organization)
    if org_int_id is None:
        if fallback_org_field:
            return queryset.filter(**{f"{org_id_field}__isnull": True, fallback_org_field: organization})
        return queryset.none()

    filters = Q(**{org_id_field: org_int_id})
    if fallback_org_field:
        filters |= Q(**{f"{org_id_field}__isnull": True, fallback_org_field: organization})

    return queryset.filter(filters)
