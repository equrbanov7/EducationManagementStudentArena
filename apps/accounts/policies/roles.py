"""
Role and permission policies for accounts.
"""

from ..models import ProfileRole


def is_superadmin_user(user):
    """Return whether the user has superadmin privileges."""
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and (user.is_superuser or getattr(user, "is_superadmin", False))
    )


def get_user_role_level(user):
    """Return the user's effective role level."""
    if not user or not getattr(user, "is_authenticated", False):
        return 0
    if is_superadmin_user(user):
        return 999
    if hasattr(user, "_highest_role_level"):
        return int(user._highest_role_level())

    profile = getattr(user, "profile", None)
    profile_role = getattr(profile, "role", "")
    return int(ProfileRole.LEVELS.get(profile_role, 0))


def user_has_any_role(user, role_names):
    """Return whether the user has any role from the provided set."""
    if not user or not getattr(user, "is_authenticated", False):
        return False

    normalized = set(role_names or [])
    if not normalized:
        return False
    if hasattr(user, "has_role"):
        return any(user.has_role(role_name) for role_name in normalized)

    profile = getattr(user, "profile", None)
    return getattr(profile, "role", None) in normalized


def get_profile_role_label(role):
    """Return the display label for a profile role."""
    return dict(ProfileRole.CHOICES).get(role, role)


def map_signup_role_to_profile_role(initial_role):
    """Normalize signup roles to profile roles."""
    role_mapping = {
        ProfileRole.STUDENT: ProfileRole.STUDENT,
        ProfileRole.LEAD_STUDENT: ProfileRole.LEAD_STUDENT,
        ProfileRole.TEACHER: ProfileRole.TEACHER,
        ProfileRole.ASSISTANT_TEACHER: ProfileRole.ASSISTANT_TEACHER,
        ProfileRole.HR: ProfileRole.HR,
        ProfileRole.MEMBER: ProfileRole.MEMBER,
        ProfileRole.ORG_ADMIN: ProfileRole.ORG_ADMIN,
        ProfileRole.ORG_OWNER: ProfileRole.ORG_OWNER,
    }
    return role_mapping.get(initial_role, ProfileRole.MEMBER)


def map_org_role_to_profile_role(role):
    """Map an organization membership role to a profile role."""
    role_name = ProfileRole.normalize_membership_role_name(getattr(role, "name", ""))
    if role_name == ProfileRole.MEMBER:
        return ProfileRole.MEMBER
    if role_name == ProfileRole.LEAD_STUDENT:
        return ProfileRole.LEAD_STUDENT
    if role_name == ProfileRole.STUDENT:
        return ProfileRole.STUDENT
    if role_name == ProfileRole.HR:
        return ProfileRole.HR
    if role_name in {ProfileRole.ASSISTANT_TEACHER, "assistant", "lab_assistant"}:
        return ProfileRole.ASSISTANT_TEACHER
    if role_name in {ProfileRole.TEACHER, "instructor", "professor", "associate_professor"}:
        return ProfileRole.TEACHER
    if getattr(role, "level", 0) >= ProfileRole.LEVELS.get(ProfileRole.ORG_ADMIN, 80):
        return ProfileRole.ORG_ADMIN
    return ProfileRole.MEMBER


def resolve_membership_role(organization, initial_role):
    """Resolve the best organization role for a requested profile role."""
    from apps.organizations.models import Role

    roles = Role.objects.filter(organization=organization, is_active=True)
    if not roles.exists():
        return None

    if initial_role in {ProfileRole.ORG_OWNER, ProfileRole.ORG_ADMIN}:
        return roles.order_by("-level").first()

    if initial_role == ProfileRole.MEMBER:
        member_role = roles.filter(name="member").first()
        if member_role:
            return member_role
        student_role = roles.filter(name="student").first()
        if student_role:
            return student_role
        return roles.order_by("level").first()

    if initial_role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}:
        return roles.filter(name="student").first() or roles.order_by("level").first()

    if initial_role == ProfileRole.ASSISTANT_TEACHER:
        for role_name in ["assistant_teacher", "assistant", "lab_assistant"]:
            match = roles.filter(name=role_name).first()
            if match:
                return match
        return (
            roles.filter(level__gte=40, level__lt=ProfileRole.LEVELS.get(ProfileRole.TEACHER, 60))
            .order_by("-level")
            .first()
            or roles.filter(level__gte=40).order_by("level").first()
            or roles.order_by("level").first()
        )

    if initial_role == ProfileRole.TEACHER:
        for role_name in ["teacher", "instructor", "professor", "associate_professor"]:
            match = roles.filter(name=role_name).first()
            if match:
                return match
        return roles.filter(level__gte=50).order_by("level").first() or roles.order_by("-level").first()

    if initial_role == ProfileRole.HR:
        hr_role = roles.filter(name="hr").first()
        if hr_role:
            return hr_role
        return Role.objects.create(
            organization=organization,
            name="hr",
            display_name="HR",
            level=65,
            scope_type="organization",
            permissions=["member.view", "member.invite", "member.edit"],
            is_system=False,
            is_active=True,
        )

    return roles.order_by("level").first()


def permission_is_grantable(permission, effective_permissions, grantable_permissions):
    """
    Return whether the permission can be granted by the acting user.
    """
    from apps.organizations.permissions import has_permission

    effective_list = list(effective_permissions)
    grantable_list = list(grantable_permissions)
    return has_permission(effective_list, permission) or has_permission(grantable_list, permission)


__all__ = [
    "get_profile_role_label",
    "get_user_role_level",
    "is_superadmin_user",
    "map_org_role_to_profile_role",
    "map_signup_role_to_profile_role",
    "permission_is_grantable",
    "resolve_membership_role",
    "user_has_any_role",
]
