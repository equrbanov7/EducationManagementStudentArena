"""
Role-based access control helpers.

Centralized RBAC logic for account views: resolving a user's profile roles,
computing per-user capabilities and allowed profile sections, and collecting
effective/grantable permissions. Keep tenant and permission checks strict.
"""

from ...models import ProfileRole
from ...policies import is_superadmin_user, permission_is_grantable, user_has_any_role
from .constants import PROFILE_ROLE_LABELS, PROFILE_ROLE_NAMES, PROFILE_ROLE_NAMES_MANAGEABLE
from .tenant import _bind_active_role_context


def _is_superadmin_user(user):
    return is_superadmin_user(user)


def _user_has_any_role(user, role_names):
    return user_has_any_role(user, role_names)


def _permission_is_grantable(permission, effective_permissions, grantable_permissions):
    return permission_is_grantable(permission, effective_permissions, grantable_permissions)


def _extract_profile_roles_for_user(user):
    if not user:
        return []

    active_organization = getattr(user, "active_organization", None)
    if active_organization is not None:
        _bind_active_role_context(
            user,
            active_organization,
            memberships=getattr(user, "_active_org_memberships", None),
        )

    roles = []
    if hasattr(user, "get_all_roles"):
        candidates = user.get_all_roles()
    else:
        candidates = []

    for role_name in candidates:
        if role_name in PROFILE_ROLE_NAMES and role_name not in roles:
            roles.append(role_name)

    return roles


def _assignable_profile_roles_for_user(user):
    if _is_superadmin_user(user):
        return [(name, display) for name, display in ProfileRole.CHOICES if name in PROFILE_ROLE_NAMES_MANAGEABLE]

    user_level = user._highest_role_level() if hasattr(user, "_highest_role_level") else 0
    return [
        (name, display)
        for name, display in ProfileRole.CHOICES
        if name in PROFILE_ROLE_NAMES_MANAGEABLE and ProfileRole.LEVELS.get(name, 0) < user_level
    ]


def _decorate_manage_role_profiles(profiles, *, actor_level, is_superadmin, organization=None, actor_user=None):
    actor_user_id = getattr(actor_user, "id", None)
    owner_self_management_enabled = bool(
        actor_user_id and organization is not None and getattr(organization, "owner_id", None) == actor_user_id
    )

    for profile in profiles:
        _bind_active_role_context(profile.user, organization)
        profile_user_is_superadmin = getattr(profile.user, "is_superuser", False) or getattr(
            profile.user, "is_superadmin", False
        )
        if profile_user_is_superadmin:
            current_roles = PROFILE_ROLE_NAMES_MANAGEABLE
        else:
            current_roles = _extract_profile_roles_for_user(profile.user)
        primary_role_name = None
        if current_roles:
            primary_role_name = max(current_roles, key=lambda role_name: ProfileRole.LEVELS.get(role_name, 0))
        profile.current_roles = current_roles
        profile.current_role_items = [
            {
                "name": role_name,
                "label": PROFILE_ROLE_LABELS.get(role_name, role_name),
                "level": ProfileRole.LEVELS.get(role_name, 0),
                "is_primary": role_name == primary_role_name,
            }
            for role_name in current_roles
        ]
        profile.primary_role = None
        if primary_role_name:
            profile.primary_role = {
                "name": primary_role_name,
                "label": PROFILE_ROLE_LABELS.get(primary_role_name, primary_role_name),
                "level": ProfileRole.LEVELS.get(primary_role_name, 0),
            }

        target_level = profile.user._highest_role_level() if hasattr(profile.user, "_highest_role_level") else 0
        is_self_profile = actor_user_id is not None and profile.user_id == actor_user_id
        profile.can_edit_roles = (
            is_superadmin or actor_level > target_level or (is_self_profile and owner_self_management_enabled)
        )


def _collect_actor_permissions(user, organization, *, request=None):
    """
    Return two sets:
    1. effective permissions user currently has in org
    2. explicitly grantable permissions declared as `grant:<permission>` in role permissions

    P1.4 — Per-request memoization (təhlükəsiz):
    Eyni request boyunca eyni (user_id, organization_id) cütü üçün təkrar
    DB sorğusu olmaması üçün nəticə `request._actor_perms_cache` dict-ində
    saxlanılır. Cross-request cache yoxdur — RLS və icazə dəyişiklikləri
    request başında həmişə yenidən qiymətləndirilir.
    """
    from apps.organizations.models import Membership

    user_id = getattr(user, "pk", None) or getattr(user, "id", None)
    org_id = getattr(organization, "pk", None) or getattr(organization, "id", None)
    cache_key = (user_id, org_id)
    cache_owner = request if request is not None else None
    if cache_owner is not None and user_id is not None and org_id is not None:
        cache = getattr(cache_owner, "_actor_perms_cache", None)
        if cache is None:
            cache = {}
            try:
                cache_owner._actor_perms_cache = cache
            except Exception:  # noqa: BLE001 — request obyekti immutable ola bilər
                cache_owner = None
        if cache_owner is not None and cache_key in cache:
            cached_effective, cached_grantable = cache[cache_key]
            # Cache-i mutasiya etməmək üçün surət qaytarırıq.
            return set(cached_effective), set(cached_grantable)

    effective_permissions = set()
    grantable_permissions = set()

    memberships = Membership.objects.filter(user=user, organization=organization, is_active=True).select_related("role")
    for membership in memberships:
        for permission in membership.role.permissions or []:
            if permission.startswith("grant:"):
                grantable_permissions.add(permission.split("grant:", 1)[1].strip())
            else:
                effective_permissions.add(permission)

    if cache_owner is not None and user_id is not None and org_id is not None:
        cache = getattr(cache_owner, "_actor_perms_cache", None)
        if cache is not None:
            cache[cache_key] = (set(effective_permissions), set(grantable_permissions))

    return effective_permissions, grantable_permissions


