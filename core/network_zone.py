"""Şəbəkə zonası — sorğunun universitet daxili (``internal``) və ya kənar (``external``) olması.

2026-10-13 (gecə): zona hesabı ``apps/accounts/network_zone.py``-dan buraya (shared kernel)
köçürüldü, çünki final/midterm imtahan qapısı (``apps/exams/services/exam_network.py``) da
eyni qaydanı işlətməlidir, ``exams`` isə ``accounts``-u import edə bilməz (``accounts`` →
``exams`` kənarı var — dövr yaranardı). ``apps.accounts.network_zone`` adları buradan yenidən
ixrac edir; davranış dəyişmir.

Zona necə tapılır: nginx (``geo $ems_zone``) real müştəri IP-sinə görə ``X-EMS-Zone`` başlığını
qoyur və müştəridən gələn eyni adlı başlığı ƏZİR. Django ona YALNIZ
``NETWORK_ZONE_TRUST_HEADER=True`` olanda inanır; əks halda ``get_client_ip`` (sağdan etibarlı
proxy) ``INTERNAL_NETWORKS`` CIDR siyahısı ilə müqayisə olunur. Oxunmayan IP → ``external``
(fail-closed).
"""

from __future__ import annotations

import ipaddress
import logging

from django.conf import settings

from core.utils import get_client_ip

logger = logging.getLogger("accounts.network_zone")

ZONE_INTERNAL = "internal"
ZONE_EXTERNAL = "external"
ZONE_HEADER = "HTTP_X_EMS_ZONE"


def _internal_networks():
    out = []
    for raw in getattr(settings, "INTERNAL_NETWORKS", None) or []:
        raw = str(raw or "").strip()
        if not raw:
            continue
        try:
            out.append(ipaddress.ip_network(raw, strict=False))
        except ValueError:
            logger.warning("INTERNAL_NETWORKS girişi yanlış formatdadır, ötürülür: %r", raw)
    return out


def zone_for_ip(ip_text) -> str:
    """IP → zona. Oxunmayan IP fail-closed = external."""
    try:
        ip = ipaddress.ip_address(str(ip_text or "").strip())
    except ValueError:
        return ZONE_EXTERNAL
    for network in _internal_networks():
        if ip in network:
            return ZONE_INTERNAL
    return ZONE_EXTERNAL


def resolve_zone(request) -> str:
    """Sorğunun zonası — etibarlı nginx başlığı (opsional) və ya IP hesablaması."""
    if getattr(settings, "NETWORK_ZONE_TRUST_HEADER", False):
        header = (request.META.get(ZONE_HEADER) or "").strip().lower()
        if header in (ZONE_INTERNAL, ZONE_EXTERNAL):
            return header
    return zone_for_ip(get_client_ip(request) or request.META.get("REMOTE_ADDR"))


def request_network_zone(request) -> str:
    """``NetworkZoneMiddleware``-in sorğuya yazdığı zona; yoxdursa (WS/RequestFactory) yenidən hesablanır."""
    zone = getattr(request, "network_zone", None)
    if zone in (ZONE_INTERNAL, ZONE_EXTERNAL):
        return zone
    return resolve_zone(request)


__all__ = [
    "ZONE_EXTERNAL",
    "ZONE_HEADER",
    "ZONE_INTERNAL",
    "request_network_zone",
    "resolve_zone",
    "zone_for_ip",
]
