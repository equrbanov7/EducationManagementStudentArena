"""
Template tags for organization permissions.
"""

from django import template

from apps.organizations.permissions import has_permission

register = template.Library()


@register.simple_tag(takes_context=True)
def has_perm(context, permission):
    """
    Check if user has a specific permission in the current organization.

    Usage: {% has_perm 'course.create' as can_create %}
    """
    request = context.get("request")
    if not request:
        return False

    user_permissions = getattr(request, "org_permissions", [])
    return has_permission(user_permissions, permission)


@register.filter
def has_permission_filter(permissions, permission):
    """
    Filter to check permission from a list.

    Usage: {{ user_permissions|has_permission_filter:'course.create' }}
    """
    if not permissions:
        return False
    return has_permission(permissions, permission)


@register.simple_tag(takes_context=True)
def user_level(context):
    """
    Get user's maximum role level in the current organization.

    Usage: {% user_level as level %}
    """
    request = context.get("request")
    if not request:
        return 0

    memberships = getattr(request, "org_memberships", [])
    if not memberships:
        return 0

    return max([m.role.level for m in memberships], default=0)
