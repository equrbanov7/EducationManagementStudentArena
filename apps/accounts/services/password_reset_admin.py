"""«Parol sıfırlama» — operatorun başqa istifadəçiyə müvəqqəti parol verməsi (sahib, 2026-09-30).

Ssenari: parolunu unudan tələbə/müəllim RİM-ə gəlir. Operator istifadəçi adını
yazır, şəxsiyyəti təsdiqləyir, «Parolu sıfırla» düyməsini basır və ekranda BİR
DƏFƏ göstərilən müvəqqəti parolu istifadəçiyə verir. İlk girişdə
``FirstLoginPasswordMiddleware`` istifadəçini öz parolunu qurmağa məcbur edir.

İCAZƏ: `account.password_reset` (RİM rəhbəri default; digər rollara icazə
redaktorundan). Superadmin həmişə. Səlahiyyət qaydaları RİM mərkəzinin sınanmış
siyasət qatından (`services/rim/policy.py`) TƏKRAR İSTİFADƏ olunur — kopyalanmır:

* yalnız operatorun AKTİV təşkilatının üzvü (tenant izolyasiyası; superadmin
  aktiv təşkilat seçibsə o da həmin təşkilatla məhdudlaşır);
* superuser / profil-rolu superadmin hesabı HEÇ VAXT hədəf ola bilməz;
* öz hesabı yox (öz parolu «Parolu dəyiş» bölməsindən dəyişilir);
* ciddi iyerarxiya: hədəfin rol səviyyəsi operatorunkundan AŞAĞI olmalıdır
  (superadmin istisna); təşkilat sahibi yalnız superadmin tərəfindən;
* silinmiş / bloklanmış / girişi bağlı (arxiv, idxal mərhələsi) hesaba parol
  VERİLMİR — o parol onsuz da işləməz, operator isə «işləyir» zənn edərdi;
* başqasının adından baxış (view-as) sessiyası HEÇ BİR rejimdə istifadə edə bilməz.

TƏHLÜKƏSİZLİK (pozulmaz):

* Parol heç yerdə SAXLANILMIR və LOGLANMIR — nə DB-də (yalnız Django heşi), nə
  audit-də, nə log-da, nə keşdə. Çağırana yalnız bir dəfə qaytarılır.
* Parol dəyişikliyi Django-nun sessiya-heş mexanizmi ilə hədəfin BÜTÜN açıq
  sessiyalarını etibarsız edir (növbəti sorğuda çıxış).
* Hədəfin hesab-səviyyəli login rate-limit vedrələri təmizlənir — parolu
  unudub bir neçə dəfə səhv yazan istifadəçi yeni parolla dərhal girə bilsin.
* Audit: operator, hədəf, təşkilat, İP, user-agent, vaxt — parolsuz.
"""

from __future__ import annotations

import logging
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import pgettext

from apps.audit.public import log_action
from core.constants import AuditAction
from core.rate_limit import clear_rate_limit, normalize_rate_identity, record_rate_limit_hit
from core.utils import get_client_ip

from ..identity import user_access_is_login_blocked
from .rim.policy import (
    RimAccessError,
    RimActor,
    assert_can_manage,
    assert_no_foreign_authority,
    manageable_users_queryset,
    resolve_actor,
)

logger = logging.getLogger(__name__)
_CTX = "accounts.password_reset"

#: İcazə açarı (kataloq: `apps/organizations/permissions_account.py`).
PERM_PASSWORD_RESET = "account.password_reset"

#: Rate-limit vedrələri — operator (istifadəçi id) başına.
RESET_RATE_SCOPE = "account_password_reset"
LOOKUP_RATE_SCOPE = "account_password_reset_lookup"
DEFAULT_RESET_RATE = "30/1h"
DEFAULT_LOOKUP_RATE = "120/10m"

