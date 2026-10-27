"""Sessiya siyasəti: brauzer bağlananda çıxış, «brauzer açıq deyil» limiti, imtahan istisnası (sahib 2026-10-27).

Sahib: «müəllim brauzeri bağlayıb və ya kompüteri söndürüb yenidən açanda kabinetdən çıxmış olsun». İki qat:

1. **Sessiya kukisi brauzer bağlananda silinir** (``request.session.set_expiry(0)``) — runtime açarı
   ``session.browser_close_scope`` əhatəsindəki istifadəçilər üçün (defolt: müəllim + əməkdaş, tələbə yox).
   Açar dəyişəndə mövcud sessiyalar da növbəti sorğuda yeni qaydaya keçir.
2. **«Brauzer açıq deyil» limiti** (``session.presence_minutes``) — Chrome-un «qaldığım yerdən davam et»
   rejimi sessiya kukisini bərpa edir, yuxu rejimindəki noutbuk isə kukini heç silmir. Ona görə server son
   sorğunun vaxtını (``SEEN_KEY``) saxlayır; açıq səhifə ``static/js/core/session_keepalive.js`` ilə mütəmadi
   «buradayam» pingi göndərir. Bu limit qədər HEÇ BİR sorğu gəlməyibsə sessiya bitir.

İmtahan istisnası: zal bileti sessiyada, imtahan-verən yol, başlanmış cəhd (``in_progress``, son 12 saat) və ya
aparıcının aktiv canlı imtahanı varsa sessiya HEÇ VAXT bu qatlarla (və fəaliyyətsizlik limiti ilə) bitirilmir.
Yoxlama yalnız çıxış qərarı anında edilir (nadir) — adi sorğuya sorğu (DB) əlavə etmir.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from types import SimpleNamespace

from django.utils import timezone
from django.utils.translation import pgettext

logger = logging.getLogger(__name__)

_CTX = "accounts.session"

#: Son sorğunun vaxtı (fon pingi daxil) — «brauzer açıqdır» siqnalı (ISO mətn).
SEEN_KEY = "_ems_seen"
#: Sessiya bu qayda ilə bitəndə TƏZƏ anonim sessiyaya yazılan səbəb — giriş səhifəsi bir dəfə göstərir.
ENDED_KEY = "_ems_session_ended"
#: Hesab növü (tələbə / heyət) — sessiyada bir dəfə hesablanır (``{"uid": pk, "kind": ...}``).
KIND_KEY = "_ems_session_kind"

REASON_IDLE = "idle"
REASON_PRESENCE = "presence"

_EXAM_ATTEMPT_WINDOW = timedelta(hours=12)
_LIVE_SESSION_WINDOW = timedelta(hours=6)


def parse_stamp(raw):
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None
    return None


def _session_settings():
    from core import runtime_settings_session

    return runtime_settings_session


def session_kind(request, user) -> str:
    """'student' | 'staff' — sessiyada keşlənir (ilk sorğuda bir dəfə üzvlük sorğusu)."""
    session = request.session
    cached = session.get(KIND_KEY)
    if isinstance(cached, dict) and cached.get("uid") == user.pk and cached.get("kind") in ("student", "staff"):
        return cached["kind"]
    from apps.accounts.network_zone import account_kind

    # Hesab növü sessiyanın SAHİBİNƏ aiddir (view-as hədəfinə yox); giriş siqnalında ``request.user`` hələ yoxdur.
    actor = SimpleNamespace(user=user, organization=None, is_view_as=False)
    kind = "student" if account_kind(actor) == "student" else "staff"
    session[KIND_KEY] = {"uid": user.pk, "kind": kind}
    return kind


def remember_at_login(request, user) -> None:
    """``user_logged_in``: hesab növü və brauzer-bağlanma rejimi GİRİŞ anında yazılır — sonrakı sorğular sorğusuz."""
    if request is None or getattr(request, "session", None) is None or user is None:
        return
    try:
        session_kind(request, user)
        apply_browser_close(request, user)
    except Exception:  # noqa: BLE001 — giriş heç vaxt bu optimallaşdırmaya görə pozulmasın (middleware təkrar edir)
        logger.warning("session_policy: login-time kind lookup failed", exc_info=True)


def in_scope(request, user) -> bool:
    """Brauzer-bağlanma + «brauzer açıq deyil» qaydaları bu istifadəçiyə aiddirmi."""
    rs = _session_settings()
    scope = rs.browser_close_scope()
    if scope == rs.SCOPE_OFF:
        return False
    if scope == rs.SCOPE_ALL:
        return True
    return session_kind(request, user) != "student"


def presence_seconds(request, user) -> int:
    """Bu istifadəçi üçün «brauzer açıq deyil» limiti (saniyə); 0 — tətbiq olunmur."""
    seconds = _session_settings().presence_seconds()
    if not seconds or not in_scope(request, user):
        return 0
    return seconds


def heartbeat_seconds(presence: int) -> int:
    """Açıq səhifənin ping intervalı: limitin ~1/4-i (60…300 san.); limit yoxdursa 10 dəq. (yalnız CSRF/aşkarlama)."""
    if not presence:
        return 600
    return max(60, min(300, presence // 4))


def apply_browser_close(request, user) -> None:
    """Sessiya kukisinin brauzer-bağlanma rejimini runtime açarına uyğunlaşdırır (yalnız fərq olanda yazır)."""
    session = request.session
    wanted = in_scope(request, user)
    if wanted and not session.get_expire_at_browser_close():
        session.set_expiry(0)
    elif not wanted and session.get("_session_expiry") == 0:
        session.set_expiry(None)


def exam_in_progress(request, user) -> bool:
    """İmtahan gedişindədirmi — onda sessiya bu middleware tərəfindən bitirilmir."""
    from apps.accounts.middleware_center_exam import CENTER_SESSION_KEY, is_center_exam_path

    if request.session.get(CENTER_SESSION_KEY):
        return True
    if is_center_exam_path(request, request.path):
        return True
    from django.apps import apps as django_apps

    from core.rls import bypass_rls

    now = timezone.now()
    attempt_model = django_apps.get_model("exams", "ExamAttempt")
    live_model = django_apps.get_model("live_exam", "LiveSession")
    live_states = (live_model.STATE_LOBBY, live_model.STATE_QUESTION, live_model.STATE_REVEAL)
    with bypass_rls():
        if attempt_model.objects.filter(
            user=user, status="in_progress", started_at__gte=now - _EXAM_ATTEMPT_WINDOW
        ).exists():
            return True
        return live_model.objects.filter(
            host_user=user, state__in=live_states, created_at__gte=now - _LIVE_SESSION_WINDOW
        ).exists()


def ended_message(reason: str) -> str:
    if reason == REASON_PRESENCE:
        return pgettext(
            _CTX,
            "Brauzer bağlandığı və ya kompüter söndüyü üçün sessiyanız təhlükəsizlik məqsədilə başa çatdı. "
            "Davam etmək üçün yenidən daxil olun.",
        )
    return pgettext(
        _CTX,
        "Uzun müddət heç bir əməliyyat edilmədiyi üçün sessiyanız başa çatdı. Davam etmək üçün yenidən daxil olun.",
    )


def pop_ended_notice(request) -> str:
    """Giriş səhifəsi üçün: sessiya qayda ilə bitibsə izah mətni (bir dəfə), yoxdursa boş."""
    session = getattr(request, "session", None)
    if session is None:
        return ""
    reason = session.pop(ENDED_KEY, None)
    return ended_message(reason) if reason in (REASON_IDLE, REASON_PRESENCE) else ""


__all__ = [
    "ENDED_KEY",
    "KIND_KEY",
    "REASON_IDLE",
    "REASON_PRESENCE",
    "SEEN_KEY",
    "apply_browser_close",
    "ended_message",
    "exam_in_progress",
    "heartbeat_seconds",
    "in_scope",
    "parse_stamp",
    "pop_ended_notice",
    "presence_seconds",
    "remember_at_login",
    "session_kind",
]
