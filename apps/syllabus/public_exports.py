"""Explicit public contracts for cross-module consumers; implementation stays local."""

from . import services  # noqa: F401
from .assessment_formula import activity_kinds_for_offering  # noqa: F401
from .constants import LESSON_HOUR_KINDS  # noqa: F401
from .constants import MIN_DESCRIPTION_CHARS  # noqa: F401
from .constants import MIN_GOAL_CHARS  # noqa: F401
from .constants import MIN_OUTCOMES  # noqa: F401
from .constants import PERM_EDIT  # noqa: F401
from .constants import PERM_REVIEW  # noqa: F401
from .constants import QUEUE_STATUSES  # noqa: F401
from .constants import RULE_SECTIONS  # noqa: F401
from .constants import SECTION_ORDER  # noqa: F401
from .constants import SELFWORK_DISALLOWED  # noqa: F401
from .constants import SELFWORK_OPTIONS  # noqa: F401
from .constants import SELFWORK_TOTAL_SCORE  # noqa: F401
from .constants import STATUS_NEXT_STEP  # noqa: F401
from .constants import STATUS_SORT_INDEX  # noqa: F401
from .constants import WEEK_ROWS  # noqa: F401
from .constants import SectionKey  # noqa: F401
from .constants import SyllabusStatus  # noqa: F401
from .document import BLOCK_TITLES  # noqa: F401
from .document import blocks_by_key  # noqa: F401
from .document import build_document  # noqa: F401
from .document import build_preview_blocks  # noqa: F401
from .document import reuse_approval_note  # noqa: F401
from .policy import escalation_days  # noqa: F401
from .policy import sla_days  # noqa: F401
from .policy import standard_splits  # noqa: F401

# Sahib 2026-10-10: sərbəst iş / 5 + 5 qaydası — sillabus görünüşləri dövrə görə (bax ``rules``).
from .rules import LEGACY as LEGACY_RULE  # noqa: F401
from .rules import SyllabusRule  # noqa: F401
from .rules import selfwork_active_for_version  # noqa: F401
from .rules import current as current_rule  # noqa: F401
from .rules import for_period as rule_for_period  # noqa: F401
from .rules import for_syllabus as rule_for_syllabus  # noqa: F401
from .rules import for_version as rule_for_version  # noqa: F401
from .services import section_data_map  # noqa: F401
from .services import version_diff  # noqa: F401
from .services import version_timeline  # noqa: F401

# Sahib 2026-10-25: jurnal dərsinin ``syllabus_week`` sətri → mövzu (toplu, bax ``services.week_rows``).
from .services.week_rows import approved_week_rows_for_offerings  # noqa: F401
from .services.week_rows import plan_rows as week_plan_rows  # noqa: F401
from .state_machine import Transition  # noqa: F401
from .state_machine import TransitionDenied  # noqa: F401

__all__ = [
    "BLOCK_TITLES",
    "LEGACY_RULE",
    "blocks_by_key",
    "SyllabusRule",
    "activity_kinds_for_offering",
    "approved_week_rows_for_offerings",
    "week_plan_rows",
    "current_rule",
    "rule_for_period",
    "rule_for_syllabus",
    "rule_for_version",
    "selfwork_active_for_version",
    "standard_splits",
    "LESSON_HOUR_KINDS",
    "MIN_DESCRIPTION_CHARS",
    "MIN_GOAL_CHARS",
    "MIN_OUTCOMES",
    "PERM_EDIT",
    "PERM_REVIEW",
    "QUEUE_STATUSES",
    "RULE_SECTIONS",
    "SECTION_ORDER",
    "SELFWORK_DISALLOWED",
    "SELFWORK_OPTIONS",
    "SELFWORK_TOTAL_SCORE",
    "STATUS_NEXT_STEP",
    "STATUS_SORT_INDEX",
    "SectionKey",
    "SyllabusStatus",
    "Transition",
    "TransitionDenied",
    "WEEK_ROWS",
    "build_document",
    "build_preview_blocks",
    "reuse_approval_note",
    "escalation_days",
    "section_data_map",
    "services",
    "sla_days",
    "version_diff",
    "version_timeline",
]