#: Oxunaqlı əlifba — qarışan simvollar (0/O/o, 1/l/I/i) YOXDUR: parol kağıza
#: yazılır və ya diktə olunur. 12 simvol × 54 hərf ≈ 69 bit — müvəqqəti parol
#: üçün kifayətdir (ilk girişdə dəyişdirilir).
_UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_LOWER = "abcdefghjkmnpqrstuvwxyz"
_DIGITS = "23456789"
TEMP_PASSWORD_LENGTH = 12
_MAX_GENERATION_ATTEMPTS = 12

#: `RimAccessError.reason_code` → bu modulun kodu (tenantdan kənar → «tapılmadı», mövcudluq sızmır).
_RIM_CODE_MAP = {
    "target_not_found": ("target_not_found", 404),
    "target_outside_organization": ("target_not_found", 404),
    "target_is_superadmin": ("target_is_superadmin", 403),
    "target_is_self": ("target_is_self", 403),
    "target_is_owner": ("target_is_owner", 403),
    "target_rank_too_high": ("target_rank_too_high", 403),
    "no_organization_context": ("no_organization_context", 403),
    "permission_denied": ("permission_denied", 403),
}


def error_message(code: str) -> str:
    """Kod → istifadəçiyə göstərilən (tərcümə olunan) mətn."""
    messages = {
        "permission_denied": pgettext(_CTX, "Parol sıfırlamaq üçün icazəniz yoxdur."),
        "view_as_forbidden": pgettext(
            _CTX, "Başqasının adından baxış rejimində parol sıfırlamaq olmaz. Əvvəlcə baxış rejimindən çıxın."
        ),
        "organization_pending": pgettext(_CTX, "Təşkilatınız hələ təsdiqlənməyib — parol sıfırlamaq olmaz."),
        "no_organization_context": pgettext(_CTX, "Aktiv təşkilat seçilməyib."),
        "target_required": pgettext(_CTX, "İstifadəçi seçilməyib."),
        "target_not_found": pgettext(_CTX, "İstifadəçi tapılmadı."),
        "target_is_superadmin": pgettext(_CTX, "Superadmin hesabının parolu bu bölmədən sıfırlana bilməz."),
        "target_is_self": pgettext(
            _CTX, "Öz parolunuzu bu bölmədən sıfırlaya bilməzsiniz — «Parolu dəyiş» bölməsindən istifadə edin."
        ),
        "target_is_owner": pgettext(_CTX, "Təşkilat sahibinin parolunu yalnız superadmin sıfırlaya bilər."),
        "target_rank_too_high": pgettext(
            _CTX, "Özünüzlə eyni və ya daha yüksək səlahiyyətli istifadəçinin parolunu sıfırlaya bilməzsiniz."
        ),
        "target_deleted": pgettext(_CTX, "Hesab silinib — əvvəlcə RİM mərkəzindən bərpa olunmalıdır."),
        "target_blocked": pgettext(_CTX, "Hesab bloklanıb — əvvəlcə RİM mərkəzindən blokdan çıxarılmalıdır."),
        "target_login_closed": pgettext(
            _CTX, "Bu hesabla sistemə giriş bağlıdır (məzun/xaric arxivi və ya tamamlanmamış idxal)."
        ),
        "rate_limited": pgettext(_CTX, "Çox sayda sorğu göndərildi. Bir az sonra yenidən cəhd edin."),
        "query_too_short": pgettext(_CTX, "Ən azı 2 simvol daxil edin."),
        "password_generation_failed": pgettext(_CTX, "Parol yaradıla bilmədi. Yenidən cəhd edin."),
    }
    return messages.get(code) or messages["permission_denied"]


class PasswordResetError(Exception):
    """Əməliyyat rədd edildi. ``code`` maşın-oxunaqlı, ``message`` tərcümə olunmuş mətndir."""

    # Bütün arqumentlər `super().__init__()`-ə ötürülür (pickle/copy — flake8-bugbear B042).
    def __init__(self, code: str, status: int = 403):
        super().__init__(code, status)
        self.code = code
        self.status = status

    @property
    def message(self) -> str:
        return error_message(self.code)

    def __str__(self):
        return self.code


