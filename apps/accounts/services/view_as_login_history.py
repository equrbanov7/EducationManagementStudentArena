"""«Giriş tarixçəsi» — «İstifadəçi profilinə bax» rejimində hədəfin giriş/çıxış izi (sahib 2026-10-26).

Sahib: «məzun olmuş olsa da tələbə nəticələrinə baxa bilim, giriş-çıxış və s. — bu
"profilə bax" yerindən onları görə bilim». Mənbə audit jurnalının platforma
səviyyəli ``login`` / ``logout`` sətirləridir (``apps/audit/signals.py`` — hər uğurlu
giriş və çıxış; ``organization`` NULL-dur, ona görə heç bir tenanta aid deyil).

QAPI (FAIL-CLOSED):

* YALNIZ aktiv view-as sessiyasında (``request.is_view_as``) — öz kabinetində heç kim
  bu paneli görmür (öz izi üçün ayrıca bölmə yoxdur, bu tapşırığın əhatəsi deyil);
* ƏSL istifadəçi (``request.real_user``) arxiv baxıcısıdır: superadmin və ya view-as
  təşkilatında ``ARCHIVE_VIEWER_ROLE_NAMES`` (RİM rəhbəri / əməkdaşı) üzvlüyü — yəni
  məzun/xaric hesablara da baxa bilən eyni dairə. Dekan/tyutor kimi READONLY aktorlar
  hədəfin İP/cihaz izini görmür.

Sorğu ``user=<hədəf>`` ilə açıq süzülür — ``bypass_rls`` kirayəçi sızması vermir
(view-as altında RLS konteksti hədəfin təşkilatıdır, login sətirləri isə org-suzdur).
Parol, sessiya açarı və s. bu sətirlərdə YOXDUR — yalnız vaxt, İP və brauzer.
"""

from __future__ import annotations

import re

from django.utils import timezone
from django.utils.translation import pgettext

from core.constants import AuditAction
from core.rls import bypass_rls

_CTX = "accounts.view_as"

#: Paneldə göstərilən ən çox sətir (sonuncular).
HISTORY_LIMIT = 30

_UA_BROWSERS = (
    ("Edge", re.compile(r"Edg(?:e|A|iOS)?/(\d+)")),
    ("Opera", re.compile(r"OPR/(\d+)")),
    ("Firefox", re.compile(r"Firefox/(\d+)")),
    ("Chrome", re.compile(r"(?:Chrome|CriOS)/(\d+)")),
    ("Safari", re.compile(r"Version/(\d+)[\d.]* .*Safari/")),
)
_UA_SYSTEMS = (
    ("Android", "Android"),
    ("iPhone", "iOS"),
    ("iPad", "iPadOS"),
    ("Windows", "Windows"),
    ("Mac OS X", "macOS"),
    ("Linux", "Linux"),
)
_UA_FALLBACK_LENGTH = 60


def device_label(user_agent: str | None) -> str:
    """«Chrome 129 · Windows» kimi qısa etiket; tanınmayan agent kəsilmiş xam mətndir."""
    text = (user_agent or "").strip()
    if not text:
        return ""
    system = next((label for token, label in _UA_SYSTEMS if token in text), "")
    for label, pattern in _UA_BROWSERS:
        match = pattern.search(text)
        if match:
            browser = f"{label} {match.group(1)}"
            return f"{browser} · {system}" if system else browser
    return text if len(text) <= _UA_FALLBACK_LENGTH else text[: _UA_FALLBACK_LENGTH - 1] + "…"


def _viewer_allowed(request) -> bool:
    """ƏSL istifadəçi arxiv baxıcısıdırmı (superadmin / RİM) — view-as təşkilatında."""
    from apps.organizations.models import Organization

    from .view_as import _active_memberships, actor_can_view_archived, get_view_as_state

    real_user = getattr(request, "real_user", None)
    if real_user is None or not getattr(real_user, "is_authenticated", False):
        return False
    state = get_view_as_state(request) or {}
    with bypass_rls():
        organization = Organization.objects.filter(pk=state.get("org_id")).first() if state.get("org_id") else None
    if organization is None:
        return False
    return actor_can_view_archived(real_user, _active_memberships(real_user, organization))


def _kind_label(action: str) -> str:
    if action == AuditAction.LOGIN:
        return pgettext(_CTX, "Giriş")
    return pgettext(_CTX, "Çıxış")


def login_history_for_view_as(request, *, limit: int = HISTORY_LIMIT):
    """Panel konteksti və ya ``None`` (qapı bağlıdır — panel render olunmur).

    Qaytarır: ``{"rows": [{when, kind, kind_label, ip, device}], "last_login": str, "limit": int}``.
    """
    if not getattr(request, "is_view_as", False):
        return None
    target = getattr(request, "view_as_target", None) or getattr(request, "user", None)
    if target is None or not getattr(target, "pk", None) or not _viewer_allowed(request):
        return None

    from apps.audit.models import AuditLog

    with bypass_rls():
        logs = list(
            AuditLog.objects.filter(user_id=target.pk, action__in=(AuditAction.LOGIN, AuditAction.LOGOUT))
            .only("action", "created_at", "ip_address", "user_agent")
            .order_by("-created_at")[: max(1, int(limit))]
        )
    rows = [
        {
            "when": timezone.localtime(log.created_at).strftime("%d.%m.%Y %H:%M"),
            "kind": log.action,
            "kind_label": _kind_label(log.action),
            "ip": log.ip_address or "",
            "device": device_label(log.user_agent),
        }
        for log in logs
    ]
    last_login = getattr(target, "last_login", None)
    return {
        "rows": rows,
        "last_login": timezone.localtime(last_login).strftime("%d.%m.%Y %H:%M") if last_login else "",
        "limit": limit,
    }


__all__ = ["HISTORY_LIMIT", "device_label", "login_history_for_view_as"]
