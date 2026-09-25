"""ŞƏBƏKƏ ZONASI qapısı — publik domenə çıxış (sahib 2026-09-21).

Qayda (sahibin sözü ilə): «tələbə publik üzərindən giriş edə bilsin; müəllim
elektron jurnaldan başqa bütün özünə aid hissələrə girsin; elektron jurnal
universitet daxilində müəllim üçün aktiv olsun; inzibati işçilər yalnız və
yalnız universitet daxilində giriş edə bilsinlər».

Zona necə tapılır
-----------------
* nginx (`geo $ems_zone`) real müştəri IP-sinə görə ``X-EMS-Zone: internal|external``
  başlığını qoyur və müştəridən gələn eyni adlı başlığı ƏZİR. Django bu başlığa
  YALNIZ ``NETWORK_ZONE_TRUST_HEADER=True`` olanda inanır (prod .env).
* Başlıq yoxdursa/etibarlı deyilsə zona ``get_client_ip`` (sağdan etibarlı proxy)
  ilə ``INTERNAL_NETWORKS`` CIDR siyahısına görə hesablanır.

Nə bloklanır (``NETWORK_ZONE_ENFORCED=True`` olanda; defolt False — LAN
yerləşdirməsi dəyişmir)
-------------------------
* ``/jurnal/`` (registrar — elektron jurnal): kənar zonadan HƏR KƏSƏ 403.
* İnzibati hesab (tələbə/müəllim ailəsindən KƏNAR hər hansı aktiv rol, org sahibi,
  superuser): kənar zonadan bütün səhifələr 403 — yalnız çıxış, statik/media,
  health/ping və giriş səhifəsinin özü açıqdır (istifadəçi «niyə» səhifəsini görüb
  çıxa bilsin).
* Tələbə (student/lead_student) və yalnız-müəllim (teacher ailəsi) hesabları
  kənardan işləyir. Müəllim + inzibati rol = inzibati (sərt qayda üstündür).

Kənar qat (nginx) eyni iki qaydanı IP-yə görə TƏKRAR tətbiq edir (defense in depth):
`/jurnal/` və admin prefiksi (`/manage/`) external zonadan 403.
"""

from __future__ import annotations

import ipaddress
import logging

from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.template.response import TemplateResponse
from django.urls import reverse

from core.audit import log_action
from core.constants import AuditAction
from core.utils import get_client_ip

from .models import ProfileRole

logger = logging.getLogger(__name__)

ZONE_INTERNAL = "internal"
ZONE_EXTERNAL = "external"
ZONE_HEADER = "HTTP_X_EMS_ZONE"

#: Kənardan da işləyən rollar. Qalan HƏR ŞEY inzibati sayılır (fail-closed).
STUDENT_ROLE_NAMES = frozenset({ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT, "alumni"})
TEACHER_ROLE_NAMES = frozenset(
    {
        ProfileRole.TEACHER,
        ProfileRole.ASSISTANT_TEACHER,
        "instructor",
        "professor",
        "associate_professor",
        "assistant",
        "lab_assistant",
    }
)
#: Rolsuz adi üzv — publik səthdən başqa heç nə görmür; kənardan bloklamağa dəyməz.
NEUTRAL_ROLE_NAMES = frozenset({ProfileRole.MEMBER})

#: Kənar zonada inzibati hesab üçün də açıq qalan yollar (prefiks).
_ALWAYS_OPEN_PREFIXES = ("/static/", "/media/", "/health/", "/ping/", "/i18n/", "/jsi18n/")


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


def account_kind(request) -> str:
    """'anonymous' | 'student' | 'teacher' | 'staff' — aktiv üzvlüklərə görə."""
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return "anonymous"
    if getattr(user, "is_superuser", False):
        return "staff"
    organization = getattr(request, "organization", None)
    if organization is not None and getattr(organization, "owner_id", None) == user.pk:
        return "staff"
    memberships = getattr(request, "org_memberships", None)
    if memberships is None:
        memberships = list(user.memberships.filter(is_active=True).select_related("role"))
    names = set()
    for membership in memberships:
        raw = getattr(getattr(membership, "role", None), "name", "") or ""
        if raw:
            names.add(ProfileRole.normalize_membership_role_name(raw))
    names -= NEUTRAL_ROLE_NAMES
    if not names:
        return "student"  # rolsuz/üzvlüksüz hesab — publik səthdən başqa heç nə yoxdur
    if names <= (STUDENT_ROLE_NAMES | TEACHER_ROLE_NAMES):
        return "teacher" if names & TEACHER_ROLE_NAMES else "student"
    return "staff"


def _is_open_path(path: str) -> bool:
    if path.startswith(_ALWAYS_OPEN_PREFIXES):
        return True
    try:
        if path == reverse("accounts:logout") or path == reverse("accounts:login"):
            return True
    except Exception:  # noqa: BLE001 — url adı yoxdursa açıq sayma
        pass
    return path.startswith("/accounts/login/") or path.startswith("/accounts/logout")


#: `/jurnal/` altında olan, amma elektron jurnal OLMAYAN şəxsi səhifələr — tələbə/müəllim
#: öz dərs cədvəlini, təqvimini və transkriptini kənardan da görür (sahib 2026-09-25:
#: «kənardan elektron jurnala girmək olmasın, başqa şeylərə olar»). Yalnız DƏQİQ yol;
#: nginx `docker/nginx/nginx.conf`-da eyni siyahı saxlanır.
JOURNAL_EXTERNAL_OPEN_PATHS = frozenset(
    {"/jurnal/cedvel/", "/jurnal/cedvel/export.ics", "/jurnal/teqvim/", "/jurnal/transkript.pdf"}
)


def _journal_path(path: str) -> bool:
    return path.startswith("/jurnal/") and path not in JOURNAL_EXTERNAL_OPEN_PATHS


class NetworkZoneMiddleware:
    """`OrganizationMiddleware`-dən SONRA durur (rol/üzvlük hazırdır)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        zone = resolve_zone(request)
        request.network_zone = zone
        if not getattr(settings, "NETWORK_ZONE_ENFORCED", False) or zone == ZONE_INTERNAL:
            return self.get_response(request)

        path = request.path_info
        if _journal_path(path):
            return self._deny(request, reason="journal_internal_only", kind=account_kind(request))
        kind = account_kind(request)
        if kind == "staff" and not _is_open_path(path):
            return self._deny(request, reason="staff_internal_only", kind=kind)
        return self.get_response(request)

    def _deny(self, request, *, reason: str, kind: str):
        client_ip = get_client_ip(request) or ""
        logger.warning("network_zone: %s — %s %s ip=%s kind=%s", reason, request.method, request.path, client_ip, kind)
        try:
            log_action(
                action=AuditAction.DENY,
                reason=f"network_zone: {reason}",
                request=request,
                resource_type="network_zone_deny",
                resource_id=client_ip,
                resource_repr=request.path[:200],
            )
        except Exception:  # noqa: BLE001 — audit heç vaxt cavabı sındırmasın
            logger.exception("network_zone: audit yazılmadı")
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.path.startswith("/api/"):
            return JsonResponse({"detail": "network_zone_denied", "reason": reason}, status=403)
        try:
            response = TemplateResponse(
                request,
                "errors/network_zone.html",
                {"zone_reason": reason, "account_kind": kind},
                status=403,
            )
            response.render()
            return response
        except Exception:  # noqa: BLE001 — şablon yoxdursa sadə 403
            logger.exception("network_zone: şablon render olunmadı")
            return HttpResponseForbidden("Bu bölmə yalnız universitet şəbəkəsindən açılır.")
