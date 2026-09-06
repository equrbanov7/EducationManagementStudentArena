"""
Shared helper functions for account views.

This package was split out of a single 1,800-line ``_helpers.py`` module.
Functions are grouped by concern (rbac, tenant, membership, review window,
formatting, redirects, etc.). This ``__init__`` re-exports every public name
so existing ``from ._helpers import ...`` imports keep working unchanged.
"""

from .attachments import _extract_assignment_attachments
from .constants import (
    MAX_PROFILE_AVATAR_SIZE_BYTES,
    PENDING_ANSWER_FILTER_CHOICES,
    PENDING_REVIEW_STATUS_CHOICES,
    PENDING_REVIEW_TYPE_CHOICES,
    PROFILE_AVATAR_ALLOWED_EXTENSIONS,
    PROFILE_ROLE_LABELS,
    PROFILE_ROLE_NAMES,
    PROFILE_ROLE_NAMES_MANAGEABLE,
    RESULT_FILTER_CHOICES,
    REVIEW_EDIT_WINDOW,
    REVIEW_EDIT_WINDOW_MINUTES,
    ROLE_ASSIGNMENT_OPERATION_TOKEN_MAX_AGE_SECONDS,
    ROLE_ASSIGNMENT_OPERATION_TOKEN_SALT,
    STUDENT_MEMBER_GROUPS_DISPLAY_LIMIT,
    STUDENT_ORG_MANAGEMENT_MIN_LEVEL,
    STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH,
    STUDENT_PENDING_INVITE_TITLE,
    signer,
)
from .formatting import (
    _append_query_params,
    _csv_to_int_set,
    _csv_to_lower_token_set,
    _normalize_assigned_tasks_filter,
    _normalize_pending_answers_filter,
    _normalize_pending_review_status,
    _normalize_pending_review_type,
    _normalize_results_filter,
    _normalized_org_name,
    _parse_decimal_score,
    _query_string,
    _result_status_badge,
    _standard_item_type_meta,
    _task_state_badge_data,
)
from .membership import (
    _activate_verified_student_membership,
    _close_other_pending_student_requests,
    _ensure_profile_admin_membership,
    _pending_student_request_queryset,
    _set_student_org_request_status,
    _sync_profile_pending_request_snapshot,
    _sync_user_role_memberships,
)
from .org_access import _build_user_organization_access_rows
from .org_sections import (
    _build_student_org_management_section,
    _build_student_org_request_section,
)
from .rbac import (
    _assignable_profile_roles_for_user,
    _collect_actor_permissions,
    _decorate_manage_role_profiles,
    _extract_profile_roles_for_user,
    _invalidate_actor_permissions_cache,
    _is_superadmin_user,
    _permission_is_grantable,
    _role_capabilities,
    _user_has_any_role,
)
from .redirects import _resolve_next_url, _safe_same_origin_redirect_path
from .rendering import _render_profile_section
from .review_window import (
    _is_result_visible_to_student,
    _is_review_window_closed,
    _is_review_window_open,
    _normalize_review_result_item_type,
    _pending_review_type_label,
    _review_window_seconds_left,
)
from .roles_map import (
    _get_signup_lookup_payload,
    _map_org_role_to_profile_role,
    _map_signup_role_to_profile_role,
    _membership_request_role_label,
    _membership_request_role_type_for_profile_role,
    _profile_role_for_membership_request_type,
    _resolve_membership_role,
)
from .tenant import (
    _assigned_courses_queryset,
    _assigned_exams_queryset,
    _bind_active_role_context,
    _get_active_organization,
    _resolve_superadmin_target_org,
    _tenant_scoped_courses,
    _tenant_scoped_exams,
)

__all__ = [
    # constants
    "MAX_PROFILE_AVATAR_SIZE_BYTES",
    "PENDING_ANSWER_FILTER_CHOICES",
    "PENDING_REVIEW_STATUS_CHOICES",
    "PENDING_REVIEW_TYPE_CHOICES",
    "PROFILE_AVATAR_ALLOWED_EXTENSIONS",
    "PROFILE_ROLE_LABELS",
    "PROFILE_ROLE_NAMES",
    "PROFILE_ROLE_NAMES_MANAGEABLE",
    "RESULT_FILTER_CHOICES",
    "REVIEW_EDIT_WINDOW",
    "REVIEW_EDIT_WINDOW_MINUTES",
    "ROLE_ASSIGNMENT_OPERATION_TOKEN_MAX_AGE_SECONDS",
    "ROLE_ASSIGNMENT_OPERATION_TOKEN_SALT",
    "STUDENT_MEMBER_GROUPS_DISPLAY_LIMIT",
    "STUDENT_ORG_MANAGEMENT_MIN_LEVEL",
    "STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH",
    "STUDENT_PENDING_INVITE_TITLE",
    "signer",
    # attachments
    "_extract_assignment_attachments",
    # formatting
    "_append_query_params",
    "_csv_to_int_set",
    "_csv_to_lower_token_set",
    "_normalize_assigned_tasks_filter",
    "_normalize_pending_answers_filter",
    "_normalize_pending_review_status",
    "_normalize_pending_review_type",
    "_normalize_results_filter",
    "_normalized_org_name",
    "_parse_decimal_score",
    "_query_string",
    "_result_status_badge",
    "_standard_item_type_meta",
    "_task_state_badge_data",
    # membership
    "_activate_verified_student_membership",
    "_close_other_pending_student_requests",
    "_ensure_profile_admin_membership",
    "_pending_student_request_queryset",
    "_set_student_org_request_status",
    "_sync_profile_pending_request_snapshot",
    "_sync_user_role_memberships",
    # org access / sections
    "_build_user_organization_access_rows",
    "_build_student_org_management_section",
    "_build_student_org_request_section",
    # rbac
    "_assignable_profile_roles_for_user",
    "_collect_actor_permissions",
    "_decorate_manage_role_profiles",
    "_extract_profile_roles_for_user",
    "_invalidate_actor_permissions_cache",
    "_is_superadmin_user",
    "_permission_is_grantable",
    "_role_capabilities",
    "_user_has_any_role",
    # redirects
    "_resolve_next_url",
    "_safe_same_origin_redirect_path",
    # rendering
    "_render_profile_section",
    # review window
    "_is_result_visible_to_student",
    "_is_review_window_closed",
    "_is_review_window_open",
    "_normalize_review_result_item_type",
    "_pending_review_type_label",
    "_review_window_seconds_left",
    # roles map
    "_get_signup_lookup_payload",
    "_map_org_role_to_profile_role",
    "_map_signup_role_to_profile_role",
    "_membership_request_role_label",
    "_membership_request_role_type_for_profile_role",
    "_profile_role_for_membership_request_type",
    "_resolve_membership_role",
    # tenant
    "_assigned_courses_queryset",
    "_assigned_exams_queryset",
    "_bind_active_role_context",
    "_get_active_organization",
    "_resolve_superadmin_target_org",
    "_tenant_scoped_courses",
    "_tenant_scoped_exams",
]
