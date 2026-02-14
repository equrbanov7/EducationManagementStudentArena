"""
User role system using UserProfile.role field.
Adds role-checking properties and methods to the User model.
Checks profile.role first, falls back to Django Groups for backward compatibility.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist

from core.constants import ROLE_LEVEL_ADMIN, ROLE_LEVEL_MODERATOR, ROLE_LEVEL_TEACHER, ROLE_LEVEL_TOP_ADMIN, ROLE_LEVELS

User = get_user_model()


def _get_profile_safe(self):
    """Safely get user profile, returns None if not found."""
    try:
        return self.profile
    except (ObjectDoesNotExist, AttributeError):
        return None


def _get_profile_role(self):
    """Get role from profile, return empty string if no profile."""
    profile = _get_profile_safe(self)
    if profile and profile.role:
        return profile.role
    return ""


def _get_profile_role_level(self):
    """Get numeric role level from profile."""
    profile = _get_profile_safe(self)
    if profile:
        return profile.role_level
    return 0


def _has_group(self, name: str) -> bool:
    """Check if user belongs to a specific group (role) - legacy fallback."""
    return self.is_authenticated and self.groups.filter(name=name).exists()


def _get_all_roles(self):
    """Get list of all role names the user has (profile role + groups)."""
    if not self.is_authenticated:
        return []
    roles = []
    profile_role = _get_profile_role(self)
    if profile_role:
        roles.append(profile_role)
    group_roles = list(self.groups.values_list("name", flat=True))
    for gr in group_roles:
        if gr not in roles:
            roles.append(gr)
    return roles


def _highest_role_level(self):
    """Get the highest role level number among user's roles."""
    if not self.is_authenticated:
        return 0
    # Check profile role level first
    profile_level = _get_profile_role_level(self)
    # Also check group-based levels for backward compat
    group_roles = list(self.groups.values_list("name", flat=True))
    group_levels = [ROLE_LEVELS.get(role, 0) for role in group_roles]
    group_max = max(group_levels) if group_levels else 0
    return max(profile_level, group_max)


def _has_role(self, role_name: str) -> bool:
    """Check if user has a specific role (profile or group)."""
    if _get_profile_role(self) == role_name:
        return True
    return _has_group(self, role_name)


def _can_assign_role(self, target_role_name: str) -> bool:
    """Check if user can assign a specific role (user's level must be higher)."""
    if not self.is_authenticated:
        return False
    user_level = self._highest_role_level()
    target_level = ROLE_LEVELS.get(target_role_name, 0)
    return user_level > target_level


def _is_teacher_or_above(self):
    """Check if user has teacher role or any higher role (level >= 60).
    Django superusers always pass this check."""
    if self.is_superuser:
        return True
    return self._highest_role_level() >= ROLE_LEVEL_TEACHER


def _is_moderator_or_above(self):
    """Check if user has moderator role or any higher role (level >= 40).
    Django superusers always pass this check."""
    if self.is_superuser:
        return True
    return self._highest_role_level() >= ROLE_LEVEL_MODERATOR


def _is_admin_level(self):
    """Check if user has admin-level role (level >= 80, department_head and above).
    Django superusers always pass this check."""
    if self.is_superuser:
        return True
    return self._highest_role_level() >= ROLE_LEVEL_ADMIN


def _is_top_admin(self):
    """Check if user has top admin role (level >= 95, rector/director/vice_rector/vice_director).
    Django superusers always pass this check."""
    if self.is_superuser:
        return True
    return self._highest_role_level() >= ROLE_LEVEL_TOP_ADMIN


def _is_role(self, role_name):
    """Check profile role or group membership."""
    return _get_profile_role(self) == role_name or _has_group(self, role_name)


# Add basic role properties (check profile.role first, fallback to groups)
User.add_to_class("is_teacher", property(lambda self: _is_role(self, "teacher")))
User.add_to_class("is_student", property(lambda self: _is_role(self, "student")))
User.add_to_class("is_assistant_teacher", property(lambda self: _is_role(self, "assistant_teacher")))
User.add_to_class("is_moderator", property(lambda self: _is_role(self, "moderator")))

# University-specific roles
User.add_to_class("is_rector", property(lambda self: _is_role(self, "rector")))
User.add_to_class("is_vice_rector", property(lambda self: _is_role(self, "vice_rector")))
User.add_to_class("is_dean", property(lambda self: _is_role(self, "dean")))
User.add_to_class("is_vice_dean", property(lambda self: _is_role(self, "vice_dean")))
User.add_to_class("is_department_head", property(lambda self: _is_role(self, "department_head")))
User.add_to_class("is_professor", property(lambda self: _is_role(self, "professor")))
User.add_to_class(
    "is_associate_professor",
    property(lambda self: _is_role(self, "associate_professor")),
)
User.add_to_class("is_lab_assistant", property(lambda self: _is_role(self, "lab_assistant")))

# School-specific roles
User.add_to_class("is_director", property(lambda self: _is_role(self, "director")))
User.add_to_class("is_vice_director", property(lambda self: _is_role(self, "vice_director")))

# Course center-specific roles
User.add_to_class("is_manager", property(lambda self: _is_role(self, "manager")))
User.add_to_class("is_senior_instructor", property(lambda self: _is_role(self, "senior_instructor")))
User.add_to_class("is_instructor", property(lambda self: _is_role(self, "instructor")))
User.add_to_class("is_assistant", property(lambda self: _is_role(self, "assistant")))

# Individual/Personal roles
User.add_to_class("is_owner", property(lambda self: _is_role(self, "owner")))

# Org-level roles from ProfileRole
User.add_to_class("is_superadmin", property(lambda self: _get_profile_role(self) == "superadmin"))
User.add_to_class("is_org_owner", property(lambda self: _get_profile_role(self) == "org_owner"))
User.add_to_class("is_org_admin", property(lambda self: _get_profile_role(self) == "org_admin"))
User.add_to_class("is_lead_student", property(lambda self: _get_profile_role(self) == "lead_student"))

# Helper properties for role-level checks
User.add_to_class("is_teacher_or_above", property(_is_teacher_or_above))
User.add_to_class("is_moderator_or_above", property(_is_moderator_or_above))
User.add_to_class("is_admin_level", property(_is_admin_level))
User.add_to_class("is_top_admin", property(_is_top_admin))

# Helper methods
User.add_to_class("get_all_roles", _get_all_roles)
User.add_to_class("_get_all_roles", _get_all_roles)  # Private version for internal use
User.add_to_class("_highest_role_level", _highest_role_level)
User.add_to_class("highest_role_level", property(_highest_role_level))
User.add_to_class("has_role", _has_role)
User.add_to_class("can_assign_role", _can_assign_role)
