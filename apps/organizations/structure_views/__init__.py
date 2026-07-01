"""structure_views — geriyə-uyğun fasad paketi (urls.py modul-atributu ilə çağırır)."""

from .context import build_organization_faculties_context, build_organization_kafedras_context  # noqa: F401
from .endpoints import organization_faculties, organization_kafedras  # noqa: F401

__all__ = [
    "build_organization_faculties_context",
    "build_organization_kafedras_context",
    "organization_faculties",
    "organization_kafedras",
]
