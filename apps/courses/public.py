"""courses modulunun PUBLIC API fasadı (M3-B, 2026-07-02).

Genişlənmə nöqtəsi: apps.courses.dashboard_sources — task modulları kurs
dashboard-una bölmə provider-lərini ready()-də qeyd edir. Course/
CourseMembership modellərinə ehtiyac üçün ORM əlaqələri və ya get_model.
"""

from apps.courses.dashboard_sources import (  # noqa: F401
    build_context,
    register,
)

__all__ = [
    "build_context",
    "register",
]
