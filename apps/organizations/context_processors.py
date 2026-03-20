"""
Context processors for making organization data available in templates.
"""


def organization_context(request):
    """
    Add organization-related context to all templates.

    Context variables:
        - current_organization: The active organization for this request
        - user_organizations: All organizations the user is a member of
        - user_permissions: User's permissions in the current organization
        - user_max_level: User's highest role level in the current organization

    This processor reads exclusively from attributes already attached to
    ``request`` by ``OrganizationMiddleware``, so it adds **zero** additional
    database queries per request.
    """
    context = {
        "current_organization": None,
        "user_organizations": [],
        "user_permissions": [],
        "user_max_level": 0,
    }

    if not hasattr(request, "user") or not request.user.is_authenticated:
        return context

    # Current organization
    if hasattr(request, "organization"):
        context["current_organization"] = request.organization

    # User's permissions in current org
    if hasattr(request, "org_permissions"):
        context["user_permissions"] = request.org_permissions

    # User's max level and organization list – derived from the membership
    # queryset already materialized by OrganizationMiddleware; no extra DB hit.
    all_memberships = getattr(request, "_all_org_memberships", None)
    if all_memberships is None:
        # Fall back to the current-org memberships if the full set is absent.
        all_memberships = getattr(request, "org_memberships", None) or []

    if all_memberships:
        context["user_max_level"] = max((m.role.level for m in all_memberships), default=0)

        # Build unique org list preserving order (primary orgs first, then alpha).
        seen_ids: set = set()
        orgs = []
        for m in all_memberships:
            if m.organization_id not in seen_ids and getattr(m.organization, "is_active", True):
                seen_ids.add(m.organization_id)
                orgs.append(m.organization)
        context["user_organizations"] = sorted(orgs, key=lambda o: o.name)

    return context
