"""Explicit public contracts for cross-module consumers; implementation stays local."""

from .cabinet_modules import CABINET_MODULES  # noqa: F401
from .cabinet_modules import default_disabled_sections  # noqa: F401
from .cabinet_modules import disabled_sections  # noqa: F401
from .cabinet_modules import is_module_enabled  # noqa: F401
from .cabinet_modules import module_items  # noqa: F401
from .cabinet_modules import set_module_enabled  # noqa: F401
from .default_roles import get_default_roles_for_org_type  # noqa: F401
from .groups_registry import build_groups_registry  # noqa: F401
from .permissions import get_permission_label  # noqa: F401
from .scoping import EMPTY_SCOPE  # noqa: F401
from .scoping import ORG_WIDE_SCOPE  # noqa: F401
from .scoping import UnitScope  # noqa: F401
from .scoping import get_permission_scope  # noqa: F401
from .scoping import scope_memberships_by_unit  # noqa: F401
from .scoping import scope_org_units  # noqa: F401
from .scoping import user_scope_covers_unit  # noqa: F401
from .services import get_active_memberships  # noqa: F401
from .structure_views import build_structure_tree_context  # noqa: F401
from .structure_views import chair_detail_context  # noqa: F401
from .structure_views import visible_chairs  # noqa: F401
from .structure_views.constants import KAFEDRA_UNIT_TYPES  # noqa: F401
from .structure_views.constants import TEACHER_ROLE_NAMES  # noqa: F401
from .structure_views.registry import unit_type_label  # noqa: F401
from .unit_heads import ancestor_unit_ids  # noqa: F401
from .unit_heads import chair_head_memberships_for_unit  # noqa: F401
from .unit_heads import dean_memberships_for_unit  # noqa: F401
from .unit_heads import members_covering_unit  # noqa: F401
from .unit_heads import resolve_ancestor  # noqa: F401
from .unit_types import UNIT_TYPES_BY_ORG  # noqa: F401
from .unit_types import validate_unit_type_for_org  # noqa: F401
from .views import _visible_units_queryset as visible_units_queryset  # noqa: F401
from .views.shared._helpers import _can_manage_organization as can_manage_organization  # noqa: F401
from .views.shared._helpers import _has_org_permission as has_org_permission  # noqa: F401

__all__ = [
    "CABINET_MODULES",
    "EMPTY_SCOPE",
    "KAFEDRA_UNIT_TYPES",
    "ORG_WIDE_SCOPE",
    "TEACHER_ROLE_NAMES",
    "UNIT_TYPES_BY_ORG",
    "UnitScope",
    "ancestor_unit_ids",
    "build_groups_registry",
    "build_structure_tree_context",
    "can_manage_organization",
    "chair_detail_context",
    "chair_head_memberships_for_unit",
    "dean_memberships_for_unit",
    "default_disabled_sections",
    "disabled_sections",
    "get_active_memberships",
    "get_default_roles_for_org_type",
    "get_permission_label",
    "get_permission_scope",
    "has_org_permission",
    "is_module_enabled",
    "members_covering_unit",
    "module_items",
    "resolve_ancestor",
    "scope_memberships_by_unit",
    "scope_org_units",
    "set_module_enabled",
    "unit_type_label",
    "user_scope_covers_unit",
    "validate_unit_type_for_org",
    "visible_chairs",
    "visible_units_queryset",
]
