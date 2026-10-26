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
* ``/jurnal/`` (registrar — elektron jurnal): kənar zonadan HƏR KƏSƏ 403. 2026-10-25: «İmtahan balının
  daxil edilməsi» ekranı (:data:`EXAM_SCORE_PREFIXES` + ``?section=exam-score-entry``) eyni qaydadadır.
* İnzibati hesab (tələbə/müəllim ailəsindən KƏNAR hər hansı aktiv rol, org sahibi,
  superuser) — YALNIZ ``NETWORK_ZONE_STAFF_INTERNAL_ONLY=True`` olanda (sahib 2026-09-29: defolt
  söndürülüb, kənardan yalnız jurnal bağlıdır): kənar zonadan bütün səhifələr 403 — yalnız çıxış, statik/media,
  health/ping və giriş səhifəsinin özü açıqdır (istifadəçi «niyə» səhifəsini görüb
  çıxa bilsin).
* Superadmin — ``NETWORK_ZONE_SUPERADMIN_INTERNAL_ONLY=True`` (defolt AÇIQ, sahib 2026-10-05):
  kənar zonadan heç bir səhifə, giriş formasından keçən uğurlu giriş də dərhal ləğv edilir
  (sessiya bağlanır, 403). Yalnız çıxış açıqdır.
* Tələbə (student/lead_student) və yalnız-müəllim (teacher ailəsi) hesabları
  kənardan işləyir. Müəllim + inzibati rol = inzibati (sərt qayda üstündür).

