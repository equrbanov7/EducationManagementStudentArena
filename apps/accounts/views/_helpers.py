"""
Shared helper functions for account views.
"""

from datetime import timedelta
from decimal import InvalidOperation
from pathlib import PurePosixPath
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.core.signing import TimestampSigner
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext

from apps.courses.models import Course
from apps.exams.models import Exam
from apps.notifications.models import (
    MembershipRequestRoleType,
    StudentOrganizationRequest,
    StudentOrganizationRequestStatus,
)
from core.constants import OrganizationType
from core.helpers import ASSIGNED_TASK_FILTER_CHOICES, REVIEW_EDIT_LOCK_WINDOW
from core.rls import bypass_rls
from core.tenancy import get_request_organization, scoped_by_organization

from ..models import ProfileRole
from ..policies import (
    is_superadmin_user,
    map_org_role_to_profile_role,
    map_signup_role_to_profile_role,
    permission_is_grantable,
    resolve_membership_role,
    user_has_any_role,
)
from ..queries import (
    get_assigned_courses_for_user,
    get_assigned_exams_for_user,
    get_signup_lookup_payload,
    pending_student_request_queryset,
)
from ..services import (
    activate_verified_student_membership,
    close_other_pending_student_requests,
    parse_decimal_score,
    set_student_org_request_status,
    sync_profile_pending_request_snapshot,
)

User = get_user_model()
signer = TimestampSigner()

# Constants
RESULT_FILTER_CHOICES = {"all", "exams", "courses", "labs", "independent"}
PENDING_ANSWER_FILTER_CHOICES = RESULT_FILTER_CHOICES
PENDING_REVIEW_TYPE_CHOICES = {"all", "exams", "assignments", "projects", "labs"}
PENDING_REVIEW_STATUS_CHOICES = {"all", "submitted", "expired", "pending", "late"}
PROFILE_ROLE_LABELS = dict(ProfileRole.CHOICES)
PROFILE_ROLE_NAMES = set(PROFILE_ROLE_LABELS.keys())
PROFILE_ROLE_NAMES_MANAGEABLE = PROFILE_ROLE_NAMES - {ProfileRole.SUPERADMIN, ProfileRole.ORG_OWNER}
REVIEW_EDIT_WINDOW_MINUTES = int(REVIEW_EDIT_LOCK_WINDOW.total_seconds() // 60)
REVIEW_EDIT_WINDOW = timedelta(minutes=REVIEW_EDIT_WINDOW_MINUTES)
STUDENT_ORG_MANAGEMENT_MIN_LEVEL = ProfileRole.LEVELS.get(ProfileRole.HR, 65)
STUDENT_PENDING_INVITE_TITLE = "__student_pending_invite__"
STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH = 280
MAX_PROFILE_AVATAR_SIZE_BYTES = 10 * 1024 * 1024
PROFILE_AVATAR_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
STUDENT_MEMBER_GROUPS_DISPLAY_LIMIT = 50
ROLE_ASSIGNMENT_OPERATION_TOKEN_SALT = "accounts.role_assignment.operation"  # nosec B105
ROLE_ASSIGNMENT_OPERATION_TOKEN_MAX_AGE_SECONDS = 60 * 5


def _is_superadmin_user(user):
    return is_superadmin_user(user)


def _get_active_organization(request):
    """
    Use middleware-selected organization first; fallback to profile organization.
    """
    return get_request_organization(request)


def _bind_active_role_context(user, organization, *, memberships=None, permissions=None):
    if user and hasattr(user, "set_active_organization_context"):
        user.set_active_organization_context(
            organization,
            memberships=memberships,
            permissions=permissions,
        )
    return user


def _tenant_scoped_courses(request, queryset=None):
    base_queryset = queryset if queryset is not None else Course.objects.all()
    return scoped_by_organization(base_queryset, request)


def _tenant_scoped_exams(request, queryset=None):
    base_queryset = queryset if queryset is not None else Exam.objects.all()
    return scoped_by_organization(base_queryset, request)


def _assigned_courses_queryset(request, user):
    return _tenant_scoped_courses(request, get_assigned_courses_for_user(user))


def _assigned_exams_queryset(request, user, *, active_only=True):
    return _tenant_scoped_exams(
        request,
        get_assigned_exams_for_user(user, active_only=active_only, include_public=False),
    ).distinct()


def _normalized_org_name(value):
    return " ".join((value or "").strip().lower().split())


def _membership_request_role_type_for_profile_role(profile_role):
    if profile_role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}:
        return MembershipRequestRoleType.STUDENT
    if profile_role in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}:
        return MembershipRequestRoleType.TEACHER
    return MembershipRequestRoleType.STAFF


def _profile_role_for_membership_request_type(role_type):
    if role_type == MembershipRequestRoleType.STUDENT:
        return ProfileRole.STUDENT
    if role_type == MembershipRequestRoleType.TEACHER:
        return ProfileRole.TEACHER
    return ProfileRole.MEMBER


def _membership_request_role_label(role_type):
    if role_type == MembershipRequestRoleType.STUDENT:
        return pgettext("membership_request.role", "Student")
    if role_type == MembershipRequestRoleType.TEACHER:
        return pgettext("membership_request.role", "Teacher")
    return pgettext("membership_request.role", "Staff")


def _pending_student_request_queryset(*, user=None, organization=None, statuses=None):
    return pending_student_request_queryset(user=user, organization=organization, statuses=statuses)


def _set_student_org_request_status(
    *,
    request_obj,
    status,
    note="",
    responded_by=None,
    when=None,
):
    return set_student_org_request_status(
        request_obj=request_obj,
        status=status,
        note=note,
        responded_by=responded_by,
        when=when,
    )


def _sync_profile_pending_request_snapshot(profile):
    return sync_profile_pending_request_snapshot(profile)


def _close_other_pending_student_requests(*, user, accepted_organization, responded_by=None, note=""):
    return close_other_pending_student_requests(
        user=user,
        accepted_organization=accepted_organization,
        responded_by=responded_by,
        note=note,
    )


def _user_has_any_role(user, role_names):
    return user_has_any_role(user, role_names)


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