def _from_rim_error(exc: RimAccessError) -> PasswordResetError:
    code, status = _RIM_CODE_MAP.get(exc.reason_code, ("permission_denied", 403))
    return PasswordResetError(code, status)


# ---------------------------------------------------------------------------
# Operator və əhatə
# ---------------------------------------------------------------------------


def operator_for(request, *, for_write: bool = False) -> RimActor:
    """Sorğunun operatorunu həll edir; icazə yoxdursa ``PasswordResetError``.

    View-as yoxlaması HƏR İKİ endpoint-də (axtarış daxil) edilir: FULL rejimdə
    middleware yazmanı buraxır, amma hesab ələ keçirmə yolu olduğundan bu əməl
    heç bir rejimdə baxış sessiyasından işləməməlidir.
    """
    if getattr(request, "is_view_as", False):
        raise PasswordResetError("view_as_forbidden")
    actor = resolve_actor(request)
    if actor.user is None or not actor.has(PERM_PASSWORD_RESET):
        raise PasswordResetError("permission_denied")
    if not actor.is_superadmin:
        if actor.organization is None:
            raise PasswordResetError("no_organization_context")
        if for_write and getattr(request, "org_pending_approval", False):
            raise PasswordResetError("organization_pending")
    return actor


def reset_scope_queryset(actor: RimActor):
    """Operatorun parolunu sıfırlaya biləcəyi hesabların baza queryset-i.

    RİM siyasəti (tenant + iyerarxiya + superuser/özü xaric) olduğu kimi; əlavə
    olaraq superadmin aktiv təşkilat seçibsə o da HƏMİN təşkilatla məhdudlaşır —
    «bu bölmə operatorun təşkilatı daxilində işləyir» qaydası hamı üçün eynidir.
    """
    queryset = manageable_users_queryset(actor)
    if actor.is_superadmin and actor.organization is not None:
        queryset = queryset.filter(memberships__organization=actor.organization).distinct()
    return queryset


def _enforce_rate(scope: str, setting_name: str, default: str, request) -> None:
    """ƏSL istifadəçi (view-as altında da `real_user`) başına vedrə — icazə yoxlamasından ƏVVƏL.

    İcazəsiz/rədd edilən cəhdlər də sayılır: endpoint-i spamlamaqla nə hesab
    «yoxlamaq», nə də rədd-audit sətirləri ilə jurnalı doldurmaq olmasın.
    """
    user = getattr(request, "real_user", None) or getattr(request, "user", None)
    rate = getattr(settings, setting_name, default)
    limited, _retry_after = record_rate_limit_hit(scope, rate, getattr(user, "pk", None))
    if limited:
        raise PasswordResetError("rate_limited", status=429)


def enforce_lookup_rate(request) -> None:
    _enforce_rate(LOOKUP_RATE_SCOPE, "ACCOUNT_PASSWORD_RESET_LOOKUP_RATE_LIMIT", DEFAULT_LOOKUP_RATE, request)


def enforce_reset_rate(request) -> None:
    _enforce_rate(RESET_RATE_SCOPE, "ACCOUNT_PASSWORD_RESET_RATE_LIMIT", DEFAULT_RESET_RATE, request)


def status_code_of(user) -> str:
    """Hesab statusu: ``active`` / ``blocked`` / ``deleted`` / ``login_closed``."""
    profile = getattr(user, "profile", None)
    if profile is not None and getattr(profile, "is_deleted", False):
        return "deleted"
    if not getattr(user, "is_active", False):
        return "blocked"
    if user_access_is_login_blocked(user):
        return "login_closed"
    return "active"


_STATUS_ERRORS = {"deleted": "target_deleted", "blocked": "target_blocked", "login_closed": "target_login_closed"}


