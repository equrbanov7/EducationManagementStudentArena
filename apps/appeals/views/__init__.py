"""
appeals/views — FASAD (F4 rol-skeleti, 2026-07-02, AGENTS §6).

Köhnə tək-fayllı views.py {student,teacher,shared} rol paketlərinə bölünüb.
`apps.appeals.views` import səthi (urls + accounts profil dashboard-unun
istifadə etdiyi build_*_context / _can_open_appeal_management daxil) dəyişmir.
"""

from .shared import appeal_detail
from .student import appeal_create, build_my_appeals_context, my_appeals
from .teacher import (
    _can_open_appeal_management,
    build_manage_appeals_context,
    manage_appeals,
    review_appeal,
)

__all__ = [
    "appeal_create",
    "my_appeals",
    "appeal_detail",
    "manage_appeals",
    "review_appeal",
    "build_my_appeals_context",
    "build_manage_appeals_context",
    "_can_open_appeal_management",
]
