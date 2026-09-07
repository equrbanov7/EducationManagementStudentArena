"""
Role and permission policies for accounts.
"""

# M2 (2026-07-02): pure helper-lər core.roles-a köçürülüb; import səthi qorunur.
from core.roles import (  # noqa: F401
    ProfileRole,
    get_profile_role_label,
    get_user_role_level,
    is_superadmin_user,
    map_org_role_to_profile_role,
    map_signup_role_to_profile_role,
    user_has_any_role,
)


def resolve_membership_role(organization, initial_role):
    """Resolve the best organization role for a requested profile role."""
    from apps.organizations.models import Role

    roles = Role.objects.filter(organization=organization, is_active=True)
    if not roles.exists():
        return None

    # Dəqiq ad uyğunluğu birinci: `exam_center_staff`, `ikt_rehber`, `lead_student` və s.
    # üçün aşağıdakı budaqlar yox idi və funksiya təşkilatın ƏN AŞAĞI roluna (alumni,
    # level 5) düşürdü — «İmtahan Mərkəzi işçisi əlavə edildi» mesajı ilə məzun
    # üzvlüyü yaranırdı (QA 2026-09-05 PEOPLE-RBAC-09).
    exact = roles.filter(name=initial_role).first()
    if exact is not None:
        return exact

    if initial_role in {ProfileRole.ORG_OWNER, ProfileRole.ORG_ADMIN}:
        return roles.order_by("-level").first()

    if initial_role == ProfileRole.MEMBER:
        for role_name in ["member", "staff", "hr"]:
            match = roles.filter(name=role_name).first()
            if match:
                return match
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

    # Naməlum rol adı üçün səssiz «ən aşağı rol» əvəzləməsi YOXDUR — fail-closed.
    return None


def permission_is_grantable(permission, effective_permissions, grantable_permissions):
    """
    Return whether the permission can be granted by the acting user.
    """
    from core.permissions import has_permission

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
