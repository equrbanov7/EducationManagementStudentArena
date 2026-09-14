"""Bal yazan / idxal edən JSON endpoint-lər üçün istifadəçi başına rate-limit.

Backend auditi 2026-09-13, F-15 (P3) — hesabat §27 (2026-09-14): `workload:assign`,
`student_registry_action`, `exam_score_import_apply` və `rim_action` yazı
endpoint-lərində heç bir limit yox idi (yalnız OTP / monitorinq / AI limitlidir).
Skript və ya ilişib qalan klient eyni hesabdan saniyədə yüzlərlə yazı göndərə
bilirdi. Hədd QƏSDƏN genişdir (defolt ``120/1m`` — bax
``config/settings/components/admin_ratelimit.py``): normal iş axını (toplu bal
daxiletmə, RİM əməliyyatları) toxunulmur, yalnız avtomatlaşdırılmış «spray»
kəsilir. Vedrə (scope, istifadəçi id) üzrədir; anonim sorğu onsuz da
``login_required`` ilə kəsilir. Spesifikasiya pozuqdursa ``core.rate_limit``
fail-closed işləyir (429).
"""

from __future__ import annotations

from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.utils.translation import pgettext

from core.rate_limit import record_rate_limit_hit

_CTX = "core.rate_limit"


def score_write_rate_limited(scope: str):
    """View dekoratoru: ``settings.SCORE_WRITE_RATE_LIMIT`` üzrə istifadəçi başına vedrə; dolanda 429 JSON."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user_id = getattr(getattr(request, "user", None), "pk", None)
            limited, retry_after = record_rate_limit_hit(
                scope, getattr(settings, "SCORE_WRITE_RATE_LIMIT", None), user_id
            )
            if limited:
                response = JsonResponse(
                    {
                        "ok": False,
                        "error": "rate_limited",
                        "message": pgettext(_CTX, "Çox tez-tez sorğu göndərilir — bir az sonra yenidən cəhd edin."),
                        "retry_after": retry_after,
                    },
                    status=429,
                )
                if retry_after:
                    response["Retry-After"] = str(retry_after)
                return response
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


__all__ = ["score_write_rate_limited"]