def _sync_user_role_memberships(user, organization, desired_role_names, *, actor=None, editable_role_names=None):
    from apps.organizations.models import Membership

    if organization is None:
        return []

    desired = set(desired_role_names or []) & PROFILE_ROLE_NAMES
    editable = set(editable_role_names or PROFILE_ROLE_NAMES) & PROFILE_ROLE_NAMES
    editable -= {ProfileRole.SUPERADMIN, ProfileRole.ORG_OWNER}

    desired_membership_roles = {}
    for role_name in sorted(desired & editable, key=lambda item: ProfileRole.LEVELS.get(item, 0), reverse=True):
        membership_role = _resolve_membership_role(organization, role_name)
        if membership_role is not None:
            desired_membership_roles[membership_role.id] = membership_role

    current_memberships = list(
        Membership.objects.filter(user=user, organization=organization)
        .select_related("role")
        .order_by("-is_active", "-is_primary", "-role__level")
    )

    memberships_to_deactivate = []
    for membership in current_memberships:
        mapped_role = _map_org_role_to_profile_role(membership.role)
        if mapped_role in editable and membership.role_id not in desired_membership_roles and membership.is_active:
            memberships_to_deactivate.append(membership.id)

    if memberships_to_deactivate:
        Membership.objects.filter(id__in=memberships_to_deactivate).update(is_active=False, is_primary=False)

    for membership_role in desired_membership_roles.values():
        Membership.objects.update_or_create(
            user=user,
            organization=organization,
            role=membership_role,
            scope_unit=None,
            defaults={
                "is_active": True,
                "is_primary": False,
                "assigned_by": actor,
            },
        )

    final_memberships = list(
        Membership.objects.filter(user=user, organization=organization, is_active=True)
        .select_related("role")
        .order_by("-role__level", "-is_primary", "id")
    )
    Membership.objects.filter(user=user, organization=organization, is_primary=True).update(is_primary=False)
    if final_memberships:
        primary_membership = final_memberships[0]
        primary_membership.is_primary = True
        primary_membership.save(update_fields=["is_primary"])
        final_memberships[0] = primary_membership

    _bind_active_role_context(user, organization, memberships=final_memberships)
    return final_memberships


def _resolve_next_url(request, fallback_url):
    next_url = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if not next_url:
        return fallback_url

    if url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return fallback_url


def _safe_same_origin_redirect_path(request, candidate_url):
    raw_url = (candidate_url or "").strip()
    if not raw_url:
        return ""

    if not url_has_allowed_host_and_scheme(
        url=raw_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return ""

    return raw_url


def _normalize_review_result_item_type(raw_type):
    normalized = (raw_type or "").strip().lower()
    if normalized in {"assignment", "assignments"}:
        return "assignment"
    if normalized in {"project", "projects"}:
        return "project"
    if normalized in {"lab", "labs"}:
        return "lab"
    return ""


def _pending_review_type_label(raw_type):
    normalized = (raw_type or "").strip().lower()
    if normalized == "exam":
        return "Yazılı imtahan"
    if normalized == "assignment":
        return "Sərbəst iş"
    if normalized == "project":
        return "Kurs işi"
    if normalized == "lab":
        return "Lab işi"
    return "Tapşırıq"


def _is_review_window_closed(reviewed_at, *, now=None):
    if not reviewed_at:
        return False
    current_time = now or timezone.now()
    return current_time >= reviewed_at + REVIEW_EDIT_WINDOW


def _is_review_window_open(reviewed_at, *, now=None):
    if not reviewed_at:
        return False
    return not _is_review_window_closed(reviewed_at, now=now)


def _review_window_seconds_left(reviewed_at, *, now=None):
    if not reviewed_at:
        return 0
    current_time = now or timezone.now()
    remaining = int((reviewed_at + REVIEW_EDIT_WINDOW - current_time).total_seconds())
    return max(0, remaining)


def _is_result_visible_to_student(reviewed_at):
    if not reviewed_at:
        return False
    return _is_review_window_closed(reviewed_at)


def _parse_decimal_score(raw_value):
    score = parse_decimal_score((raw_value or "").strip().replace(",", "."), default=None)
    if score is None:
        raise InvalidOperation
    return score


def _extract_assignment_attachments(submission):
    attachments = []
    seen_attachments = set()

    def _append_attachment(name, url):
        clean_name = (name or "").strip()
        clean_url = (url or "").strip()
        if not clean_url:
            return
        attachment_key = (clean_name, clean_url)
        if attachment_key in seen_attachments:
            return
        seen_attachments.add(attachment_key)
        attachments.append({"name": clean_name or PurePosixPath(clean_url).name, "url": clean_url})

    legacy_file = getattr(submission, "file", None)
    if legacy_file:
        _append_attachment(
            PurePosixPath(getattr(legacy_file, "name", "fayl")).name,
            getattr(legacy_file, "url", ""),
        )

    files_payload = getattr(submission, "files", None)
    if not isinstance(files_payload, list):
        return attachments

    def _normalize_url(candidate_url):
        if candidate_url.startswith(("http://", "https://", "/")):
            return candidate_url
        return f"/media/{candidate_url.lstrip('/')}"

    for item in files_payload:
        if isinstance(item, str):
            clean = item.strip()
            if clean:
                _append_attachment(PurePosixPath(clean).name, _normalize_url(clean))
            continue
        if not isinstance(item, dict):
            continue

        candidate_url = (item.get("url") or item.get("file") or item.get("path") or "").strip()
        if not candidate_url:
            continue
        candidate_name = (item.get("name") or item.get("filename") or "").strip()
        _append_attachment(candidate_name or PurePosixPath(candidate_url).name, _normalize_url(candidate_url))

    return attachments


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
            "superadmin-organizations",
            "pending-post-approvals",
            "blog",
            "edit-profile",
            "change-password",
            "publish-notification",
        }
    else:
        allowed_sections = {
            "profile-info",
            "notifications",
            "posts",
            "blog",
            "edit-profile",
            "change-password",
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
    }


def _collect_actor_permissions(user, organization):
    """
    Return two sets:
    1. effective permissions user currently has in org
    2. explicitly grantable permissions declared as `grant:<permission>` in role permissions
    """
    from apps.organizations.models import Membership

    effective_permissions = set()
    grantable_permissions = set()

    memberships = Membership.objects.filter(user=user, organization=organization, is_active=True).select_related("role")
    for membership in memberships:
        for permission in membership.role.permissions or []:
            if permission.startswith("grant:"):
                grantable_permissions.add(permission.split("grant:", 1)[1].strip())
            else:
                effective_permissions.add(permission)

    return effective_permissions, grantable_permissions


def _ensure_profile_admin_membership(user, organization):
    """
    Backfill membership for org owner/admin profiles that are missing organization membership.
    This prevents false-negative `role.assign` errors for valid tenant admins.
    """
    from apps.organizations.models import Membership
    from apps.organizations.services import ensure_owner_membership

    if _is_superadmin_user(user):
        return

    profile = getattr(user, "profile", None)
    profile_role = getattr(profile, "role", None)
    profile_org = getattr(profile, "organization", None)
    is_org_owner = bool(organization and getattr(organization, "owner_id", None) == getattr(user, "id", None))

    if not is_org_owner and profile_role not in {ProfileRole.ORG_OWNER, ProfileRole.ORG_ADMIN}:
        return
    if not organization or profile_org != organization:
        return
    if Membership.objects.filter(user=user, organization=organization, is_active=True).exists():
        return
    ensure_owner_membership(user, organization)


def _permission_is_grantable(permission, effective_permissions, grantable_permissions):
    return permission_is_grantable(permission, effective_permissions, grantable_permissions)


