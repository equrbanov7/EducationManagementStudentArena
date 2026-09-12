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


# Explicit exports keep external callers out of implementation modules.
from .public_exports import *  # noqa: E402,F401,F403
from .public_exports import __all__ as _api_exports  # noqa: E402

__all__ += [name for name in _api_exports if name not in __all__]
