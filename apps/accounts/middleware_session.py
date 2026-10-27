"""Sessiyanın fəaliyyətsizlik / «brauzer açıq deyil» limiti + brauzer-bağlanma rejimi.

``apps/accounts/middleware.py``-dən ayrıldı (2026-10-27, o fayl 600-sətir tavanına yaxındır); ad dəyişmir —
``config/settings`` hələ ``apps.accounts.middleware.SessionTimeoutMiddleware``-ə istinad edir (orada re-export).

Sahib 2026-10-27 əlavələri (bax :mod:`apps.accounts.session_policy`):

* **Fon pingi** (``accounts:session_ping``, ``?active=0``) «brauzer açıqdır» sayılır, amma istifadəçi FƏALİYYƏTİ
  sayılmır — açıq qalmış tab fəaliyyətsizlik limitini əbədi uzatmasın. ``?active=1`` (son pingdən bəri klik/yazı
  olub) və digər bütün sorğular fəaliyyətdir.
* Sessiya bu qaydalarla bitəndə AJAX/JSON sorğusu ``401 {"session_expired": true, "message": …}`` alır (JS
  lokallaşdırılmış «yenidən daxil olun» pəncərəsi göstərir, xam xəta yox); adi sorğu view-a davam edir
  (``login_required`` giriş səhifəsinə aparır, orada səbəb bir dəfə göstərilir).
* İmtahan gedişində (``session_policy.exam_in_progress``) sessiya bitirilmir.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import SESSION_KEY, logout
from django.http import JsonResponse
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.accounts import session_policy


def wants_json(request) -> bool:
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    accept = (request.headers.get("Accept") or "").lower()
    return "application/json" in accept and "text/html" not in accept


def session_expired_response(request, reason: str):
    return JsonResponse(
        {
            "ok": False,
            "error": "session_expired",
            "session_expired": True,
            "authenticated": False,
            "reason": reason,
            "message": session_policy.ended_message(reason),
            "login_url": settings.LOGIN_URL,
        },
        status=401,
    )


class SessionTimeoutMiddleware:
    """
    Automatically log users out after a period of inactivity.

    Performance note: the ``last_activity`` timestamp is only written back to
    the session at most once every ``SESSION_ACTIVITY_WRITE_INTERVAL`` seconds.
    Writing it on every request marked the session dirty on every authenticated
    hit, forcing a session save (a DB write under db/cached_db backends) for
    each request and serialising authenticated traffic under load. Throttling
    the write keeps inactivity enforcement accurate (the stored value is at most
    one interval stale against a multi-hour timeout) while removing that
    per-request write. The presence stamp (``session_policy.SEEN_KEY``) follows
    the same throttle (capped at a quarter of the presence limit).
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.timeout_seconds = settings.SESSION_INACTIVITY_TIMEOUT
        self.write_interval = getattr(settings, "SESSION_ACTIVITY_WRITE_INTERVAL", 300)
        self._ping_path = None

    def _timeout_seconds(self):
        """2026-10-03: «Sistem tənzimləmələri»ndə RİM rəhbərinin dəyəri (saat) varsa o, yoxdursa mühitin ayarı."""
        from core import runtime_settings

        hours = runtime_settings.override("session.idle_hours")
        return int(hours) * 3600 if hours else self.timeout_seconds

    def _is_background_ping(self, request) -> bool:
        if self._ping_path is None:
            try:
                self._ping_path = reverse("accounts:session_ping")
            except NoReverseMatch:
                self._ping_path = ""
        return bool(self._ping_path) and request.path == self._ping_path and request.GET.get("active") != "1"

    def __call__(self, request):
        # Backend siyahısından çıxarılmış köhnə/bypass backend sessiyası Django
        # tərəfindən anonymous kimi yüklənir, amma auth açarları sessiyada qala
        # bilər. Onları request view-a çatmamış tam sil.
        if not request.user.is_authenticated and SESSION_KEY in request.session:
            logout(request)
            return self.get_response(request)
        if request.user.is_authenticated:
            from .identity import request_user_login_blocked

            if request_user_login_blocked(request.user):
                logout(request)
                return self.get_response(request)
            ended = self._enforce(request, request.user, timezone.now())
            if ended is not None:
                return ended
        return self.get_response(request)

    def _enforce(self, request, user, now):
        session = request.session
        last_activity = session_policy.parse_stamp(session.get("last_activity"))
        seen = session_policy.parse_stamp(session.get(session_policy.SEEN_KEY)) or last_activity
        presence = session_policy.presence_seconds(request, user)

        reason = None
        if last_activity and (now - last_activity).total_seconds() > self._timeout_seconds():
            reason = session_policy.REASON_IDLE
        elif presence and seen and (now - seen).total_seconds() > presence:
            reason = session_policy.REASON_PRESENCE
        if reason and not session_policy.exam_in_progress(request, user):
            logout(request)
            request.session[session_policy.ENDED_KEY] = reason
            if wants_json(request):
                return session_expired_response(request, reason)
            return self.get_response(request)

        seen_interval = min(self.write_interval, presence // 4) if presence else self.write_interval
        write_seen = (
            seen is None
            or session.get(session_policy.SEEN_KEY) is None
            or (now - seen).total_seconds() >= seen_interval
        )
        if not last_activity:
            # First authenticated request (or unparseable value): seed it.
            session["last_activity"] = now.isoformat()
            write_seen = True
        elif not self._is_background_ping(request) and (now - last_activity).total_seconds() >= self.write_interval:
            # Refresh the timestamp only once per interval to avoid a session write on every request.
            session["last_activity"] = now.isoformat()
            write_seen = True  # eyni yazıda — ayrıca sessiya yazısı olmasın
        if write_seen:
            session[session_policy.SEEN_KEY] = now.isoformat()
        session_policy.apply_browser_close(request, user)
        return None


__all__ = ["SessionTimeoutMiddleware", "session_expired_response", "wants_json"]
