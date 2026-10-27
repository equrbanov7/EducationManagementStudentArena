"""``GET /accounts/session/ping/`` — açıq səhifənin «buradayam» pingi (sahib 2026-10-27).

``static/js/core/session_keepalive.js`` hər bir neçə dəqiqədən bir çağırır:

* ``?active=1`` — son pingdən bəri istifadəçi klik/yazı edib: fəaliyyət sayılır, fəaliyyətsizlik limiti uzanır
  (uzun formanı doldurarkən sessiya bitmir). ``active=0`` yalnız «brauzer açıqdır» siqnalıdır
  (``SessionTimeoutMiddleware`` onu fəaliyyət saymır).
* Cavabda TƏZƏ CSRF tokeni qayıdır — JS səhifədəki köhnə ``csrfmiddlewaretoken`` sahələrini yeniləyir; başqa tabda
  yenidən daxil olandan (token dəyişir) sonra köhnə tab «Səhifə köhnəlib» xətası vermir.
* Sessiya bitibsə ``authenticated: false`` + lokallaşdırılmış mətn (middleware 401 də qaytara bilər — eyni forma).

GET-dir (CSRF tələb etmir — məhz köhnəlmiş token vəziyyətində işləməlidir), yan təsiri yalnız sessiya möhürüdür.
"""

from __future__ import annotations

from django.conf import settings
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts import session_policy


@never_cache
@require_GET
def session_ping(request):
    user = request.user
    payload = {
        "ok": True,
        "authenticated": bool(user.is_authenticated),
        "csrf_token": get_token(request),
        "login_url": settings.LOGIN_URL,
    }
    if user.is_authenticated:
        presence = session_policy.presence_seconds(request, user)
        payload.update(presence_seconds=presence, heartbeat_seconds=session_policy.heartbeat_seconds(presence))
    else:
        payload["message"] = session_policy.ended_message(session_policy.REASON_IDLE)
    return JsonResponse(payload)


__all__ = ["session_ping"]
