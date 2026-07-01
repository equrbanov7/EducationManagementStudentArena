"""statistics_selectors — geriyə-uyğun fasad paketi."""

from ._shared import UNSUPPORTED_METRICS, build_ai_stats_payload  # noqa: F401
from .org_admin import get_org_admin_statistics  # noqa: F401
from .student import get_student_statistics  # noqa: F401
from .superadmin import get_superadmin_statistics  # noqa: F401
from .teacher import get_teacher_statistics  # noqa: F401

__all__ = [
    "get_student_statistics",
    "get_teacher_statistics",
    "get_org_admin_statistics",
    "get_superadmin_statistics",
    "build_ai_stats_payload",
    "UNSUPPORTED_METRICS",
]