def _role_capabilities(user, profile):
    scoped_roles = _extract_profile_roles_for_user(user)
    profile_role = getattr(profile, "role", ProfileRole.MEMBER) if profile else ProfileRole.MEMBER
    active_organization = getattr(user, "active_organization", None)
    has_active_org_context = bool(scoped_roles or active_organization)
    role = scoped_roles[0] if scoped_roles else profile_role
    is_superadmin = _is_superadmin_user(user)
    is_student = _user_has_any_role(user, {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT})
    if not has_active_org_context and profile_role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}:
        is_student = True
    is_teacher = _user_has_any_role(user, {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER})
    is_owner_of_active_org = bool(
        active_organization is not None and getattr(active_organization, "owner_id", None) == user.id
    )
    is_org_admin = (
        _user_has_any_role(user, {ProfileRole.ORG_ADMIN, ProfileRole.ORG_OWNER, ProfileRole.HR})
        or is_owner_of_active_org
    )
    user_level = 999 if is_superadmin else (user._highest_role_level() if hasattr(user, "_highest_role_level") else 0)

    can_manage_org = is_superadmin or is_org_admin
    can_view_owned_learning = is_superadmin or is_teacher or is_org_admin
    can_review_submissions = is_superadmin or is_teacher
    can_view_student_assignments = is_student or _user_has_any_role(user, {ProfileRole.MEMBER})
    can_manage_blog = getattr(user, "is_authenticated", False)
    can_approve_posts = is_superadmin or user_level >= ProfileRole.LEVELS.get(ProfileRole.TEACHER, 60)

    # Allow tenant admins to delegate either student-management or
    # invite-only access to teachers without elevating them to full admins.
    teacher_can_manage_students = False
    teacher_can_invite_members = False
    teacher_has_student_org_access = False
    if is_teacher and not is_org_admin and not is_superadmin and active_organization:
        from apps.organizations.permissions import has_permission as _has_permission

        actor_perms, _ = _collect_actor_permissions(user, active_organization)
        teacher_can_manage_students = _has_permission(list(actor_perms), "member.student_manage")
        teacher_can_invite_members = _has_permission(list(actor_perms), "member.invite")
        teacher_has_student_org_access = teacher_can_manage_students or teacher_can_invite_members

    if is_superadmin:
        allowed_sections = {
            "profile-info",
            "notifications",
            "posts",
            "my-results",
            "my-exams",
            "my-courses",
            "courses",
            "assigned-exams",
            "assigned-courses",
            "groups",
            "pending-review",
            "review-results",
            "role-assignment",
            "student-organization-management",
            "permission-editor",
            "manage-roles",
            "create-category",
            "category-management",
            "superadmin-org-features",
            "superadmin-organizations",
            "superadmin-users",
            "superadmin-ai",
            "superadmin-contact-messages",  # public contact form inbox
            "pending-post-approvals",
            "blog",
            "edit-profile",
            "change-password",
            "publish-notification",
            "delete-account",
            "statistics",
        }
    else:
        allowed_sections = {
            "profile-info",
            "notifications",
            "posts",
            "blog",
            "edit-profile",
            "change-password",
            "delete-account",
            "statistics",
        }
        allowed_sections.add("my-results")
        if can_view_student_assignments:
            allowed_sections.add("pending-answers")

        if is_org_admin:
            allowed_sections.update(
                {
                    "my-exams",
                    "my-courses",
                    "groups",
                    "role-assignment",
                    "student-organization-management",
                    "permission-editor",
                    "manage-roles",
                    "publish-notification",
                }
            )

        if is_teacher:
            allowed_sections.update(
                {"my-exams", "my-courses", "groups", "pending-review", "review-results", "publish-notification"}
            )
            if teacher_has_student_org_access:
                allowed_sections.add("student-organization-management")

        if is_student:
            allowed_sections.update({"assigned-exams", "assigned-courses"})

        if not (is_student or is_teacher or is_org_admin):
            allowed_sections.update({"courses", "assigned-exams", "assigned-courses", "groups"})

    has_admin_control_role = (
        _user_has_any_role(user, {ProfileRole.ORG_ADMIN, ProfileRole.ORG_OWNER}) or is_owner_of_active_org
    )

    if (
        profile_role
        in {
            ProfileRole.STUDENT,
            ProfileRole.LEAD_STUDENT,
            ProfileRole.TEACHER,
            ProfileRole.ASSISTANT_TEACHER,
            ProfileRole.MEMBER,
            ProfileRole.HR,
        }
        and not is_superadmin
        and not has_admin_control_role
    ):
        allowed_sections.add("student-organization-request")

    if can_manage_blog:
        allowed_sections.add("create-post")
    if can_approve_posts:
        allowed_sections.add("pending-post-approvals")

    return {
        "role": role,
        "is_superadmin": is_superadmin,
        "is_student": is_student,
        "is_teacher": is_teacher,
        "is_org_admin": is_org_admin,
        "can_manage_org": can_manage_org,
        "can_view_owned_learning": can_view_owned_learning,
        "can_review_submissions": can_review_submissions,
        "can_view_student_assignments": can_view_student_assignments,
        "can_view_blog": True,
        "can_manage_blog": can_manage_blog,
        "can_approve_posts": can_approve_posts,
        "allowed_sections": allowed_sections,
        "teacher_can_manage_students": teacher_can_manage_students,
        "teacher_can_invite_members": teacher_can_invite_members,
        "teacher_has_student_org_access": teacher_has_student_org_access,
    }
