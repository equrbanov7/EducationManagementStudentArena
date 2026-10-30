"""Explicit public contracts for cross-module consumers; implementation stays local."""

from .approval_registry import build_approval  # noqa: F401
from .center_registry import build_center  # noqa: F401
from .overview_registry import build_overview_section  # noqa: F401
from .review_registry import build_visa  # noqa: F401
from .services import (  # noqa: F401
    assign_teacher,
    ensure_can_distribute,
    ensure_distribution_stage,
    legacy_loads,
    open_amendment,
    save_row,
    unassign,
)
from .services.journal_assignments import teacher_journal_assignments  # noqa: F401
from .services.load_upload_parsing import parse_workbook as parse_load_workbook  # noqa: F401
from .services.norms import (  # noqa: F401
    StaffRateError,
    admin_teacher_ids,
    current_rule,
    norm_rule_note,
    norms_for,
    staff_rate_error,
)
from .services.offering_sync import sync_task_offerings  # noqa: F401
from .services.people import home_chair_rank, home_chairs, is_assignable_teacher, join_chair_as_teacher  # noqa: F401
from .services.repair_fingerprints import academic_database_fingerprint as journal_academic_fingerprint  # noqa: F401
from .services.repair_fingerprints import queryset_database_fingerprint
from .services.roster_profile import restore_roster_profile, sync_roster_profile  # noqa: F401
from .teacher_hooks import register_chair_teacher_resolver  # noqa: F401

__all__ = [
    "journal_academic_fingerprint",
    "queryset_database_fingerprint",
    "assign_teacher",
    "is_assignable_teacher",
    "ensure_can_distribute",
    "ensure_distribution_stage",
    "open_amendment",
    "save_row",
    "unassign",
    "sync_task_offerings",
    "teacher_journal_assignments",
    "StaffRateError",
    "admin_teacher_ids",
    "build_approval",
    "build_center",
    "build_overview_section",
    "build_visa",
    "current_rule",
    "home_chair_rank",
    "home_chairs",
    "join_chair_as_teacher",
    "legacy_loads",
    "norm_rule_note",
    "norms_for",
    "parse_load_workbook",
    "register_chair_teacher_resolver",
    "restore_roster_profile",
    "staff_rate_error",
    "sync_roster_profile",
]
