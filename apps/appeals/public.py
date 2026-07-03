"""appeals modulunun PUBLIC API fasadı (M3-B, 2026-07-02).

QEYD: exams appeals-i İMPORT ETMİR — bal-düzəliş inteqrasiyası
apps.exams.score_adjustments hook-ları ilə gedir (ready()-də qeydiyyat).
Bu fasad profil bölmələri kimi yuxarı-səviyyə istehlakçılar üçündür.
"""

from apps.appeals.services import (  # noqa: F401
    appeal_bonus_map,
    apply_bonus_to_test_result,
)
from apps.appeals.views import _can_open_appeal_management as can_open_appeal_management  # noqa: F401
from apps.appeals.views import (  # noqa: F401
    build_manage_appeals_context,
    build_my_appeals_context,
)

__all__ = [
    "appeal_bonus_map",
    "can_open_appeal_management",
    "apply_bonus_to_test_result",
    "build_manage_appeals_context",
    "build_my_appeals_context",
]
