"""
appeals/views — FASAD (F4 rol-skeleti, 2026-07-02, AGENTS §6).

Köhnə tək-fayllı views.py {student,teacher,shared} rol paketlərinə bölünüb.
`apps.appeals.views` import səthi (urls + accounts profil dashboard-unun
istifadə etdiyi build_*_context / _can_open_appeal_management daxil) dəyişmir.
"""

from .shared import appeal_detail
from .student import appeal_create, build_my_appeals_context, hall_appeal_done, my_appeals
from .teacher import (
    _can_open_appeal_management,
    appeal_stats_ai,
    appeal_stats_charts,
    appeal_stats_data,
    appeal_stats_filters,
    build_manage_appeals_context,
    count_pending_manage_appeals,
    key_correction_apply,
    key_correction_revoke,
    manage_appeals,
    review_appeal,
    teaching_appeals,
)
from .teacher.teaching import build_teaching_appeals_context

__all__ = [
    "appeal_create",
    "hall_appeal_done",
    "my_appeals",
    "appeal_detail",
    "manage_appeals",
    "review_appeal",
    "teaching_appeals",
    "build_teaching_appeals_context",
    "key_correction_apply",
    "key_correction_revoke",
    "build_my_appeals_context",
    "build_manage_appeals_context",
    "count_pending_manage_appeals",
    "_can_open_appeal_management",
    "appeal_stats_data",
    "appeal_stats_charts",
    "appeal_stats_filters",
    "appeal_stats_ai",
]
