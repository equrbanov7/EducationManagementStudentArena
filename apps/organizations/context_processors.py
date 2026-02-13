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

    # User's max level in current org
    if hasattr(request, "org_memberships") and request.org_memberships:
        context["user_max_level"] = max(
            [m.role.level for m in request.org_memberships], default=0
        )

    # All organizations user is a member of
    from .models import Organization

    user_org_ids = (
        request.user.memberships.filter(is_active=True)
        .values_list("organization_id", flat=True)
        .distinct()
    )

    context["user_organizations"] = list(
        Organization.active.filter(id__in=user_org_ids).order_by("name")
    )

    return context
