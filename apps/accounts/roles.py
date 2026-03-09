"""
Organization-scoped role system for the User model.

Authorization resolves from active organization memberships only.
Legacy Django auth groups are not used for role checks.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist

from apps.accounts.models import ProfileRole
from core.constants import ROLE_LEVEL_ADMIN, ROLE_LEVEL_MODERATOR, ROLE_LEVEL_TEACHER, ROLE_LEVEL_TOP_ADMIN, ROLE_LEVELS

User = get_user_model()


def _get_profile_safe(self):
    try:
        return self.profile
    except (ObjectDoesNotExist, AttributeError):
        return None


def _is_authenticated_user(self):
    return bool(self and getattr(self, "is_authenticated", False))


def _set_active_organization_context(self, organization=None, *, memberships=None, permissions=None):
    self._active_organization = organization
    self._active_org_memberships = list(memberships) if memberships is not None else None
    self._active_org_permissions = list(permissions) if permissions is not None else None
    return self


def _clear_active_organization_context(self):
    self._active_organization = None
    self._active_org_memberships = None
    self._active_org_permissions = None
    return self


def _resolve_active_organization_context(self):
    if not _is_authenticated_user(self):
        return None, []

    cached_memberships = getattr(self, "_active_org_memberships", None)
    active_organization = getattr(self, "_active_organization", None)

    if cached_memberships is not None:
        memberships = [membership for membership in cached_memberships if getattr(membership, "is_active", False)]
        if active_organization is not None:
            memberships = [
                membership
                for membership in memberships
                if getattr(membership, "organization_id", None) == active_organization.id
            ]
        elif memberships:
            active_organization = memberships[0].organization
        return active_organization, memberships

    if active_organization is not None:
        memberships = list(
            self.memberships.filter(organization=active_organization, is_active=True)
            .select_related("organization", "role", "scope_unit")
            .order_by("-is_primary", "-role__level")
        )
        self._active_org_memberships = memberships
        return active_organization, memberships

    memberships = list(
        self.memberships.filter(is_active=True, organization__is_active=True)
        .select_related("organization", "role", "scope_unit")
        .order_by("-is_primary", "-role__level")
    )
    unique_org_ids = {membership.organization_id for membership in memberships}
    if len(unique_org_ids) == 1 and memberships:
        active_organization = memberships[0].organization
        self._active_organization = active_organization
        self._active_org_memberships = memberships
        return active_organization, memberships

    return None, []


def _should_use_legacy_profile_fallback(self):
    if not _is_authenticated_user(self):
        return False

    active_organization = getattr(self, "_active_organization", None)
    if active_organization is not None:
        return False

    return not self.memberships.filter(is_active=True, organization__is_active=True).exists()


def _get_active_organization(self):
    organization, _memberships = _resolve_active_organization_context(self)
    return organization


def _membership_role_aliases(self, membership, active_organization):
    role = getattr(membership, "role", None)
    role_name = ProfileRole.normalize_membership_role_name(getattr(role, "name", ""))
    is_org_owner = bool(active_organization and getattr(active_organization, "owner_id", None) == self.id)
    return ProfileRole.aliases_for_membership_role(
        role_name,
        level=getattr(role, "level", 0),
        is_org_owner=is_org_owner,
    )


def _membership_effective_level(self, membership, active_organization):
    role = getattr(membership, "role", None)
    role_name = ProfileRole.normalize_membership_role_name(getattr(role, "name", ""))
    aliases = _membership_role_aliases(self, membership, active_organization)

    candidate_levels = [getattr(role, "level", 0), ROLE_LEVELS.get(role_name, 0)]
    candidate_levels.extend(ROLE_LEVELS.get(alias, 0) for alias in aliases)
    candidate_levels.extend(ProfileRole.LEVELS.get(alias, 0) for alias in aliases)
    return max(candidate_levels, default=0)


def _get_all_roles(self):
    if not _is_authenticated_user(self):
        return []

    active_organization, memberships = _resolve_active_organization_context(self)
    if not memberships and _should_use_legacy_profile_fallback(self):
        profile = _get_profile_safe(self)
        legacy_role = getattr(profile, "role", None)
        return [legacy_role] if legacy_role in ProfileRole.LEVELS else []

    role_names = []
    for membership in memberships:
        aliases = _membership_role_aliases(self, membership, active_organization)
        for role_name in aliases:
            if role_name in ProfileRole.LEVELS and role_name not in role_names:
                role_names.append(role_name)

    role_names.sort(
        key=lambda role_name: (
            ProfileRole.LEVELS.get(role_name, ROLE_LEVELS.get(role_name, 0)),
            role_name,
        ),
        reverse=True,
    )
    return role_names


def _highest_role_level(self):
    if not _is_authenticated_user(self):
        return 0
    if self.is_superuser:
        return 999

    active_organization, memberships = _resolve_active_organization_context(self)
    if not memberships and _should_use_legacy_profile_fallback(self):
        profile = _get_profile_safe(self)
        return ProfileRole.LEVELS.get(getattr(profile, "role", None), 0)

    levels = [_membership_effective_level(self, membership, active_organization) for membership in memberships]
    return max(levels, default=0)


def _has_role(self, role_name: str) -> bool:
    if not _is_authenticated_user(self):
        return False

    normalized_role_name = ProfileRole.normalize_membership_role_name(role_name)
    if normalized_role_name == ProfileRole.SUPERADMIN:
        profile = _get_profile_safe(self)
        return bool(self.is_superuser or getattr(profile, "role", None) == ProfileRole.SUPERADMIN)

    active_organization, memberships = _resolve_active_organization_context(self)
    if not memberships:
        if _should_use_legacy_profile_fallback(self):
            profile = _get_profile_safe(self)
            return getattr(profile, "role", None) == normalized_role_name
        return False

    for membership in memberships:
        if normalized_role_name in _membership_role_aliases(self, membership, active_organization):
            return True
    return False


def _can_assign_role(self, target_role_name: str) -> bool:
    if not _is_authenticated_user(self):
        return False
    user_level = self._highest_role_level()
    normalized_target_role = ProfileRole.normalize_membership_role_name(target_role_name)
    target_level = max(
        ProfileRole.LEVELS.get(normalized_target_role, 0),
        ROLE_LEVELS.get(normalized_target_role, 0),
    )
    return user_level > target_level


def _is_teacher_or_above(self):
    if self.is_superuser:
        return True
    return self._highest_role_level() >= ROLE_LEVEL_TEACHER


def _is_moderator_or_above(self):
    if self.is_superuser:
        return True
    return self._highest_role_level() >= ROLE_LEVEL_MODERATOR


def _is_admin_level(self):
    if self.is_superuser:
        return True
    return self._highest_role_level() >= ROLE_LEVEL_ADMIN


def _is_top_admin(self):
    if self.is_superuser:
        return True
    return self._highest_role_level() >= ROLE_LEVEL_TOP_ADMIN


User.add_to_class("set_active_organization_context", _set_active_organization_context)
User.add_to_class("clear_active_organization_context", _clear_active_organization_context)
User.add_to_class("get_active_organization", _get_active_organization)
User.add_to_class("active_organization", property(_get_active_organization))

User.add_to_class("is_teacher", property(lambda self: _has_role(self, "teacher")))
User.add_to_class("is_student", property(lambda self: _has_role(self, "student")))
User.add_to_class("is_assistant_teacher", property(lambda self: _has_role(self, "assistant_teacher")))
User.add_to_class("is_moderator", property(lambda self: _has_role(self, "moderator")))

User.add_to_class("is_rector", property(lambda self: _has_role(self, "rector")))
User.add_to_class("is_vice_rector", property(lambda self: _has_role(self, "vice_rector")))
User.add_to_class("is_dean", property(lambda self: _has_role(self, "dean")))
User.add_to_class("is_vice_dean", property(lambda self: _has_role(self, "vice_dean")))
User.add_to_class("is_department_head", property(lambda self: _has_role(self, "department_head")))
User.add_to_class("is_professor", property(lambda self: _has_role(self, "professor")))
User.add_to_class(
    "is_associate_professor",
    property(lambda self: _has_role(self, "associate_professor")),
)
User.add_to_class("is_lab_assistant", property(lambda self: _has_role(self, "lab_assistant")))

User.add_to_class("is_director", property(lambda self: _has_role(self, "director")))
User.add_to_class("is_vice_director", property(lambda self: _has_role(self, "vice_director")))

User.add_to_class("is_manager", property(lambda self: _has_role(self, "manager")))
User.add_to_class("is_senior_instructor", property(lambda self: _has_role(self, "senior_instructor")))
User.add_to_class("is_instructor", property(lambda self: _has_role(self, "instructor")))
User.add_to_class("is_assistant", property(lambda self: _has_role(self, "assistant")))

User.add_to_class("is_owner", property(lambda self: _has_role(self, "owner")))

User.add_to_class(
    "is_superadmin",
    property(
        lambda self: bool(
            self.is_superuser or getattr(_get_profile_safe(self), "role", None) == ProfileRole.SUPERADMIN
        )
    ),
)
User.add_to_class("is_org_owner", property(lambda self: _has_role(self, ProfileRole.ORG_OWNER)))
User.add_to_class("is_org_admin", property(lambda self: _has_role(self, ProfileRole.ORG_ADMIN)))
User.add_to_class("is_member", property(lambda self: _has_role(self, ProfileRole.MEMBER)))
User.add_to_class("is_hr", property(lambda self: _has_role(self, ProfileRole.HR)))
User.add_to_class("is_lead_student", property(lambda self: _has_role(self, ProfileRole.LEAD_STUDENT)))

User.add_to_class("is_teacher_or_above", property(_is_teacher_or_above))
User.add_to_class("is_moderator_or_above", property(_is_moderator_or_above))
User.add_to_class("is_admin_level", property(_is_admin_level))
User.add_to_class("is_top_admin", property(_is_top_admin))

User.add_to_class("get_all_roles", _get_all_roles)
User.add_to_class("_get_all_roles", _get_all_roles)
User.add_to_class("_highest_role_level", _highest_role_level)
User.add_to_class("highest_role_level", property(_highest_role_level))
User.add_to_class("has_role", _has_role)
User.add_to_class("can_assign_role", _can_assign_role)