def _map_signup_role_to_profile_role(initial_role):
    return map_signup_role_to_profile_role(initial_role)


def _map_org_role_to_profile_role(role):
    return map_org_role_to_profile_role(role)


def _resolve_membership_role(organization, initial_role):
    return resolve_membership_role(organization, initial_role)


def _get_signup_lookup_payload():
    return get_signup_lookup_payload()


def _activate_verified_student_membership(user):
    return activate_verified_student_membership(user)


def _result_status_badge(status, is_graded=False):
    """Normalize source-specific statuses into submitted/graded/pending."""
    if is_graded:
        return "graded"

    normalized_status = (status or "").lower()
    if normalized_status in {"graded"}:
        return "graded"
    if normalized_status in {"grading", "returned", "rejected", "expired", "draft", "in_progress"}:
        return "pending"
    return "submitted"


def _normalize_results_filter(value):
    normalized = (value or "all").lower()
    if normalized in RESULT_FILTER_CHOICES:
        return normalized
    return "all"


def _normalize_pending_answers_filter(value):
    normalized = (value or "all").lower()
    if normalized in PENDING_ANSWER_FILTER_CHOICES:
        return normalized
    return "all"


def _append_query_params(url, **params):
    clean_params = {key: value for key, value in params.items() if value not in (None, "")}
    if not clean_params:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode(clean_params)}"


def _query_string(**params):
    clean_params = {key: value for key, value in params.items() if value not in (None, "")}
    return urlencode(clean_params)


def _build_user_organization_access_rows(
    user,
    *,
    active_organization=None,
    include_active_superadmin_org=False,
    profile_section="profile-info",
):
    from apps.organizations.models import Membership, Organization

    if not user or not getattr(user, "is_authenticated", False):
        return []

    membership_queryset = (
        Membership.objects.filter(
            user=user,
            is_active=True,
            organization__is_active=True,
            organization__status="active",
        )
        .select_related("organization", "organization__owner", "role")
        .order_by("organization__name", "-is_primary", "-role__level", "role__display_name")
    )

    grouped_rows = {}
    for membership in membership_queryset:
        organization = membership.organization
        row = grouped_rows.setdefault(
            organization.id,
            {
                "organization": organization,
                "memberships": [],
                "role_labels": [],
                "access_origin": "membership",
                "is_owner": organization.owner_id == user.id,
            },
        )
        row["memberships"].append(membership)
        role_label = membership.role.display_name
        if role_label not in row["role_labels"]:
            row["role_labels"].append(role_label)

    owned_organizations = (
        Organization.objects.filter(owner=user, is_active=True, status="active")
        .select_related("owner")
        .order_by("name")
    )
    for organization in owned_organizations:
        row = grouped_rows.setdefault(
            organization.id,
            {
                "organization": organization,
                "memberships": [],
                "role_labels": [],
                "access_origin": "owner",
                "is_owner": True,
            },
        )
        row["is_owner"] = True
        if PROFILE_ROLE_LABELS[ProfileRole.ORG_OWNER] not in row["role_labels"]:
            row["role_labels"].insert(0, PROFILE_ROLE_LABELS[ProfileRole.ORG_OWNER])
        if row["access_origin"] != "membership":
            row["access_origin"] = "owner"

    if (
        include_active_superadmin_org
        and _is_superadmin_user(user)
        and active_organization is not None
        and getattr(active_organization, "is_active", False)
        and getattr(active_organization, "status", "") == "active"
        and active_organization.id not in grouped_rows
    ):
        grouped_rows[active_organization.id] = {
            "organization": active_organization,
            "memberships": [],
            "role_labels": [PROFILE_ROLE_LABELS[ProfileRole.SUPERADMIN]],
            "access_origin": "superadmin",
            "is_owner": active_organization.owner_id == user.id,
        }

    org_ids = list(grouped_rows.keys())
    member_counts = {}
    if org_ids:
        member_counts = {
            row["organization_id"]: row["member_count"]
            for row in Membership.objects.filter(organization_id__in=org_ids, is_active=True)
            .values("organization_id")
            .annotate(member_count=Count("id"))
        }

    section_url = _append_query_params(reverse("accounts:profile"), section=profile_section)
    rows = []
    for row in grouped_rows.values():
        organization = row["organization"]
        if (
            row["access_origin"] == "superadmin"
            and PROFILE_ROLE_LABELS[ProfileRole.SUPERADMIN] not in row["role_labels"]
        ):
            row["role_labels"].insert(0, PROFILE_ROLE_LABELS[ProfileRole.SUPERADMIN])
        if row["is_owner"] and PROFILE_ROLE_LABELS[ProfileRole.ORG_OWNER] not in row["role_labels"]:
            row["role_labels"].insert(0, PROFILE_ROLE_LABELS[ProfileRole.ORG_OWNER])

        row["is_current"] = active_organization is not None and organization.id == active_organization.id
        row["member_count"] = member_counts.get(organization.id, 0)
        row["status_label"] = (
            "Aktiv"
            if organization.is_active and organization.status == "active"
            else ("Dayandırılıb" if organization.is_suspended else "Qeyri-aktiv")
        )
        row["switch_url"] = _append_query_params(
            reverse("organizations:switch", kwargs={"slug": organization.slug}),
            next=section_url,
        )
        row["dashboard_url"] = reverse("organizations:dashboard", kwargs={"slug": organization.slug})
        row["members_url"] = reverse("organizations:members", kwargs={"slug": organization.slug})
        row["roles_url"] = reverse("organizations:roles", kwargs={"slug": organization.slug})
        row["settings_url"] = reverse("organizations:settings", kwargs={"slug": organization.slug})
        rows.append(row)

    rows.sort(
        key=lambda item: (
            not item["is_current"],
            item["organization"].name.lower(),
        )
    )
    return rows


