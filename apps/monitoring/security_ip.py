"""«Təhlükəsizlik» tabının IP filtri (sahib 2026-10-05).

Sahib bir IP ünvanını (və ya şəbəkəni) yazıb iki suala cavab görmək istəyir:

1. həmin IP-dən hansı təhlükəsizlik hadisələri gəlib (uğursuz / brute-force /
   superadmin girişləri…) — ``views.security_events_api`` mövcud cədvəli
   ``IpFilter.q()`` ilə daraldır;
2. həmin IP-dən KİM UĞURLA daxil olub — ``apps.audit.signals.log_user_login``
   hər girişi ``AuditLog(action=login, ip_address, user, user_agent)`` kimi yazır;
   ``successful_logins`` onları (IP, hesab, cihaz) üzrə qruplaşdırıb qaytarır.

Doğrulama ``ipaddress`` ilədir: tək IP (IPv4/IPv6) və ya şəbəkə (``10.0.0.0/24``;
``strict=False`` — host bitləri sıfırlanır). Yararsız giriş ``InvalidIpFilter``
atır, API onu 400 JSON-a çevirir (heç vaxt 500 yox). Şəbəkə ORM ``__range``
(``BETWEEN``) ilə süzülür: PostgreSQL ``inet`` müqayisəsi ünvanı ədədi sıralayır,
ona görə xam SQL lazım deyil. ``inet`` olmayan bazada (lokal SQLite) mətn
müqayisəsi yanlış olardı — orada şəbəkə filtri açıq mesajla rədd edilir.

Tenant əhatəsi: login sətirləri ``organization`` DAŞIMIR (platforma hadisəsidir,
RLS onları hər tenanta göstərir). Ona görə icazəli üzv (RİM rəhbəri) üçün açıq
ORM filtri qoyulur: yalnız ÖZ təşkilatının AKTİV üzvlərinin girişləri (+ həmin
təşkilata yazılmış sətirlər) — başqa tenantın istifadəçi adı sızmır. Superadmin
platforma görünüşündədir (dekorator ``bypass_rls()`` açır). Əhatə məlum deyilsə
FAIL-CLOSED: boş nəticə.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

from django.db import connection
from django.db.models import Count, Max, Min, Q
from django.utils.translation import pgettext

from core.constants import AuditAction

_CTX = "monitoring.security"

#: Ən uzun mənalı yazılış ``ffff:…:255.255.255.255/128`` 49 simvoldur — ehtiyatla 64.
IP_FILTER_MAX_LENGTH = 64
#: «Bu IP-dən uğurlu girişlər» blokunda ən çox bu qədər (IP, hesab, cihaz) qrupu.
LOGIN_GROUP_LIMIT = 50
#: Tam user-agent yalnız ipucu (title) üçündür — cavabı şişirtməsin.
USER_AGENT_MAX = 300
_UA_FALLBACK_LENGTH = 60

#: Sıra vacibdir: Edge/Opera/Samsung/Yandex agentində «Chrome/», Chrome-da «Safari/» da var.
_UA_BROWSERS = (
    ("Edge", re.compile(r"\bEdg(?:e|A|iOS)?/(\d+)")),
    ("Opera", re.compile(r"\b(?:OPR|OPiOS)/(\d+)")),
    ("Yandex", re.compile(r"\bYaBrowser/(\d+)")),
    ("Samsung Internet", re.compile(r"\bSamsungBrowser/(\d+)")),
    ("Firefox", re.compile(r"\b(?:Firefox|FxiOS)/(\d+)")),
    ("Chrome", re.compile(r"\b(?:Chrome|CriOS)/(\d+)")),
    ("Safari", re.compile(r"\bVersion/(\d+)[\w.]*(?: Mobile/\w+)? Safari/")),
)
#: Android agentində «Linux», iPhone agentində «like Mac OS X» da var — sıra vacibdir.
_UA_SYSTEMS = (
    ("Windows", "Windows"),
    ("Android", "Android"),
    ("iPhone", "iOS"),
    ("iPad", "iPadOS"),
    ("CrOS", "ChromeOS"),
    ("Macintosh", "macOS"),
    ("Linux", "Linux"),
)


class InvalidIpFilter(ValueError):
    """Daxil edilən IP / şəbəkə yararsızdır; mesaj (tərcümə olunmuş) UI-a gedir."""


def _address_text(address) -> str:
    # Python 3.11 IPv4-mapped ünvanı «::ffff:102:304» yazır; PostgreSQL və Django
    # «::ffff:1.2.3.4» qaytarır — UI-dakı aktiv IP müqayisəsi tutsun deyə eyni formada.
    mapped = getattr(address, "ipv4_mapped", None)
    return f"::ffff:{mapped}" if mapped else str(address)


@dataclass(frozen=True)
class IpFilter:
    """Doğrulanmış filtr: ``query`` — istifadəçinin yazdığı, ``network`` — normallaşdırılmış."""

    query: str
    network: ipaddress.IPv4Network | ipaddress.IPv6Network

    @property
    def is_network(self) -> bool:
        return self.network.num_addresses > 1

    @property
    def normalized(self) -> str:
        return str(self.network) if self.is_network else _address_text(self.network.network_address)

    def q(self, field: str = "ip_address") -> Q:
        """``GenericIPAddressField`` üçün şərt: tək IP — bərabərlik, şəbəkə — ``inet`` aralığı."""
        if not self.is_network:
            return Q(**{field: self.normalized})
        bounds = (_address_text(self.network.network_address), _address_text(self.network.broadcast_address))
        return Q(**{f"{field}__range": bounds})

    def as_dict(self) -> dict:
        return {
            "query": self.query,
            "normalized": self.normalized,
            "kind": "network" if self.is_network else "address",
        }


def _invalid() -> InvalidIpFilter:
    return InvalidIpFilter(
        pgettext(
            _CTX,
            "IP ünvanı düzgün deyil. Tək IP (məs. 192.168.1.10) və ya şəbəkə (məs. 10.0.0.0/24) daxil edin.",
        )
    )


def parse_ip_filter(raw: str | None) -> IpFilter | None:
    """``?ip=`` dəyərini doğrula; boşdursa ``None``, yararsızdırsa ``InvalidIpFilter``."""
    text = (raw or "").strip()
    if not text:
        return None
    # «%» — IPv6 zona identifikatoru (``fe80::1%eth0``): ``inet`` onu saxlamır.
    if len(text) > IP_FILTER_MAX_LENGTH or "%" in text:
        raise _invalid()
    try:
        network = ipaddress.ip_network(text, strict=False)
    except ValueError:
        raise _invalid() from None
    ip_filter = IpFilter(query=text, network=network)
    if ip_filter.is_network and connection.vendor != "postgresql":
        raise InvalidIpFilter(pgettext(_CTX, "Şəbəkə (CIDR) filtri bu bazada dəstəklənmir — tək IP ünvanı daxil edin."))
    return ip_filter


def short_user_agent(user_agent: str | None) -> str:
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


def successful_logins(scope, ip_filter: IpFilter, *, limit: int = LOGIN_GROUP_LIMIT) -> dict:
    """Filtrə uyğun UĞURLU girişlər — (IP, hesab, cihaz) qrupları, ən yenisi əvvəl (2 sorğu).

    ``scope`` — ``permissions.MonitoringScope``; platforma deyilsə yalnız öz
    təşkilatının aktiv üzvləri (modul docstring-inə bax).
    """
    from apps.audit.models import AuditLog

    platform = bool(scope is not None and scope.platform)
    result = {"items": [], "total": 0, "accounts": 0, "limit": limit, "truncated": False, "org_scoped": not platform}
    queryset = AuditLog.objects.filter(ip_filter.q(), action=AuditAction.LOGIN)
    if not platform:
        organization_id = getattr(scope, "organization_id", None)
        if not organization_id:
            return result
        from apps.organizations.models import Membership

        members = Membership.objects.filter(organization_id=organization_id, is_active=True).values("user_id")
        queryset = queryset.filter(
            Q(organization_id=organization_id) | Q(organization_id__isnull=True, user_id__in=members)
        )

    totals = queryset.aggregate(total=Count("id"), accounts=Count("user_id", distinct=True))
    if not totals["total"]:
        return result
    groups = list(
        queryset.values("ip_address", "user_agent", "user_id", "user__username", "user__first_name", "user__last_name")
        .annotate(count=Count("id"), first_seen=Min("created_at"), last_seen=Max("created_at"))
        .order_by("-last_seen", "user__username")[: limit + 1]
    )
    result.update(
        total=int(totals["total"]),
        accounts=int(totals["accounts"] or 0),
        truncated=len(groups) > limit,
        items=[
            {
                "ip": group["ip_address"] or "",
                "user": group["user__username"] or None,
                "full_name": f"{group['user__first_name'] or ''} {group['user__last_name'] or ''}".strip(),
                "user_agent": (group["user_agent"] or "")[:USER_AGENT_MAX],
                "device": short_user_agent(group["user_agent"]),
                "count": group["count"],
                "first_seen": group["first_seen"].isoformat(),
                "last_seen": group["last_seen"].isoformat(),
            }
            for group in groups[:limit]
        ],
    )
    return result


__all__ = [
    "IP_FILTER_MAX_LENGTH",
    "LOGIN_GROUP_LIMIT",
    "InvalidIpFilter",
    "IpFilter",
    "parse_ip_filter",
    "short_user_agent",
    "successful_logins",
]
