"""statistics_metrics — «Statistika» bölməsinin rol-aware metrik modeli (2026-09-12).

Giriş nöqtəsi: :func:`build_statistics_dashboard`. Rəqəmlər (`*_metrics`) qısa
keşlənir; etiketlər (`presenter*`) hər sorğuda aktiv dildə qurulur.
"""

from ._shared import Window, build_window, parse_date, period_label, resolve_period  # noqa: F401
from .exam_center import exam_center_metrics  # noqa: F401
from .org import org_metrics  # noqa: F401
from .presenter import present_student, present_teacher  # noqa: F401
from .presenter_org import present_exam_center, present_org, present_superadmin  # noqa: F401
from .student import student_metrics  # noqa: F401
from .superadmin import superadmin_metrics  # noqa: F401
from .teacher import teacher_metrics  # noqa: F401

__all__ = [
    "Window",
    "build_window",
    "parse_date",
    "period_label",
    "resolve_period",
    "student_metrics",
    "teacher_metrics",
    "exam_center_metrics",
    "org_metrics",
    "superadmin_metrics",
    "present_student",
    "present_teacher",
    "present_exam_center",
    "present_org",
    "present_superadmin",
]