def check_resettable(actor: RimActor, target) -> None:
    """Hədəfə parol verilə bilərmi — yoxsa ``PasswordResetError`` (409 = vəziyyət)."""
    try:
        assert_can_manage(actor, target)
        assert_no_foreign_authority(actor, target)
    except RimAccessError as exc:
        raise _from_rim_error(exc) from exc
    status = status_code_of(target)
    if status in _STATUS_ERRORS:
        raise PasswordResetError(_STATUS_ERRORS[status], status=409)


def explain_unavailable(actor: RimActor, candidate):
    """Hədəf sıfırlama əhatəsində deyil — SƏBƏB kodu (və ya «tapılmadı»).

    RİM `_target_error` ilə eyni prinsip: hədəf operatorun ÖZ təşkilatındadırsa
    (və ya özüdürsə) dəqiq səbəb göstərilir; təşkilatdan kənar hesab həmişə
    «tapılmadı»dır — başqa tenantın hesabının MÖVCUDLUĞU sızmır.
    """
    if candidate is None:
        return PasswordResetError("target_not_found", status=404)
    is_self = getattr(actor.user, "pk", None) == candidate.pk
    organization = actor.organization
    if organization is None:
        # Yalnız təşkilatsız superadmin buraya çatır (`operator_for`) — o, platforma
        # səviyyəsində hər hesabı görür.
        visible = actor.is_superadmin
    else:
        visible = candidate.memberships.filter(organization=organization).exists()
    if not (is_self or visible):
        return PasswordResetError("target_not_found", status=404)
    try:
        check_resettable(actor, candidate)
    except PasswordResetError as exc:
        return exc
    return PasswordResetError("target_not_found", status=404)


# ---------------------------------------------------------------------------
# Parol
# ---------------------------------------------------------------------------


def generate_temporary_password(length: int = TEMP_PASSWORD_LENGTH) -> str:
    """Hər qrupdan ən azı bir simvol daşıyan, qarışmayan hərflərdən təsadüfi parol."""
    length = max(10, int(length))
    pools = (_UPPER, _LOWER, _DIGITS)
    characters = [secrets.choice(pool) for pool in pools]
    alphabet = "".join(pools)
    characters += [secrets.choice(alphabet) for _ in range(length - len(characters))]
    secrets.SystemRandom().shuffle(characters)
    return "".join(characters)


def _valid_password(target) -> str:
    """Layihənin parol validatorlarından keçən parol (nadir ilişmədə təkrar cəhd)."""
    for _attempt in range(_MAX_GENERATION_ATTEMPTS):
        candidate = generate_temporary_password()
        try:
            validate_password(candidate, user=target)
        except ValidationError:  # noqa: PERF203 — nadir hal
            continue
        return candidate
    logger.error("Parol sıfırlama: generasiya validatordan keçmədi (target=%s)", getattr(target, "pk", None))
    raise PasswordResetError("password_generation_failed", status=500)


def _clear_login_limits(request, target) -> None:
    """Hədəfin HESAB səviyyəli login vedrələrini təmizləyir (bax `views/auth/_shared.py`).

    Cihaz vedrələri hədəfin öz cihaz cookie-sinə bağlıdır (operator onu bilmir);
    hesab vedrəsi isə yalnız istifadəçi adı/email-ə — məhz «bir neçə dəfə səhv
    yazdım, indi girə bilmirəm» halını bağlayan odur. Operatorun İP-si üzrə
    identity vedrəsi də təmizlənir (istifadəçi çox vaxt eyni kampus şəbəkəsindədir).
    """
    from ..views.auth.constants import LOGIN_LIMIT_SCOPE_ACCOUNT, LOGIN_LIMIT_SCOPE_IDENTITY

    ip_key = f"ip:{(get_client_ip(request) or 'unknown').strip().lower()}"
    for identity in {getattr(target, "username", ""), getattr(target, "email", "")}:
        if not identity:
            continue
        normalized = normalize_rate_identity(identity)
        clear_rate_limit(LOGIN_LIMIT_SCOPE_ACCOUNT, normalized)
        clear_rate_limit(LOGIN_LIMIT_SCOPE_IDENTITY, ip_key, normalized)


