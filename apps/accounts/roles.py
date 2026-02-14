"""
User role system using Django Groups.
Adds role-checking properties and methods to the User model.
"""

from django.contrib.auth import get_user_model

from core.constants import ROLE_LEVEL_ADMIN, ROLE_LEVEL_MODERATOR, ROLE_LEVEL_TEACHER, ROLE_LEVEL_TOP_ADMIN, ROLE_LEVELS

User = get_user_model()


def _has_group(self, name: str) -> bool:
    """Check if user belongs to a specific group (role)."""
    return self.is_authenticated and self.groups.filter(name=name).exists()


def _get_all_roles(self):
    """Get list of all role names the user has."""
    if not self.is_authenticated:
        return []
    return list(self.groups.values_list("name", flat=True))


def _highest_role_level(self):
    """Get the highest role level number among user's roles."""
    if not self.is_authenticated:
        return 0
    roles = self._get_all_roles()
    levels = [ROLE_LEVELS.get(role, 0) for role in roles]
    return max(levels) if levels else 0


def _has_role(self, role_name: str) -> bool:
    """Check if user has a specific role."""
    return _has_group(self, role_name)


def _can_assign_role(self, target_role_name: str) -> bool:
    """Check if user can assign a specific role (user's level must be higher)."""
    if not self.is_authenticated:
        return False
    user_level = self._highest_role_level()
    target_level = ROLE_LEVELS.get(target_role_name, 0)
    return user_level > target_level


def _is_teacher_or_above(self):
    """Check if user has teacher role or any higher role (level >= 60)."""
    return self._highest_role_level() >= ROLE_LEVEL_TEACHER


def _is_moderator_or_above(self):
    """Check if user has moderator role or any higher role (level >= 40)."""
    return self._highest_role_level() >= ROLE_LEVEL_MODERATOR


def _is_admin_level(self):
    """Check if user has admin-level role (level >= 80, department_head and above)."""
    return self._highest_role_level() >= ROLE_LEVEL_ADMIN


def _is_top_admin(self):
    """Check if user has top admin role (level >= 95, rector/director/vice_rector/vice_director)."""
    return self._highest_role_level() >= ROLE_LEVEL_TOP_ADMIN


# Add all basic role properties (exact role checks)
User.add_to_class("is_teacher", property(lambda self: _has_group(self, "teacher")))
User.add_to_class("is_student", property(lambda self: _has_group(self, "student")))
User.add_to_class("is_assistant_teacher", property(lambda self: _has_group(self, "assistant_teacher")))
User.add_to_class("is_moderator", property(lambda self: _has_group(self, "moderator")))

# University-specific roles
User.add_to_class("is_rector", property(lambda self: _has_group(self, "rector")))
User.add_to_class("is_vice_rector", property(lambda self: _has_group(self, "vice_rector")))
User.add_to_class("is_dean", property(lambda self: _has_group(self, "dean")))
User.add_to_class("is_vice_dean", property(lambda self: _has_group(self, "vice_dean")))
User.add_to_class("is_department_head", property(lambda self: _has_group(self, "department_head")))
User.add_to_class("is_professor", property(lambda self: _has_group(self, "professor")))
User.add_to_class(
    "is_associate_professor",
    property(lambda self: _has_group(self, "associate_professor")),
)
User.add_to_class("is_lab_assistant", property(lambda self: _has_group(self, "lab_assistant")))

# School-specific roles
User.add_to_class("is_director", property(lambda self: _has_group(self, "director")))
User.add_to_class("is_vice_director", property(lambda self: _has_group(self, "vice_director")))

# Course center-specific roles
User.add_to_class("is_manager", property(lambda self: _has_group(self, "manager")))
User.add_to_class("is_senior_instructor", property(lambda self: _has_group(self, "senior_instructor")))
User.add_to_class("is_instructor", property(lambda self: _has_group(self, "instructor")))
User.add_to_class("is_assistant", property(lambda self: _has_group(self, "assistant")))

# Individual/Personal roles
User.add_to_class("is_owner", property(lambda self: _has_group(self, "owner")))

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
