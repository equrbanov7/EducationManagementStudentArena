"""structure_views — geriyə-uyğun fasad paketi (urls.py modul-atributu ilə çağırır)."""

from .context import build_organization_faculties_context, build_organization_kafedras_context  # noqa: F401
from .endpoints import (  # noqa: F401
    organization_faculties,
    organization_kafedras,
    organization_unit_detail,
)
from .tree import (  # noqa: F401
    build_structure_tree_context,
    chair_detail_context,
    visible_chairs,
)
from .unit_detail import build_unit_detail_context  # noqa: F401

__all__ = [
    "build_organization_faculties_context",
    "build_organization_kafedras_context",
    "build_structure_tree_context",
    "chair_detail_context",
    "visible_chairs",
    "build_unit_detail_context",
    "organization_faculties",
    "organization_kafedras",
    "organization_unit_detail",
]