Kənar qat (nginx) eyni iki qaydanı IP-yə görə TƏKRAR tətbiq edir (defense in depth):
`/jurnal/` və admin prefiksi (`/manage/`) external zonadan 403.
"""

from __future__ import annotations

import logging
import re

from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.template.response import TemplateResponse
from django.urls import reverse

from core.audit import log_action
from core.constants import AuditAction

# 2026-10-13 (gecə): zona hesabı shared kernel-ə (``core.network_zone``) köçürüldü — final/midterm
# imtahan qapısı (exams) da eyni qaydanı işlədir; adlar geriyə-uyğunluq üçün buradan ixrac olunur.
from core.network_zone import (  # noqa: F401
    ZONE_EXTERNAL,
    ZONE_HEADER,
    ZONE_INTERNAL,
    _internal_networks,
    request_network_zone,
    resolve_zone,
    zone_for_ip,
)
from core.utils import get_client_ip

from .models import ProfileRole

logger = logging.getLogger(__name__)

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

#: Publik sənəd yoxlaması (2026-10-18) — QR-ı skan edən hər kəs (işəgötürən, başqa universitet) kənardan açır.
#: Əməkdaş siyahısı (`/sened-yoxlamasi/`) QƏSDƏN bu prefiksdən kənardadır.
DOCUMENT_VERIFY_PREFIX = "/yoxla/"

#: Kənar zonada inzibati hesab üçün də açıq qalan yollar (prefiks).
_ALWAYS_OPEN_PREFIXES = ("/static/", "/media/", "/health/", "/ping/", "/i18n/", "/jsi18n/", DOCUMENT_VERIFY_PREFIX)


def _is_view_as(request) -> bool:
    return bool(getattr(request, "is_view_as", False) and getattr(request, "real_user", None) is not None)


def gate_actor(request):
    """Qapının qiymətləndirdiyi hesab — view-as altında HƏDƏF deyil, ƏSL istifadəçi.

    Təhlükəsizlik auditi 2026-10-07 (AUTH-01): ``ViewAsMiddleware`` bu middleware-dən
    ƏVVƏL ``request.user``-i hədəflə əvəz edir. Qapı ``request.user``-ə baxanda
    daxildə başladılmış view-as sessiyası (superadmin və ya inzibati aktor) kənar
    zonadan işləməyə davam edirdi. Zona qaydası hesabın SAHİBİNƏ aiddir.
    """
    if _is_view_as(request):
        return request.real_user
    return getattr(request, "user", None)


def account_kind(request) -> str:
    """'anonymous' | 'student' | 'teacher' | 'staff' — aktiv üzvlüklərə görə (view-as altında aktor)."""
    user = gate_actor(request)
    if user is None or not getattr(user, "is_authenticated", False):
        return "anonymous"
    # Audit 2026-09-28 SA-04: profil rolu ``superadmin`` olan hesab da staff-dır
    # (əvvəl yalnız ``is_superuser`` — belə hesab müəllim/tələbə sayılıb kənar
    # zonadan açıq qalırdı).
    from core.permissions import is_superadmin_user

    if is_superadmin_user(user):
        return "staff"
    organization = getattr(request, "organization", None)
    if organization is not None and getattr(organization, "owner_id", None) == user.pk:
        return "staff"
    # View-as altında ``org_memberships`` HƏDƏFİN üzvlükləridir — aktorunkunu təzədən oxu.
    memberships = None if _is_view_as(request) else getattr(request, "org_memberships", None)
    if memberships is None:
        from core.rls import bypass_rls

        # Sorğu ``user`` ilə açıq süzülür; RLS konteksti (view-as altında hədəfin org-u)
        # aktorun başqa org-dakı üzvlüyünü gizlədib onu «tələbə» kimi buraxmasın.
        with bypass_rls():
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


def _is_superadmin(request) -> bool:
    from core.permissions import is_superadmin_user

    return is_superadmin_user(gate_actor(request))


def _is_logout_path(path: str) -> bool:
    return path.startswith("/accounts/logout")


#: `/jurnal/` altında olan, amma elektron jurnal OLMAYAN şəxsi səhifələr — tələbə/müəllim
#: öz dərs cədvəlini və transkriptini kənardan da görür (sahib 2026-09-25:
#: «kənardan elektron jurnala girmək olmasın, başqa şeylərə olar»). Yalnız DƏQİQ yol;
#: nginx `docker/nginx/nginx.conf`-da eyni siyahı saxlanır. URL auditi A11 (2026-10-10):
#: `teqvim/` (təqvim kabinetdədir) və `cedvel/export.ics` (iCal ləğv edildi) silindi.
JOURNAL_EXTERNAL_OPEN_PATHS = frozenset({"/jurnal/cedvel/", "/jurnal/transkript.pdf"})
#: Sahib 2026-10-26: tələbə kabinetindəki «Sillabus (təsdiqlənmiş)» kənardan açılmırdı («universitet şəbəkəsi»).
#: Təsdiqlənmiş sillabusun OXUNUŞU jurnal deyil — view özü icazəni (qeydiyyat / müəllim) fail-closed yoxlayır.
JOURNAL_EXTERNAL_OPEN_RE = re.compile(r"^/jurnal/[0-9a-f-]{36}/sillabus\.(pdf|json)$")


#: Sahib 2026-10-25: «İmtahan balının daxil edilməsi» ekranı və onun API-ləri (forma, qaralama, fayl idxalı,
#: «Dəyişən nəticələr» CSV-si, bölmə fraqmenti) elektron jurnal kimi YALNIZ universitet şəbəkəsində işləyir.
#: Kabinetin tam səhifəsi (``/accounts/profile/?section=exam-score-entry``) sorğu parametri ilə tanınır.
EXAM_SCORE_PREFIXES = ("/accounts/imtahan-bali/", "/accounts/profile/api/sections/exam-score-entry/")
EXAM_SCORE_SECTION = "exam-score-entry"


def _journal_path(path: str, section: str = "") -> bool:
    if path.startswith(EXAM_SCORE_PREFIXES):
        return True
    if section == EXAM_SCORE_SECTION and path.startswith("/accounts/profile"):
        return True
    if path in JOURNAL_EXTERNAL_OPEN_PATHS or JOURNAL_EXTERNAL_OPEN_RE.match(path):
        return False
    return path.startswith("/jurnal/")


REASON_JOURNAL = "journal_internal_only"
REASON_SUPERADMIN = "superadmin_internal_only"
REASON_STAFF = "staff_internal_only"


#: Sessiyada müvəqqəti superadmin istisnasının bitmə anı (epoch saniyə) — WS qapısı DB-siz oxuyur.
TEMP_SUPERUSER_SESSION_KEY = "nz_temp_superuser_until"


def _temporary_superuser_until(user):
    """``grant_temporary_superuser`` ilə verilmiş, müddəti bitməmiş girişin sonu (datetime) və ya ``None``.

    Sahib 2026-10-27: «superadmin kimi iş görə bilim, amma hər yerdən daxil ola bilim — evdəyəm». Yalnız
    MÜVƏQQƏTİ verilmiş giriş (audit sətri ``temporary_superuser`` / ``grant`` + ``expires_at``) şəbəkə zonası
    qaydasından azaddır; müddət bitəndə və ya ``--revoke`` ilə qayda avtomatik geri qayıdır. Daimi superadminə aid deyil.
    """
    if user is None or not getattr(user, "is_superuser", False) or not getattr(user, "pk", None):
        return None
    from datetime import datetime

    from django.apps import apps as django_apps
    from django.utils import timezone

    AuditLog = django_apps.get_model("audit", "AuditLog")
    row = (
        AuditLog.objects.filter(resource_type="temporary_superuser", resource_id=str(user.pk))
        .order_by("-created_at")
        .values_list("changes", flat=True)
        .first()
    )
    if not isinstance(row, dict) or row.get("operation") != "grant" or not row.get("expires_at"):
        return None
    try:
        until = datetime.fromisoformat(str(row["expires_at"]))
    except ValueError:
        return None
    return until if until > timezone.now() else None


def temporary_superuser_exempt(request) -> bool:
    """HTTP: müvəqqəti superadmin girişi aktivdirsə ``True`` (nəticə sessiyada saxlanır — WS qapısı üçün)."""
    user = gate_actor(request)  # view-as altında ƏSL hesab
    if user is None or not getattr(user, "is_authenticated", False) or not getattr(user, "is_superuser", False):
        return False
    until = _temporary_superuser_until(user)
    session = getattr(request, "session", None)
    if session is not None:
        if until is None:
            session.pop(TEMP_SUPERUSER_SESSION_KEY, None)
        else:
            session[TEMP_SUPERUSER_SESSION_KEY] = until.timestamp()
    return until is not None


def _superadmin_gate_enabled() -> bool:
    return bool(getattr(settings, "NETWORK_ZONE_SUPERADMIN_INTERNAL_ONLY", True))


def zone_policy_denial(*, zone: str, path: str, is_superadmin, account_kind_of, section: str = ""):
    """ŞƏBƏKƏ ZONASI qaydası — HTTP middleware-i və WebSocket qapısı üçün TƏK mənbə.

    Təhlükəsizlik dizaynı 2026-10-08: əvvəl qayda yalnız ``NetworkZoneMiddleware.__call__``-
    da idi və WebSocket qoşulmaları (``/ws/…``) ondan heç keçmirdi. İndi hər iki nəqliyyat
    bu funksiyanı çağırır — qaydalar ayrı-ayrı yazılıb bir-birindən uzaqlaşa bilməz.

    ``is_superadmin`` / ``account_kind_of`` — tənbəl (lazy) çağırışlar: yalnız qayda onlara
    çatanda hesablanır (daxili zonada və ya enforce söndürüləndə heç biri çağırılmır).
    Hər ikisi zona qaydasının aid olduğu ƏSL hesabı (view-as altında aktoru) qiymətləndirir.

    ``section`` — kabinetin ``?section=`` parametri (HTTP; «İmtahan balının daxil edilməsi» bölməsi, 2026-10-25).

    Qaytarır: ``(reason, account_kind)`` rədd üçün, keçidə ``None``.
    """
    if not getattr(settings, "NETWORK_ZONE_ENFORCED", False) or zone == ZONE_INTERNAL:
        return None
    if _journal_path(path, section):
        return REASON_JOURNAL, account_kind_of()
    if _superadmin_gate_enabled() and not _is_logout_path(path) and is_superadmin():
        return REASON_SUPERADMIN, "staff"
    # Sahib 2026-09-29: inzibati hesabların daxili-şəbəkə məhdudiyyəti ayarla idarə olunur (defolt söndürülüb).
    if getattr(settings, "NETWORK_ZONE_STAFF_INTERNAL_ONLY", False):
        kind = account_kind_of()
        if kind == "staff" and not _is_open_path(path):
            return REASON_STAFF, kind
    return None


class _HttpGateFacts:
    """HTTP sorğusu üçün tənbəl faktlar — hesablanan dəyər sessiyaya yazılır (WS qapısı oxuyur)."""

    def __init__(self, request):
        self.request = request

    def superadmin(self) -> bool:
        from core.access_facts import FACT_SUPERADMIN, remember_access_facts

        value = _is_superadmin(self.request)
        remember_access_facts(self.request, gate_actor(self.request), **{FACT_SUPERADMIN: value})
        return value

    def kind(self) -> str:
        from core.access_facts import FACT_ACCOUNT_KIND, remember_access_facts

        value = account_kind(self.request)
        remember_access_facts(self.request, gate_actor(self.request), **{FACT_ACCOUNT_KIND: value})
        return value


def log_zone_denial(request, *, reason: str, kind: str, transport: str = "http") -> None:
    """Zona rəddinin logu + audit sətri — HTTP və WebSocket üçün eyni format."""
    client_ip = get_client_ip(request) or ""
    method = getattr(request, "method", "") or ""
    logger.warning(
        "network_zone: %s — %s %s ip=%s kind=%s transport=%s", reason, method, request.path, client_ip, kind, transport
    )
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


class NetworkZoneMiddleware:
    """`OrganizationMiddleware`-dən SONRA durur (rol/üzvlük hazırdır)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        zone = resolve_zone(request)
        request.network_zone = zone
        if not getattr(settings, "NETWORK_ZONE_ENFORCED", False) or zone == ZONE_INTERNAL:
            return self.get_response(request)

        if temporary_superuser_exempt(request):
            return self.get_response(request)
        path = request.path_info
        facts = _HttpGateFacts(request)
        denial = zone_policy_denial(
            zone=zone,
            path=path,
            is_superadmin=facts.superadmin,
            account_kind_of=facts.kind,
            section=(request.GET.get("section") or "").strip(),
        )
        if denial is not None:
            reason, kind = denial
            if reason == REASON_SUPERADMIN:
                return self._deny_superadmin(request)
            return self._deny(request, reason=reason, kind=kind)
        response = self.get_response(request)
        # Sahib 2026-10-05: superadmin YALNIZ universitet şəbəkəsindən. Giriş formaları
        # (və OTP addımları) açıq yoldur — bu sorğuda login() superadmin sessiyası
        # açıbsa, kənar zonada həmin sessiya dərhal ləğv edilir.
        if _superadmin_gate_enabled() and _is_superadmin(request) and not _is_logout_path(path):
            return self._deny_superadmin(request)
        return response

    def _deny_superadmin(self, request):
        from django.contrib.auth import logout

        logout(request)
        return self._deny(request, reason=REASON_SUPERADMIN, kind="staff")

    def _deny(self, request, *, reason: str, kind: str):
        log_zone_denial(request, reason=reason, kind=kind)
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