def reset_password(actor: RimActor, target_id, *, request):
    """Hədəfə müvəqqəti parol verir. Qaytarır: ``(target, raw_password)``.

    Xam parol YALNIZ bu qaytarışdadır — çağıran onu cavabda bir dəfə göstərməli,
    heç yerdə saxlamamalı və loglamamalıdır. Rate-limit çağıranın işidir
    (`enforce_reset_rate`, icazə yoxlamasından ƏVVƏL).
    """
    if target_id in (None, ""):
        raise PasswordResetError("target_required", status=400)

    User = get_user_model()
    try:
        target = reset_scope_queryset(actor).filter(pk=int(target_id)).first()
    except (TypeError, ValueError):
        raise PasswordResetError("target_not_found", status=404) from None
    if target is None:
        raise explain_unavailable(actor, User.objects.select_related("profile").filter(pk=int(target_id)).first())
    check_resettable(actor, target)

    raw_password = _valid_password(target)
    with transaction.atomic():
        target.set_password(raw_password)
        target.save(update_fields=["password"])
        profile = getattr(target, "profile", None)
        if profile is not None:
            # İlk girişdə `FirstLoginPasswordMiddleware` öz parolunu qurmağa məcbur edir.
            profile.password_change_required = True
            profile.save(update_fields=["password_change_required", "updated_at"])
        # DİQQƏT: audit sətrində parol YOXDUR və olmamalıdır.
        log_action(
            action=AuditAction.UPDATE,
            user=actor.user,
            organization=actor.organization,
            obj=target,
            reason="Parol sıfırlama: müvəqqəti parol verildi (ilk girişdə dəyişmək məcburidir)",
            changes={
                "operation": "admin_password_reset",
                "target_user_id": str(target.pk),
                "target_username": target.username,
                "password_change_required": True,
                "sessions_invalidated": True,
            },
            request=request,
            resource_type="User",
            resource_id=str(target.pk),
            resource_repr=target.username,
        )
    _clear_login_limits(request, target)
    logger.info(
        "Parol sıfırlama: operator=%s target=%s org=%s",
        getattr(actor.user, "pk", None),
        target.pk,
        getattr(actor.organization, "pk", None),
    )
    return target, raw_password


def audit_denied(actor: RimActor | None, request, target_id, code: str) -> None:
    """Rədd edilmiş SIFIRLAMA cəhdi (icazə/iyerarxiya) — pozuntu siqnalı üçün iz."""
    if code in {"rate_limited", "target_required"}:
        return
    try:
        log_action(
            action=AuditAction.DENY,
            user=getattr(request, "real_user", None) or getattr(request, "user", None),
            organization=getattr(actor, "organization", None),
            reason=f"Parol sıfırlama rədd edildi: {code}",
            changes={"operation": "admin_password_reset", "target_user_id": str(target_id or "")[:32], "code": code},
            request=request,
            resource_type="User",
            resource_id=str(target_id or "")[:64],
        )
    except Exception:  # noqa: BLE001 — audit xətası cavabı sındırmamalıdır
        logger.exception("Parol sıfırlama: rədd auditi yazılmadı")


__all__ = [
    "DEFAULT_LOOKUP_RATE",
    "DEFAULT_RESET_RATE",
    "LOOKUP_RATE_SCOPE",
    "PERM_PASSWORD_RESET",
    "PasswordResetError",
    "RESET_RATE_SCOPE",
    "TEMP_PASSWORD_LENGTH",
    "audit_denied",
    "check_resettable",
    "enforce_lookup_rate",
    "enforce_reset_rate",
    "error_message",
    "explain_unavailable",
    "generate_temporary_password",
    "operator_for",
    "reset_password",
    "reset_scope_queryset",
    "status_code_of",
]