def _build_student_org_management_section(*, request, organization, is_superadmin, user_level, default_view=None):
    from apps.organizations.models import Membership
    from apps.organizations.models import Organization as OrganizationModel

    from ..models import UserProfile

    student_search = request.GET.get("student_org_search", "")
    pending_search = request.GET.get("student_org_pending_search", "")
    unassigned_search = request.GET.get("student_org_unassigned_search", "")
    sent_invite_search = request.GET.get("student_org_sent_invite_search", "")
    teacher_staff_search = request.GET.get("student_org_ts_search", "")
    organization_search = request.GET.get("organization_search", "")
    organization_status_filter = (request.GET.get("organization_status", "") or "").strip().lower()
    organization_type_filter = (request.GET.get("organization_type", "") or "").strip().lower()
    superadmin_user_ids = list(
        User.objects.filter(Q(is_superuser=True) | Q(profile__role=ProfileRole.SUPERADMIN)).values_list("id", flat=True)
    )

    allowed_management_views = {"students", "teachers", "staff"}
    if is_superadmin:
        allowed_management_views.add("organizations")

    fallback_management_view = default_view or (
        "organizations" if is_superadmin and organization is None else "students"
    )
    management_view = (request.GET.get("management_view") or fallback_management_view).strip().lower()
    if management_view not in allowed_management_views:
        management_view = (
            fallback_management_view if fallback_management_view in allowed_management_views else "students"
        )

    student_tab = (request.GET.get("student_tab") or "members").strip().lower()
    if student_tab not in {"members", "pending", "unassigned", "invites"}:
        student_tab = "members"

    teacher_tab = (request.GET.get("teacher_tab") or "members").strip().lower()
    if teacher_tab not in {"members", "requests", "unassigned", "invites"}:
        teacher_tab = "members"

    staff_tab = (request.GET.get("staff_tab") or "members").strip().lower()
    if staff_tab not in {"members", "requests", "unassigned", "invites"}:
        staff_tab = "members"

    section = {
        "organization": organization,
        "is_superadmin": is_superadmin,
        "active_management_view": management_view,
        "active_student_tab": student_tab,
        "active_teacher_tab": teacher_tab,
        "active_staff_tab": staff_tab,
        "management_view_options": [],
        "student_tab_options": [],
        "teacher_tab_options": [],
        "staff_tab_options": [],
        "students": [],
        "pending_requested_students": [],
        "unassigned_students": [],
        "sent_student_invites": [],
        "teacher_members": [],
        "staff_members": [],
        "unassigned_teachers": [],
        "sent_teacher_invites": [],
        "unassigned_staff": [],
        "sent_staff_invites": [],
        "pending_teacher_requests": [],
        "pending_staff_requests": [],
        "pending_teacher_staff_requests": [],
        "organization_records": [],
        "student_search_query": student_search,
        "pending_search_query": pending_search,
        "unassigned_search_query": unassigned_search,
        "sent_invite_search_query": sent_invite_search,
        "teacher_staff_search_query": teacher_staff_search,
        "organization_search_query": organization_search,
        "organization_status_filter": organization_status_filter,
        "organization_type_filter": organization_type_filter,
        "post_next_url": "",
        "access_denied_message": "",
        "can_manage_students": False,
        "pending_org_count": 0,
        "students_page_param": "student_org_members_page",
        "students_pagination_query": "",
        "pending_page_param": "student_org_pending_page",
        "pending_pagination_query": "",
        "unassigned_page_param": "student_org_unassigned_page",
        "unassigned_pagination_query": "",
        "sent_invites_page_param": "student_org_sent_invites_page",
        "sent_invites_pagination_query": "",
        "teacher_staff_page_param": "student_org_ts_page",
        "teacher_staff_pagination_query": "",
        "teacher_members_page_param": "teacher_members_page",
        "teacher_members_pagination_query": "",
        "staff_members_page_param": "staff_members_page",
        "staff_members_pagination_query": "",
        "teacher_requests_page_param": "teacher_requests_page",
        "teacher_requests_pagination_query": "",
        "teacher_unassigned_page_param": "teacher_unassigned_page",
        "teacher_unassigned_pagination_query": "",
        "teacher_invites_page_param": "teacher_invites_page",
        "teacher_invites_pagination_query": "",
        "staff_requests_page_param": "staff_requests_page",
        "staff_requests_pagination_query": "",
        "staff_unassigned_page_param": "staff_unassigned_page",
        "staff_unassigned_pagination_query": "",
        "staff_invites_page_param": "staff_invites_page",
        "staff_invites_pagination_query": "",
        "organizations_page_param": "organization_page",
        "organizations_pagination_query": "",
    }

    if organization is None:
        if is_superadmin and management_view == "organizations":
            organization_records = OrganizationModel.objects.select_related("owner").annotate(
                active_member_count=Count("memberships", filter=Q(memberships__is_active=True))
            )
            if organization_search:
                organization_records = organization_records.filter(
                    Q(name__icontains=organization_search)
                    | Q(slug__icontains=organization_search)
                    | Q(organization_identifier__icontains=organization_search)
                    | Q(license_identifier__icontains=organization_search)
                    | Q(owner__username__icontains=organization_search)
                    | Q(owner__email__icontains=organization_search)
                )
            if organization_type_filter:
                organization_records = organization_records.filter(org_type=organization_type_filter)
            if organization_status_filter == "active":
                organization_records = organization_records.filter(is_active=True, status="active")
            elif organization_status_filter == "pending":
                organization_records = organization_records.filter(status="pending")
            elif organization_status_filter == "suspended":
                organization_records = organization_records.filter(status="suspended")
            elif organization_status_filter == "inactive":
                organization_records = organization_records.filter(is_active=False)

            section["organization_records"] = Paginator(
                organization_records.order_by("name"),
                12,
            ).get_page(request.GET.get(section["organizations_page_param"]))
            section["pending_org_count"] = OrganizationModel.objects.filter(status="pending").count()
            section["management_view_options"] = [
                {"value": "students", "label": "Tələbələr", "count": 0},
                {"value": "teachers", "label": "Müəllimlər", "count": 0},
                {"value": "staff", "label": "Staff", "count": 0},
                {
                    "value": "organizations",
                    "label": "Təşkilatlar",
                    "count": section["organization_records"].paginator.count,
                },
            ]
            section["post_next_url"] = _append_query_params(
                reverse("accounts:student_organization_management"),
                management_view="organizations",
                organization_search=organization_search,
                organization_status=organization_status_filter,
                organization_type=organization_type_filter,
            )
            return section

        section["access_denied_message"] = "Aktiv təşkilat tapılmadı."
        return section

    if not is_superadmin and user_level < STUDENT_ORG_MANAGEMENT_MIN_LEVEL:
        section["access_denied_message"] = (
            "Bu bölmə üçün minimum HR, təşkilat admini və ya daha yüksək səviyyə tələb olunur."
        )
        return section

    sent_pending_invites = list(
        Membership.objects.filter(
            organization=organization,
            is_active=False,
            title=STUDENT_PENDING_INVITE_TITLE,
            user__is_active=True,
        )
        .exclude(user_id__in=superadmin_user_ids)
        .select_related("user", "assigned_by", "role", "user__profile")
        .order_by("-updated_at", "user__username")
    )
    pending_invite_user_ids = {invite.user_id for invite in sent_pending_invites}
    sent_student_invites = []
    sent_teacher_invites = []
    sent_staff_invites = []
    for invite_membership in sent_pending_invites:
        mapped_role = _map_org_role_to_profile_role(invite_membership.role)
        invite_membership.management_role_key = mapped_role
        invite_membership.management_role_label = getattr(
            invite_membership.role, "display_name", ""
        ) or PROFILE_ROLE_LABELS.get(mapped_role, getattr(invite_membership.role, "name", "Üzv"))
        invite_membership.management_position = (
            getattr(getattr(invite_membership.user, "profile", None), "staff_position", "") or ""
        ).strip()
        if mapped_role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}:
            sent_student_invites.append(invite_membership)
        elif mapped_role in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}:
            sent_teacher_invites.append(invite_membership)
        else:
            sent_staff_invites.append(invite_membership)

    if sent_invite_search:
        search_lower = sent_invite_search.lower()

        def _match_invite(invite_membership):
            return any(
                search_lower in (value or "").lower()
                for value in [
                    invite_membership.user.username,
                    invite_membership.user.email,
                    invite_membership.user.first_name,
                    invite_membership.user.last_name,
                    invite_membership.management_role_label,
                    invite_membership.management_position,
                ]
            )

        sent_student_invites = [invite for invite in sent_student_invites if _match_invite(invite)]
        sent_teacher_invites = [invite for invite in sent_teacher_invites if _match_invite(invite)]
        sent_staff_invites = [invite for invite in sent_staff_invites if _match_invite(invite)]

    legacy_requested_profiles = (
        UserProfile.objects.filter(
            user__is_active=True,
            organization__isnull=True,
            role__in=[
                ProfileRole.STUDENT,
                ProfileRole.LEAD_STUDENT,
                ProfileRole.TEACHER,
                ProfileRole.ASSISTANT_TEACHER,
                ProfileRole.MEMBER,
                ProfileRole.HR,
            ],
        )
        .exclude(user__id__in=superadmin_user_ids)
        .filter(
            Q(requested_organization=organization)
            | Q(
                requested_organization__isnull=True,
                requested_organization_name__iexact=organization.name,
            )
        )
        .exclude(user_id__in=pending_invite_user_ids)
    )
    legacy_user_ids = set(legacy_requested_profiles.values_list("user_id", flat=True))
    if legacy_user_ids:
        existing_pending_request_keys = set(
            _pending_student_request_queryset(
                organization=organization,
                statuses=[StudentOrganizationRequestStatus.PENDING],
            )
            .filter(user_id__in=legacy_user_ids)
            .values_list("user_id", "role_type")
        )
        missing_pending_requests = []
        for legacy_profile in legacy_requested_profiles.select_related("user"):
            legacy_role_type = _membership_request_role_type_for_profile_role(legacy_profile.role)
            if (legacy_profile.user_id, legacy_role_type) in existing_pending_request_keys:
                continue
            missing_pending_requests.append(
                StudentOrganizationRequest(
                    user=legacy_profile.user,
                    organization=organization,
                    role_type=legacy_role_type,
                    message=(legacy_profile.requested_organization_message or "").strip(),
                    status=StudentOrganizationRequestStatus.PENDING,
                )
            )
        if missing_pending_requests:
            StudentOrganizationRequest.objects.bulk_create(missing_pending_requests)

    students = (
        UserProfile.objects.filter(user__is_active=True, organization=organization)
        .exclude(user__id__in=superadmin_user_ids)
        .filter(
            Q(role__in=[ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT])
            | Q(
                user__memberships__organization=organization,
                user__memberships__is_active=True,
                user__memberships__role__name="student",
            )
        )
        .select_related("user")
        .distinct()
        .order_by("user__username")
    )
    if student_search:
        students = students.filter(
            Q(user__username__icontains=student_search)
            | Q(user__email__icontains=student_search)
            | Q(user__first_name__icontains=student_search)
            | Q(user__last_name__icontains=student_search)
        )

    pending_requested_students = (
        _pending_student_request_queryset(
            organization=organization,
            statuses=[
                StudentOrganizationRequestStatus.PENDING,
                StudentOrganizationRequestStatus.AUTO_CLOSED,
            ],
        )
        .filter(role_type=MembershipRequestRoleType.STUDENT)
        .filter(user__is_active=True)
        .exclude(user_id__in=superadmin_user_ids)
        .exclude(user_id__in=pending_invite_user_ids)
        .select_related("user", "organization", "user__profile", "user__profile__organization")
        .order_by("-created_at", "user__username")
    )
    if pending_search:
        pending_requested_students = pending_requested_students.filter(
            Q(user__username__icontains=pending_search)
            | Q(user__email__icontains=pending_search)
            | Q(user__first_name__icontains=pending_search)
            | Q(user__last_name__icontains=pending_search)
            | Q(message__icontains=pending_search)
            | Q(resolution_note__icontains=pending_search)
        )

    pending_request_user_ids_any = _pending_student_request_queryset(
        statuses=[StudentOrganizationRequestStatus.PENDING]
    ).values_list("user_id", flat=True)

    unassigned_students = (
        UserProfile.objects.filter(
            user__is_active=True,
            organization__isnull=True,
            role__in=[ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT],
        )
        .exclude(user__id__in=superadmin_user_ids)
        .exclude(user_id__in=pending_request_user_ids_any)
        .exclude(user_id__in=pending_invite_user_ids)
        .exclude(
            user__memberships__organization=organization,
            user__memberships__is_active=True,
        )
        .filter(
            requested_organization__isnull=True,
            requested_organization_name__exact="",
        )
        .select_related("user", "requested_organization")
        .distinct()
        .order_by("user__username")
    )
    if unassigned_search:
        unassigned_students = unassigned_students.filter(
            Q(user__username__icontains=unassigned_search)
            | Q(user__email__icontains=unassigned_search)
            | Q(user__first_name__icontains=unassigned_search)
            | Q(user__last_name__icontains=unassigned_search)
        )

    unassigned_teachers = (
        UserProfile.objects.filter(
            user__is_active=True,
            organization__isnull=True,
            role__in=[ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER],
        )
        .exclude(user__id__in=superadmin_user_ids)
        .exclude(user_id__in=pending_request_user_ids_any)
        .exclude(user_id__in=pending_invite_user_ids)
        .exclude(
            user__memberships__organization=organization,
            user__memberships__is_active=True,
        )
        .filter(
            requested_organization__isnull=True,
            requested_organization_name__exact="",
        )
        .select_related("user", "requested_organization")
        .distinct()
        .order_by("user__username")
    )
    if teacher_staff_search:
        unassigned_teachers = unassigned_teachers.filter(
            Q(user__username__icontains=teacher_staff_search)
            | Q(user__email__icontains=teacher_staff_search)
            | Q(user__first_name__icontains=teacher_staff_search)
            | Q(user__last_name__icontains=teacher_staff_search)
            | Q(department__icontains=teacher_staff_search)
        )

    unassigned_staff = (
        UserProfile.objects.filter(
            user__is_active=True,
            organization__isnull=True,
            role__in=[ProfileRole.MEMBER, ProfileRole.HR],
        )
        .exclude(user__id__in=superadmin_user_ids)
        .exclude(user_id__in=pending_request_user_ids_any)
        .exclude(user_id__in=pending_invite_user_ids)
        .exclude(
            user__memberships__organization=organization,
            user__memberships__is_active=True,
        )
        .filter(
            requested_organization__isnull=True,
            requested_organization_name__exact="",
        )
        .select_related("user", "requested_organization")
        .distinct()
        .order_by("user__username")
    )
    if teacher_staff_search:
        unassigned_staff = unassigned_staff.filter(
            Q(user__username__icontains=teacher_staff_search)
            | Q(user__email__icontains=teacher_staff_search)
            | Q(user__first_name__icontains=teacher_staff_search)
            | Q(user__last_name__icontains=teacher_staff_search)
            | Q(department__icontains=teacher_staff_search)
            | Q(staff_position__icontains=teacher_staff_search)
        )

    students_page = request.GET.get(section["students_page_param"])
    pending_page = request.GET.get(section["pending_page_param"])
    unassigned_page = request.GET.get(section["unassigned_page_param"])
    sent_invites_page = request.GET.get(section["sent_invites_page_param"])
    teacher_unassigned_page = request.GET.get(section["teacher_unassigned_page_param"])
    teacher_invites_page = request.GET.get(section["teacher_invites_page_param"])
    staff_unassigned_page = request.GET.get(section["staff_unassigned_page_param"])
    staff_invites_page = request.GET.get(section["staff_invites_page_param"])
    teacher_staff_page = request.GET.get(section["teacher_staff_page_param"])
    section["students"] = Paginator(students, 12).get_page(students_page)
    section["pending_requested_students"] = Paginator(pending_requested_students, 12).get_page(pending_page)
    section["unassigned_students"] = Paginator(unassigned_students, 12).get_page(unassigned_page)
    section["sent_student_invites"] = Paginator(sent_student_invites, 12).get_page(sent_invites_page)
    section["unassigned_teachers"] = Paginator(unassigned_teachers, 12).get_page(teacher_unassigned_page)
    section["sent_teacher_invites"] = Paginator(sent_teacher_invites, 12).get_page(teacher_invites_page)
    section["unassigned_staff"] = Paginator(unassigned_staff, 12).get_page(staff_unassigned_page)
    section["sent_staff_invites"] = Paginator(sent_staff_invites, 12).get_page(staff_invites_page)

    teacher_staff_pending_qs = (
        StudentOrganizationRequest.objects.filter(
            organization=organization,
            status=StudentOrganizationRequestStatus.PENDING,
            role_type__in=[MembershipRequestRoleType.TEACHER, MembershipRequestRoleType.STAFF],
            user__is_active=True,
        )
        .exclude(user_id__in=superadmin_user_ids)
        .exclude(user_id__in=pending_invite_user_ids)
        .select_related("user", "user__profile")
        .order_by("-created_at", "user__username")
    )
    if teacher_staff_search:
        teacher_staff_pending_qs = teacher_staff_pending_qs.filter(
            Q(user__username__icontains=teacher_staff_search)
            | Q(user__email__icontains=teacher_staff_search)
            | Q(user__first_name__icontains=teacher_staff_search)
            | Q(user__last_name__icontains=teacher_staff_search)
            | Q(message__icontains=teacher_staff_search)
        )
    section["pending_teacher_staff_requests"] = Paginator(teacher_staff_pending_qs, 12).get_page(teacher_staff_page)

    teacher_requests_qs = teacher_staff_pending_qs.filter(role_type=MembershipRequestRoleType.TEACHER)
    staff_requests_qs = teacher_staff_pending_qs.filter(role_type=MembershipRequestRoleType.STAFF)
    section["pending_teacher_requests"] = Paginator(
        teacher_requests_qs,
        12,
    ).get_page(request.GET.get(section["teacher_requests_page_param"]))
    section["pending_staff_requests"] = Paginator(
        staff_requests_qs,
        12,
    ).get_page(request.GET.get(section["staff_requests_page_param"]))

    active_member_qs = (
        Membership.objects.filter(
            organization=organization,
            is_active=True,
            user__is_active=True,
        )
        .exclude(user_id__in=superadmin_user_ids)
        .select_related("user", "role", "user__profile")
        .order_by("user_id", "-is_primary", "-role__level", "role__display_name")
    )
    if teacher_staff_search:
        active_member_qs = active_member_qs.filter(
            Q(user__username__icontains=teacher_staff_search)
            | Q(user__email__icontains=teacher_staff_search)
            | Q(user__first_name__icontains=teacher_staff_search)
            | Q(user__last_name__icontains=teacher_staff_search)
            | Q(role__display_name__icontains=teacher_staff_search)
            | Q(role__name__icontains=teacher_staff_search)
        )

    teacher_members = []
    staff_members = []
    seen_member_user_ids = set()
    removable_member_roles = {
        ProfileRole.STUDENT,
        ProfileRole.LEAD_STUDENT,
        ProfileRole.TEACHER,
        ProfileRole.ASSISTANT_TEACHER,
        ProfileRole.MEMBER,
        ProfileRole.HR,
    }
    for membership in active_member_qs:
        if membership.user_id in seen_member_user_ids:
            continue
        seen_member_user_ids.add(membership.user_id)
        mapped_role = _map_org_role_to_profile_role(membership.role)
        membership.management_role_key = mapped_role
        membership.management_role_label = getattr(membership.role, "display_name", "") or PROFILE_ROLE_LABELS.get(
            mapped_role, membership.role.name
        )
        membership.management_position = (getattr(membership.user.profile, "staff_position", "") or "").strip()
        membership.management_can_remove = mapped_role in removable_member_roles and membership.user_id != getattr(
            organization, "owner_id", None
        )

        if mapped_role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}:
            continue
        if mapped_role in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}:
            teacher_members.append(membership)
            continue
        staff_members.append(membership)

    section["teacher_members"] = Paginator(
        teacher_members,
        12,
    ).get_page(request.GET.get(section["teacher_members_page_param"]))
    section["staff_members"] = Paginator(
        staff_members,
        12,
    ).get_page(request.GET.get(section["staff_members_page_param"]))

    for pending_request in section["pending_requested_students"].object_list:
        pending_request.request_display_status = (
            "Gözləyir" if pending_request.status == StudentOrganizationRequestStatus.PENDING else "Bağlanıb"
        )
        pending_request.request_display_class = (
            "warning" if pending_request.status == StudentOrganizationRequestStatus.PENDING else "secondary"
        )

        profile = getattr(pending_request.user, "profile", None)
        if (
            profile
            and profile.organization == organization
            and pending_request.status == StudentOrganizationRequestStatus.PENDING
        ):
            pending_request.request_note = "İstifadəçi artıq bu təşkilatın üzvüdür."
            pending_request.request_is_actionable = False
            continue

        active_other_org_name = ""
        if profile and profile.organization and profile.organization != organization:
            active_other_org_name = profile.organization.name

        if not active_other_org_name and pending_request.status == StudentOrganizationRequestStatus.PENDING:
            active_other_membership = (
                Membership.objects.filter(user=pending_request.user, is_active=True)
                .exclude(organization=organization)
                .select_related("organization", "role")
                .order_by("-is_primary", "-role__level")
                .first()
            )
            if active_other_membership:
                active_other_org_name = active_other_membership.organization.name

        if active_other_org_name and pending_request.status == StudentOrganizationRequestStatus.PENDING:
            pending_request.request_note = f"İstifadəçi artıq {active_other_org_name} təşkilatının üzvüdür."
            pending_request.request_is_actionable = False
        elif pending_request.status == StudentOrganizationRequestStatus.AUTO_CLOSED:
            pending_request.request_note = (
                pending_request.resolution_note or ""
            ).strip() or "Bu müraciət avtomatik bağlanıb."
            pending_request.request_is_actionable = False
        else:
            pending_request.request_note = (pending_request.resolution_note or "").strip()
            pending_request.request_is_actionable = True

    organization_records = OrganizationModel.objects.none()
    if is_superadmin:
        organization_records = (
            OrganizationModel.objects.select_related("owner")
            .annotate(active_member_count=Count("memberships", filter=Q(memberships__is_active=True)))
            .order_by("name")
        )
        if organization_search:
            organization_records = organization_records.filter(
                Q(name__icontains=organization_search)
                | Q(slug__icontains=organization_search)
                | Q(organization_identifier__icontains=organization_search)
                | Q(license_identifier__icontains=organization_search)
                | Q(owner__username__icontains=organization_search)
                | Q(owner__email__icontains=organization_search)
            )
        if organization_type_filter:
            organization_records = organization_records.filter(org_type=organization_type_filter)
        if organization_status_filter == "active":
            organization_records = organization_records.filter(is_active=True, status="active")
        elif organization_status_filter == "pending":
            organization_records = organization_records.filter(status="pending")
        elif organization_status_filter == "suspended":
            organization_records = organization_records.filter(status="suspended")
        elif organization_status_filter == "inactive":
            organization_records = organization_records.filter(is_active=False)

        section["organization_records"] = Paginator(
            organization_records,
            12,
        ).get_page(request.GET.get(section["organizations_page_param"]))
        section["pending_org_count"] = OrganizationModel.objects.filter(status="pending").count()

    base_query_kwargs = {
        "section": "student-organization-management",
        "management_view": management_view,
        "student_tab": student_tab,
        "teacher_tab": teacher_tab,
        "staff_tab": staff_tab,
        "student_org_search": student_search,
        "student_org_pending_search": pending_search,
        "student_org_unassigned_search": unassigned_search,
        "student_org_sent_invite_search": sent_invite_search,
        "student_org_ts_search": teacher_staff_search,
        "organization_search": organization_search,
        "organization_status": organization_status_filter,
        "organization_type": organization_type_filter,
    }
    section["students_pagination_query"] = _query_string(**base_query_kwargs)
    section["pending_pagination_query"] = _query_string(**base_query_kwargs)
    section["unassigned_pagination_query"] = _query_string(**base_query_kwargs)
    section["sent_invites_pagination_query"] = _query_string(**base_query_kwargs)
    section["teacher_staff_pagination_query"] = _query_string(**base_query_kwargs)
    section["teacher_members_pagination_query"] = _query_string(**base_query_kwargs)
    section["staff_members_pagination_query"] = _query_string(**base_query_kwargs)
    section["teacher_requests_pagination_query"] = _query_string(**base_query_kwargs)
    section["teacher_unassigned_pagination_query"] = _query_string(**base_query_kwargs)
    section["teacher_invites_pagination_query"] = _query_string(**base_query_kwargs)
    section["staff_requests_pagination_query"] = _query_string(**base_query_kwargs)
    section["staff_unassigned_pagination_query"] = _query_string(**base_query_kwargs)
    section["staff_invites_pagination_query"] = _query_string(**base_query_kwargs)
    section["organizations_pagination_query"] = _query_string(**base_query_kwargs)
    section["post_next_url"] = _append_query_params(
        reverse("accounts:student_organization_management"),
        **{key: value for key, value in base_query_kwargs.items() if key != "section"},
    )

    section["student_tab_options"] = [
        {
            "value": "members",
            "label": "Tələbələr",
            "count": section["students"].paginator.count,
        },
        {
            "value": "pending",
            "label": "Müraciətlər",
            "count": section["pending_requested_students"].paginator.count,
        },
        {
            "value": "unassigned",
            "label": "Dəvətsizlər",
            "count": section["unassigned_students"].paginator.count,
        },
        {
            "value": "invites",
            "label": "Dəvətlər",
            "count": section["sent_student_invites"].paginator.count,
        },
    ]
    section["teacher_tab_options"] = [
        {
            "value": "members",
            "label": "Müəllimlər",
            "count": section["teacher_members"].paginator.count,
        },
        {
            "value": "requests",
            "label": "Müraciətlər",
            "count": section["pending_teacher_requests"].paginator.count,
        },
        {
            "value": "unassigned",
            "label": "Dəvətsizlər",
            "count": section["unassigned_teachers"].paginator.count,
        },
        {
            "value": "invites",
            "label": "Dəvətlər",
            "count": section["sent_teacher_invites"].paginator.count,
        },
    ]
    section["staff_tab_options"] = [
        {
            "value": "members",
            "label": "Staff",
            "count": section["staff_members"].paginator.count,
        },
        {
            "value": "requests",
            "label": "Müraciətlər",
            "count": section["pending_staff_requests"].paginator.count,
        },
        {
            "value": "unassigned",
            "label": "Dəvətsizlər",
            "count": section["unassigned_staff"].paginator.count,
        },
        {
            "value": "invites",
            "label": "Dəvətlər",
            "count": section["sent_staff_invites"].paginator.count,
        },
    ]
    section["management_view_options"] = [
        {
            "value": "students",
            "label": "Tələbələr",
            "count": section["students"].paginator.count,
        },
        {
            "value": "teachers",
            "label": "Müəllimlər",
            "count": (
                section["teacher_members"].paginator.count
                + section["pending_teacher_requests"].paginator.count
                + section["unassigned_teachers"].paginator.count
                + section["sent_teacher_invites"].paginator.count
            ),
        },
        {
            "value": "staff",
            "label": "Staff",
            "count": (
                section["staff_members"].paginator.count
                + section["pending_staff_requests"].paginator.count
                + section["unassigned_staff"].paginator.count
                + section["sent_staff_invites"].paginator.count
            ),
        },
    ]
    if is_superadmin:
        section["management_view_options"].append(
            {
                "value": "organizations",
                "label": "Təşkilatlar",
                "count": section["organization_records"].paginator.count,
            }
        )

    section["can_manage_students"] = True
    return section


