"""Explicit public contracts for cross-module consumers; implementation stays local."""

from .approval_registry import build_approval  # noqa: F401
from .center_registry import build_center  # noqa: F401
from .overview_registry import build_overview_section  # noqa: F401
from .review_registry import build_visa  # noqa: F401
from .services import legacy_loads  # noqa: F401
from .services.norms import (  # noqa: F401
    StaffRateError,
    admin_teacher_ids,
    current_rule,
    norm_rule_note,
    norms_for,
    staff_rate_error,
)
from .services.roster_profile import restore_roster_profile, sync_roster_profile  # noqa: F401
from .teacher_hooks import register_chair_teacher_resolver  # noqa: F401

__all__ = [
    "StaffRateError",
    "admin_teacher_ids",
    "build_approval",
    "build_center",
    "build_overview_section",
    "build_visa",
    "current_rule",
    "legacy_loads",
    "norm_rule_note",
    "norms_for",
    "register_chair_teacher_resolver",
    "restore_roster_profile",
    "staff_rate_error",
    "sync_roster_profile",
]
