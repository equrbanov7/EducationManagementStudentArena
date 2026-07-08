"""Superadmin səthi (F6 rol-skeleti, 2026-07-02).

QEYD: services/registration lazy olaraq `_notify_superadmins_of_pending_org`-u
buradan idxal edir (AGENTS §1 — kənarda istifadə olunan underscore ad).
"""

from .endpoints import (
    _notify_superadmins_of_pending_org,
    build_superadmin_ai_settings_context,
    superadmin_ai_settings,
    superadmin_organizations,
)
from .exam_rooms import superadmin_exam_rooms

__all__ = [
    "superadmin_organizations",
    "superadmin_ai_settings",
    "superadmin_exam_rooms",
    "build_superadmin_ai_settings_context",
    "_notify_superadmins_of_pending_org",
]
