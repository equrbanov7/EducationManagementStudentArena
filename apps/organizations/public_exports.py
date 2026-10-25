"""Explicit public contracts for cross-module consumers; implementation stays local."""

from .cabinet_links import register_cabinet_section_resolver  # noqa: F401
from .cabinet_modules import CABINET_MODULES  # noqa: F401
from .cabinet_modules import default_disabled_sections  # noqa: F401
from .cabinet_modules import disabled_sections  # noqa: F401
from .cabinet_modules import is_module_enabled  # noqa: F401
from .cabinet_modules import module_items  # noqa: F401
from .cabinet_modules import set_module_enabled  # noqa: F401
from .default_roles import get_default_roles_for_org_type  # noqa: F401
from .group_cohort import group_admission_year  # noqa: F401
from .group_cohort import group_cohort_year  # noqa: F401
from .group_education_form import chain_names as group_chain_names  # noqa: F401
from .group_education_form import education_form_from_group_name  # noqa: F401
from .group_education_form import group_rule_form  # noqa: F401
from .group_education_form import rule_form_for as group_rule_form_for  # noqa: F401
from .groups_registry import build_groups_registry  # noqa: F401
from .groups_registry import student_record_scope_q  # noqa: F401
from .holidays import HolidayError  # noqa: F401
from .holidays import WorkCalendar  # noqa: F401
from .holidays import delete_holiday  # noqa: F401
from .holidays import holidays_between  # noqa: F401
from .holidays import save_holiday  # noqa: F401
from .holidays import seed_fixed_holidays  # noqa: F401
from .holidays import work_calendar  # noqa: F401
from .holidays import academic_year_bounds as holiday_academic_year_bounds  # noqa: F401
from .holidays import academic_year_label as holiday_academic_year_label  # noqa: F401
from .holidays import academic_year_start as holiday_academic_year_start  # noqa: F401
from .holidays import current_academic_year_start as holiday_current_academic_year  # noqa: F401
from .kafedra_units import is_kafedra_type  # noqa: F401
from .kafedra_units import is_kafedra_unit  # noqa: F401
from .kafedra_units import kafedra_q  # noqa: F401
from .kafedra_units import kafedra_unit_types  # noqa: F401
from .kafedra_units import narrow_kafedra_rows  # noqa: F401
from .overview import build_overview_data  # noqa: F401
from .permissions import get_permission_label  # noqa: F401
from .request_memberships import drop_request_memberships  # noqa: F401
from .request_memberships import request_active_memberships  # noqa: F401
from .review_visibility import save_review_identity_reveal  # noqa: F401
from .scoping import EMPTY_SCOPE  # noqa: F401
from .scoping import ORG_WIDE_SCOPE  # noqa: F401
from .scoping import UnitScope  # noqa: F401
from .scoping import faculty_read_scope  # noqa: F401
from .scoping import get_permission_scope  # noqa: F401
from .scoping import permission_scope_unit_types  # noqa: F401
from .scoping import permission_scope_units  # noqa: F401
from .scoping import scope_memberships_by_unit  # noqa: F401
from .scoping import scope_org_units  # noqa: F401
from .scoping import unit_in_scope  # noqa: F401
from .scoping import user_scope_covers_unit  # noqa: F401
from .services import get_active_memberships  # noqa: F401
from .settings_store import REMOVE as REMOVE_SETTINGS_KEY  # noqa: F401
from .settings_store import UNCHANGED as UNCHANGED_SETTINGS_KEY  # noqa: F401
from .settings_store import register_managed_settings_key  # noqa: F401
from .settings_store import set_settings_keys  # noqa: F401
from .settings_store import update_settings_key  # noqa: F401
from .structure_views import build_structure_tree_context  # noqa: F401
from .structure_views import chair_detail_context  # noqa: F401
from .structure_views import visible_chairs  # noqa: F401
from .structure_views.constants import KAFEDRA_UNIT_TYPES  # noqa: F401
from .structure_views.constants import TEACHER_ROLE_NAMES  # noqa: F401
from .structure_views.members_base import resolve_members_access  # noqa: F401
from .structure_views.registry import unit_type_label  # noqa: F401
from .student_privacy import STUDENT_ACCOUNT_PERMISSIONS  # noqa: F401
from .student_privacy import holds_student_key  # noqa: F401
from .student_privacy import request_holds_student_key  # noqa: F401
from .student_privacy import student_only_q  # noqa: F401
from .unit_heads import ancestor_unit_ids  # noqa: F401
from .unit_heads import chair_head_memberships_for_unit  # noqa: F401
from .unit_heads import dean_memberships_for_unit  # noqa: F401
from .unit_heads import members_covering_unit  # noqa: F401
from .unit_heads import resolve_ancestor  # noqa: F401
from .unit_types import UNIT_TYPES_BY_ORG  # noqa: F401
from .unit_types import validate_unit_type_for_org  # noqa: F401
from .views import _visible_units_queryset as visible_units_queryset  # noqa: F401
from .views.shared._helpers import _can_manage_org_settings as can_manage_org_settings  # noqa: F401
from .views.shared._helpers import _can_manage_organization as can_manage_organization  # noqa: F401
from .views.shared._helpers import _has_org_permission as has_org_permission  # noqa: F401

__all__ = [
    "CABINET_MODULES",
    "EMPTY_SCOPE",
    "KAFEDRA_UNIT_TYPES",
    "ORG_WIDE_SCOPE",
    "REMOVE_SETTINGS_KEY",
    "STUDENT_ACCOUNT_PERMISSIONS",
    "TEACHER_ROLE_NAMES",
    "UNCHANGED_SETTINGS_KEY",
    "UNIT_TYPES_BY_ORG",
    "UnitScope",
    "ancestor_unit_ids",
    "HolidayError",
    "WorkCalendar",
    "build_groups_registry",
    "delete_holiday",
    "group_admission_year",
    "group_cohort_year",
    "group_chain_names",
    "education_form_from_group_name",
    "group_rule_form",
    "group_rule_form_for",
    "holiday_academic_year_bounds",
    "holiday_academic_year_label",
    "holiday_academic_year_start",
    "holiday_current_academic_year",
    "holidays_between",
    "save_holiday",
    "seed_fixed_holidays",
    "work_calendar",
    "build_overview_data",
    "build_structure_tree_context",
    "can_manage_org_settings",
    "can_manage_organization",
    "chair_detail_context",
    "chair_head_memberships_for_unit",
    "dean_memberships_for_unit",
    "default_disabled_sections",
    "disabled_sections",
    "drop_request_memberships",
    "faculty_read_scope",
    "get_active_memberships",
    "get_default_roles_for_org_type",
    "get_permission_label",
    "get_permission_scope",
    "has_org_permission",
    "holds_student_key",
    "is_kafedra_type",
    "is_kafedra_unit",
    "is_module_enabled",
    "kafedra_q",
    "kafedra_unit_types",
    "narrow_kafedra_rows",
    "members_covering_unit",
    "module_items",
    "permission_scope_unit_types",
    "permission_scope_units",
    "register_cabinet_section_resolver",
    "register_managed_settings_key",
    "request_active_memberships",
    "request_holds_student_key",
    "resolve_ancestor",
    "resolve_members_access",
    "save_review_identity_reveal",
    "scope_memberships_by_unit",
    "scope_org_units",
    "unit_in_scope",
    "set_module_enabled",
    "set_settings_keys",
    "student_only_q",
    "student_record_scope_q",
    "unit_type_label",
    "update_settings_key",
    "user_scope_covers_unit",
    "validate_unit_type_for_org",
    "visible_chairs",
    "visible_units_queryset",
]