def _build_student_org_request_section(*, request, profile):
    from apps.organizations.models import Membership, Organization

    search_query = request.GET.get("student_org_request_search", "")
    org_type_filter = (request.GET.get("student_org_request_type", "") or "").strip().lower()
    request_role_type = _membership_request_role_type_for_profile_role(getattr(profile, "role", ProfileRole.MEMBER))
    request_role_label = _membership_request_role_label(request_role_type)
    request_role_label_lower = str(request_role_label).lower()
    allowed_types = {
        OrganizationType.SCHOOL,
        OrganizationType.UNIVERSITY,
        OrganizationType.COURSE_CENTER,
    }
    if org_type_filter not in allowed_types:
        org_type_filter = ""

    pending_invites = list(
        Membership.objects.filter(
            user=request.user,
            is_active=False,
            title=STUDENT_PENDING_INVITE_TITLE,
            organization__is_active=True,
            organization__status="active",
        )
        .select_related("organization", "role")
        .order_by("organization__name")
    )
    for pending_invite in pending_invites:
        invite_profile_role = _map_org_role_to_profile_role(getattr(pending_invite, "role", None))
        invite_role_type = _membership_request_role_type_for_profile_role(invite_profile_role)
        pending_invite.role_label = _membership_request_role_label(invite_role_type)
        pending_invite.role_label_lower = str(pending_invite.role_label).lower()

    legacy_requested_org = getattr(profile, "requested_organization", None)
    has_matching_pending_request = False
    if legacy_requested_org is not None:
        with bypass_rls():
            has_matching_pending_request = StudentOrganizationRequest.objects.filter(
                user=request.user,
                organization=legacy_requested_org,
                status=StudentOrganizationRequestStatus.PENDING,
                role_type=request_role_type,
            ).exists()
    if (
        profile.organization is None
        and legacy_requested_org is not None
        and legacy_requested_org.is_active
        and not legacy_requested_org.is_suspended
        and profile.role
        in {
            ProfileRole.STUDENT,
            ProfileRole.LEAD_STUDENT,
            ProfileRole.TEACHER,
            ProfileRole.ASSISTANT_TEACHER,
            ProfileRole.MEMBER,
            ProfileRole.HR,
        }
        and not has_matching_pending_request
    ):
        with bypass_rls():
            StudentOrganizationRequest.objects.create(
                user=request.user,
                organization=legacy_requested_org,
                role_type=request_role_type,
                message=(profile.requested_organization_message or "").strip(),
                status=StudentOrganizationRequestStatus.PENDING,
            )

    with bypass_rls():
        pending_student_requests = list(
            StudentOrganizationRequest.objects.filter(
                user=request.user,
                status=StudentOrganizationRequestStatus.PENDING,
                role_type=request_role_type,
                organization__is_active=True,
                organization__status="active",
            )
            .select_related("organization")
            .order_by("-created_at")
        )

    for pending_request in pending_student_requests:
        pending_request.role_label = request_role_label
        pending_request.role_label_lower = request_role_label_lower

    pending_requested_org = pending_student_requests[0].organization if pending_student_requests else None
    pending_requested_org_name = pending_requested_org.name if pending_requested_org else ""
    pending_request_message = (pending_student_requests[0].message or "").strip() if pending_student_requests else ""
    selected_org_id = (
        str(pending_requested_org.id) if pending_requested_org else str(profile.requested_organization_id or "")
    )
    pending_request_org_ids = {item.organization_id for item in pending_student_requests}

    organizations = Organization.objects.filter(is_active=True, status="active").exclude(
        org_type=OrganizationType.INDIVIDUAL
    )
    if org_type_filter:
        organizations = organizations.filter(org_type=org_type_filter)
    if search_query:
        organizations = organizations.filter(
            Q(name__icontains=search_query)
            | Q(country__icontains=search_query)
            | Q(slug__icontains=search_query)
            | Q(organization_identifier__icontains=search_query)
            | Q(license_identifier__icontains=search_query)
        )
    organizations = organizations.order_by("name")

    page_param = "student_org_request_page"
    page_number = request.GET.get(page_param)
    organizations_page = Paginator(organizations, 12).get_page(page_number)

    return {
        "organizations": organizations_page,
        "search_query": search_query,
        "org_type_filter": org_type_filter,
        "pending_invites": pending_invites,
        "pending_invites_count": len(pending_invites),
        "has_pending_invites": bool(pending_invites),
        "pending_student_requests": pending_student_requests,
        "pending_student_requests_count": len(pending_student_requests),
        "has_pending_student_requests": bool(pending_student_requests),
        "pending_request_org_ids": pending_request_org_ids,
        "current_organization": profile.organization,
        "pending_requested_organization": pending_requested_org,
        "pending_requested_org_name": pending_requested_org_name,
        "pending_request_message": pending_request_message,
        "selected_org_id": selected_org_id,
        "page_param": page_param,
        "pagination_query": _query_string(
            section="student-organization-request",
            student_org_request_search=search_query,
            student_org_request_type=org_type_filter,
        ),
        "post_next_url": _append_query_params(
            reverse("accounts:student_organization_request"),
            student_org_request_search=search_query,
            student_org_request_type=org_type_filter,
        ),
        "request_message_max_length": STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH,
        "request_role_type": request_role_type,
        "request_role_label": request_role_label,
        "request_role_label_lower": request_role_label_lower,
    }


