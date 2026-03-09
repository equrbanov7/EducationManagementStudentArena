"""
Shared helpers for request-scoped tenant filtering.
"""

def get_request_organization(request):
    """
    Resolve the active organization selected on this request.
    """
    if request is None:
        return None

    return getattr(request, "organization", None)


def request_has_active_organization_context(request, *, allow_superadmin=True):
    """
    Return whether the request has a valid active tenant context.
    """
    organization = get_request_organization(request)
    if organization is None:
        return False

    user = getattr(request, "user", None)
    if allow_superadmin and bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False)):
        return True

    memberships = getattr(request, "org_memberships", None) or []
    return bool(memberships)


def scoped_by_organization(queryset, request, org_field="organization"):
    """
    Apply active-organization filtering for models bound to an Organization FK.

    Args:
        queryset: Base queryset to scope.
        request: Django request object (for active org lookup).
        org_field: Organization FK field on the model (defaults to ``organization``).
    """
    organization = get_request_organization(request)
    if organization is None or not request_has_active_organization_context(request):
        return queryset.none()

    return queryset.filter(**{org_field: organization})
