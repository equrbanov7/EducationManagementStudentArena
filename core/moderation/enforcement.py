"""Ad moderasiyası — tətbiq nöqtələri üçün yoxlama + audit izi + rate-limit (2026-09-30).

Sahib tələbi (2026-09-30): «ad qoyulan hər yerdə nalayiq söz / ifadə yazılsa —
tut, blokla və kimin etdiyini (IP, vaxt, yer) jurnala yaz».

``screen_names(request, {sahə: dəyər, …}, …)`` çağıran view / servis üçün tək
giriş nöqtəsidir:

* dəyər təmizdirsə ``None`` qaytarır (heç nə yazılmır);
* nalayiq ifadə varsa — mövcud audit jurnalına (``core.audit.log_action``,
  ``action=deny``, ``resource_type="moderation.profanity_blocked"``) qeyd yazır
  və tərcümə olunmuş, sözü TƏKRARLAMAYAN ``NameRejection`` qaytarır;
* eyni aktorun (istifadəçi → canlı imtahan klienti → IP) təkrar cəhdləri
  ``core.rate_limit`` ilə məhdudlaşır: limit dolanda həmin aktorun ad
  dəyişikliyi pəncərə bitənə qədər 429 alır (filtri «sınaqla» keçmə cəhdi
  yavaşlayır). Aktor IP deyil, istifadəçi / klient səviyyəsindədir — sinfin
  ortaq NAT IP-si bir tələbənin ucbatından bütün sinfi bloklamasın;
* IP başına ayrıca tavan yalnız AUDİT YAZISINI məhdudlaşdırır (cookie silib
  jurnalı «daşqın»la doldurmaq olmasın) — rədd cavabı yenə verilir.

Qeydə dəyərin özü YAZILMIR: yalnız maska («S*****»), uzunluq və HMAC izi
(eyni sözün təkrarlarını əlaqələndirmək üçün). IP / user-agent / request_id
``log_action`` tərəfindən (etibarlı ``core.utils.get_client_ip`` ilə) yazılır.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.apps import apps as django_apps
from django.conf import settings
from django.db import transaction
from django.utils.crypto import salted_hmac
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction
from core.rate_limit import is_rate_limited, record_rate_limit_hit
from core.utils import get_client_ip

from .detector import find_profanity, mask_value
from .normalize import canonical_text

logger = logging.getLogger(__name__)

#: Audit qeydinin resurs tipi — audit jurnalının «Nalayiq ad cəhdləri» filtri bununla süzür.
PROFANITY_RESOURCE_TYPE = "moderation.profanity_blocked"

ATTEMPT_SCOPE = "moderation.profanity"
IP_LOG_SCOPE = "moderation.profanity.ip_log"
#: Aktor başına: 10 dəqiqədə 5 nalayiq cəhd → pəncərənin sonuna qədər ad dəyişmək olmur.
DEFAULT_ATTEMPT_RATE = "5/10m"
#: IP başına audit yazısı tavanı (rədd yenə verilir, yalnız jurnal yazılmır).
DEFAULT_IP_LOG_RATE = "30/10m"

_CTX = "moderation.profanity"
_HMAC_SALT = "core.moderation.profanity.value"


def rejection_message() -> str:
    return pgettext(_CTX, "Bu ad qəbul edilmir: tərkibində nalayiq ifadə var. Zəhmət olmasa başqa ad yazın.")


def rate_limited_message() -> str:
    return pgettext(_CTX, "Çox sayda nalayiq ad cəhdi edildi. Bir neçə dəqiqədən sonra yenidən cəhd edin.")


@dataclass(frozen=True)
class NameRejection:
    """Rədd cavabı: ``field`` — sahə açarı, ``message`` — istifadəçiyə göstərilən mətn."""

    field: str
    message: str
    status: int = 400
    retry_after: int | None = None

    @property
    def rate_limited(self) -> bool:
        return self.status == 429

    @property
    def field_name(self) -> str:
        """Sahə açarının son hissəsi («accounts.profile.first_name» → «first_name»)."""
        return self.field.rsplit(".", 1)[-1]


def _attempt_rate() -> str:
    return getattr(settings, "PROFANITY_ATTEMPT_RATE_LIMIT", DEFAULT_ATTEMPT_RATE)


def _ip_log_rate() -> str:
    return getattr(settings, "PROFANITY_IP_LOG_RATE_LIMIT", DEFAULT_IP_LOG_RATE)


def _authenticated_user(request):
    user = getattr(request, "user", None)
    return user if user is not None and getattr(user, "is_authenticated", False) else None


def actor_key(request, client_id: str = "") -> str:
    """Rate-limit açarı: istifadəçi → canlı imtahan klienti → IP."""
    user = _authenticated_user(request)
    if user is not None:
        return f"user:{user.pk}"
    if client_id:
        return f"client:{client_id}"
    return f"ip:{get_client_ip(request) or 'unknown'}"


def value_digest(value) -> str:
    """Normallaşdırılmış dəyərin HMAC-SHA256 izi (``SECRET_KEY`` ilə; dəyər geri açılmır)."""
    normalized = " ".join(canonical_text(value).split())
    return salted_hmac(_HMAC_SALT, normalized, algorithm="sha256").hexdigest()


def _resolve_organization(request, organization, organization_id):
    if organization is not None:
        return organization
    if organization_id:
        from core.rls import bypass_rls

        with bypass_rls():
            return django_apps.get_model("organizations", "Organization").objects.filter(pk=organization_id).first()
    return getattr(request, "organization", None) if request is not None else None


def _request_bits(request) -> dict:
    if request is None:
        return {}
    match = getattr(request, "resolver_match", None)
    return {
        "path": str(getattr(request, "path", "") or "")[:300],
        "method": str(getattr(request, "method", "") or ""),
        "view": str(getattr(match, "view_name", "") or "") if match is not None else "",
    }


def _audit_allowed_for_ip(request) -> bool:
    if request is None:
        return True
    limited, _retry = record_rate_limit_hit(IP_LOG_SCOPE, _ip_log_rate(), f"ip:{get_client_ip(request) or 'unknown'}")
    return not limited


def _record_attempt(request, *, user, field, value, match, organization, target, client_id, context, lock_engaged):
    user = user or _authenticated_user(request)
    details = {
        "field": field,
        "value_masked": mask_value(value),
        "value_length": len(str(value)),
        "value_hmac": value_digest(value),
        "language": match.language,
        "rule": match.kind,
        "term_masked": mask_value(match.term.strip("=*")),
        "anonymous": user is None,
        "live_client_id": str(client_id or "")[:64],
        "lock_engaged": bool(lock_engaged),
        **_request_bits(request),
    }
    if target is not None:
        details["target_id"] = str(getattr(target, "pk", "") or "")
    for key, extra in (context or {}).items():
        details[str(key)] = extra if isinstance(extra, (bool, int)) else str(extra)[:200]
    logger.warning(
        "moderation: nalayiq ad bloklandı field=%s lang=%s rule=%s user=%s client=%s",
        field,
        match.language,
        match.kind,
        getattr(user, "pk", None),
        details["live_client_id"] or "-",
    )
    if not _audit_allowed_for_ip(request):
        return
    try:
        # Savepoint: audit yazısı uğursuz olsa belə rədd cavabı verilir və
        # çağıranın (ATOMIC_REQUESTS) transaksiyası zədələnmir.
        with transaction.atomic():
            log_action(
                action=AuditAction.DENY,
                user=user,
                organization=organization,
                reason=f"Nalayiq ifadə bloklandı: {field}",
                request=request,
                resource_type=PROFANITY_RESOURCE_TYPE,
                resource_id=details.get("target_id", ""),
                resource_repr=field[:500],
                new_values=details,
            )
    except Exception:  # noqa: BLE001 — audit xətası moderasiyanı söndürməməlidir
        logger.exception("moderation: audit qeydi yazılmadı (field=%s)", field)


def screen_names(
    request,
    values,
    *,
    organization=None,
    organization_id=None,
    target=None,
    client_id: str = "",
    context: dict | None = None,
    user=None,
) -> NameRejection | None:
    """Ad sahələrini yoxlayır; ilk nalayiq sahə üçün audit qeydi yazıb rədd qaytarır.

    Args:
        values: ``{sahə açarı: dəyər}`` — açar audit-də «harada» sualına cavabdır
            (məs. ``"live_exam.join.nickname"``, ``"accounts.profile.first_name"``).
        organization / organization_id: qeydin təşkilatı (verilməyibsə ``request.organization``).
        target: adı dəyişən obyekt (məs. RİM-in redaktə etdiyi istifadəçi).
        client_id: anonim canlı imtahan klientinin ``live_client_id``-si.
        context: qeydə əlavə sahələr (sessiya id-si və s.).
        user: icraçı — ``request`` olmayan servis çağırışında (məs. RİM) açıq verilir.
    """
    items = [(str(field), str(value)) for field, value in dict(values or {}).items() if str(value or "").strip()]
    if not items:
        return None
    if user is not None and getattr(user, "is_authenticated", False):
        key = f"user:{user.pk}"
    else:
        user = None
        key = actor_key(request, client_id) if request is not None else ""
    if key.startswith("ip:"):
        # Təhlükəsizlik baxışı 2026-09-30 (M6): klient kukisi olmayan qoşulmada açar sinfin
        # ortaq NAT IP-si olardı — kilid bütün sinfi bağlayardı. Belə cəhd yalnız rədd + jurnal.
        key = ""
    rate = _attempt_rate()
    for field, value in items:
        match = find_profanity(value)
        if match is None:
            # Təmiz ad HƏMİŞƏ keçir — kilid yalnız təkrarlanan NALAYİQ cəhdləri dayandırır
            # (yanlış pozitivə düşən real tələbə canlı imtahana 10 dəqiqə bağlanmasın).
            continue
        if key:
            limited, retry_after = is_rate_limited(ATTEMPT_SCOPE, rate, key)
            if limited:
                return NameRejection(field=field, message=rate_limited_message(), status=429, retry_after=retry_after)
        lock_engaged = False
        if key:
            record_rate_limit_hit(ATTEMPT_SCOPE, rate, key)
            lock_engaged, _retry = is_rate_limited(ATTEMPT_SCOPE, rate, key)
        _record_attempt(
            request,
            user=user,
            field=field,
            value=value,
            match=match,
            organization=_resolve_organization(request, organization, organization_id),
            target=target,
            client_id=client_id,
            context=context,
            lock_engaged=lock_engaged,
        )
        return NameRejection(field=field, message=rejection_message())
    return None


def screen_name(request, field: str, value, **kwargs) -> NameRejection | None:
    """Tək sahə üçün ``screen_names`` qısayolu."""
    return screen_names(request, {field: value}, **kwargs)


__all__ = [
    "ATTEMPT_SCOPE",
    "DEFAULT_ATTEMPT_RATE",
    "DEFAULT_IP_LOG_RATE",
    "IP_LOG_SCOPE",
    "PROFANITY_RESOURCE_TYPE",
    "NameRejection",
    "actor_key",
    "rate_limited_message",
    "rejection_message",
    "screen_name",
    "screen_names",
    "value_digest",
]