def _normalize_assigned_tasks_filter(value):
    normalized = (value or "all").lower()
    if normalized in ASSIGNED_TASK_FILTER_CHOICES:
        return normalized
    return "all"


def _csv_to_int_set(raw_value):
    values = set()
    for chunk in (raw_value or "").split(","):
        token = chunk.strip()
        if token.isdigit():
            values.add(int(token))
    return values


def _csv_to_lower_token_set(raw_value):
    return {chunk.strip().lower() for chunk in (raw_value or "").split(",") if chunk.strip()}


def _task_state_badge_data(state):
    normalized_state = (state or "open").lower()
    if normalized_state == "upcoming":
        return "Gözləyir", "upcoming"
    if normalized_state == "closed":
        return "Bağlı", "closed"
    return "Aktiv", "open"


def _standard_item_type_meta(raw_type):
    normalized = (raw_type or "").strip().lower()
    if normalized == "exam":
        return {"type": "exam", "label": "İmtahan", "icon": "exam"}
    if normalized == "assignment":
        return {"type": "assignment", "label": "Sərbəst iş", "icon": "assignment"}
    if normalized == "lab":
        return {"type": "lab", "label": "Lab işi", "icon": "lab"}
    if normalized == "project":
        return {"type": "project", "label": "Kurs işi", "icon": "project"}
    if normalized == "course":
        return {"type": "course", "label": "Kurs", "icon": "course"}
    return {"type": "unknown", "label": "Tapşırıq", "icon": "task"}


def _normalize_pending_review_type(value):
    normalized = (value or "all").lower()
    if normalized in PENDING_REVIEW_TYPE_CHOICES:
        return normalized
    return "all"


def _normalize_pending_review_status(value):
    normalized = (value or "all").lower()
    if normalized in PENDING_REVIEW_STATUS_CHOICES:
        return normalized
    return "all"
