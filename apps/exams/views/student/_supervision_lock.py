"""Nəzarət kilidinin server tərəfində tətbiqi — praktik (kod) imtahan JSON uçları üçün.

EXAMQA R9 (2026-10-01): test/yazılı axınında olduğu kimi (``student/attempts.py``) kilid əvvəl yalnız
klient overlay-i idi — overlay-i DevTools ilə silən tələbə kilid altında kod saxlaya / işlədə / təhvil
verə bilirdi. Kilidli cəhdə yazı qəbul olunmur (423).
"""

from django.http import JsonResponse
from django.utils.translation import pgettext

from apps.exams.features import exam_supervision_enabled


def supervision_locked_json(attempt):
    if exam_supervision_enabled() and getattr(attempt, "supervision_status", "") == "locked":
        message = pgettext(
            "exams.view.access.message",
            "İmtahanınız nəzarətçi tərəfindən dayandırılıb — kilid açılana qədər cavablar qəbul edilmir.",
        )
        return JsonResponse({"success": False, "error": message, "locked": True}, status=423)
    return None
