"""Organization role-template and explicit-grant checks for cabinet FAQ editing."""

from functools import lru_cache

from core.constants import RoleScopeType

PERM_FAQ_VIDEO_MANAGE = "faq.video.manage"


@lru_cache(maxsize=16)
def _faq_editor_roles(org_type):
    from .default_roles import get_default_roles_for_org_type

    return frozenset(
        row["name"] for row in get_default_roles_for_org_type(org_type) if PERM_FAQ_VIDEO_MANAGE in row["permissions"]
    )


def has_faq_video_editor_grant(active_memberships) -> bool:
    """Only active, seeded organization roles designated by the university template can edit."""
    return any(
        membership.role.is_system
        and membership.role.scope_type == RoleScopeType.ORGANIZATION
        and membership.role.name in _faq_editor_roles(membership.organization.org_type)
        and PERM_FAQ_VIDEO_MANAGE in (membership.role.permissions or [])
        for membership in active_memberships
    )
