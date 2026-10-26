"""«İstifadəçi adını dəyiş» — operator başqasının istifadəçi adını PAROLU BİLMƏDƏN dəyişir (sahib 2026-10-26).

Sahib: «username dəyişməyim üçün hissəni mənə aç, pass bilmədən username dəyişə bilim». Yer — «Parol sıfırlama»
bölməsi (`account.password_reset`): eyni axtarış kartında «Parolu sıfırla»nın yanında ikinci düymə.

İCAZƏ VƏ İYERARXİYA parol sıfırlama ilə EYNİDİR — `password_reset_admin.operator_for` (icazə, view-as qadağası,
aktiv təşkilat) və RİM siyasəti (`assert_can_manage` + `assert_no_foreign_authority`): superuser / profil-superadmin
heç vaxt, özü yox (öz adı «Profil redaktə»dən), təşkilat sahibi yalnız superadmin, eyni və ya yüksək rütbə (məs.
başqa RİM rəhbəri) yox, tenantdan kənar hesab «tapılmadı». Fərq: bloklanmış və girişi bağlı (arxiv) hesabın da adı
dəyişə bilər — ad dəyişikliyi girişi AÇMIR; yalnız SİLİNMİŞ hesab əvvəlcə bərpa olunmalıdır.

AD QAYDASI istifadəçinin öz dəyişikliyi ilə EYNİDİR (`username_change.validate_username`): kanonik forma (NFKC + trim
+ kiçik hərf), 3–30 simvol, ``a–z 0–9 . _ -``, ``@`` yox (e-poçtla toqquşmur), rezerv adlar/prefikslər yox, unikallıq
kanonik formada (``Ad.Soyad`` = ``ad.soyad``). «Avtomatik təklif» — ``ad.soyad`` (ASCII), tutulubsa ``ad.soyad2`` …
(`username_repair.name_base` + `teacher_roster.claim_name_username` qaydası).

DƏYİŞMƏYƏNLƏR (sahib: «heç kimin parolunu dəyişmə»): parol, sessiyalar (Django sessiya heşi parola bağlıdır, ada
yox), ``email_verified`` / OTP vəziyyəti, ``password_change_required`` və istifadəçinin öz gözləmə müddəti
(``username_changed_at`` — operator dəyişikliyi onu YAZMIR). Yalnız ``auth_user.username``.

AUDİT: operator, hədəf, köhnə → yeni ad, SƏBƏB (≥ ``MIN_REASON_LENGTH``); rədd edilmiş cəhdlər də (DENY). Hədəfə
in-app bildiriş + real ünvana e-poçt (COMMIT-dən sonra, best-effort).
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils.translation import pgettext

from apps.audit.public import log_action
from core.constants import AuditAction
from core.rate_limit import record_rate_limit_hit

from ..identity import canonical_identity
from . import password_reset_admin as pwr
from .rim.policy import RimAccessError, RimActor, assert_can_manage, assert_no_foreign_authority
from .username_change import MAX_LENGTH, UsernameChangeError, normalize_username, username_taken, validate_username

logger = logging.getLogger(__name__)
_CTX = "accounts.username_change_admin"

OPERATION = "admin_username_change"
RENAME_RATE_SCOPE = "account_username_change"
DEFAULT_RENAME_RATE = "30/1h"
_SUGGEST_MAX_SUFFIX = 200

#: Mətni parol sıfırlama ilə EYNİ olan kodlar — onun (artıq tərcümə olunmuş) mesajı işlədilir.
_SHARED_CODES = frozenset(
    {"no_organization_context", "target_required", "target_not_found", "target_deleted", "rate_limited"}
)
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
    if code in _SHARED_CODES:
        return pwr.error_message(code)
    messages = {
        "permission_denied": pgettext(_CTX, "İstifadəçi adını dəyişmək üçün icazəniz yoxdur."),
        "view_as_forbidden": pgettext(
            _CTX, "Başqasının adından baxış rejimində istifadəçi adını dəyişmək olmaz. Əvvəlcə baxış rejimindən çıxın."
        ),
        "organization_pending": pgettext(_CTX, "Təşkilatınız hələ təsdiqlənməyib — istifadəçi adını dəyişmək olmaz."),
        "target_is_superadmin": pgettext(_CTX, "Superadmin hesabının istifadəçi adı bu bölmədən dəyişdirilə bilməz."),
        "target_is_self": pgettext(
            _CTX, "Öz istifadəçi adınızı bu bölmədən dəyişə bilməzsiniz — «Profil redaktə» bölməsindən istifadə edin."
        ),
        "target_is_owner": pgettext(_CTX, "Təşkilat sahibinin istifadəçi adını yalnız superadmin dəyişə bilər."),
        "target_rank_too_high": pgettext(
            _CTX, "Özünüzlə eyni və ya daha yüksək səlahiyyətli istifadəçinin adını dəyişə bilməzsiniz."
        ),
        "reason_required": pgettext(_CTX, "Səbəb yazılmalıdır (ən azı 10 simvol)."),
        "same": pgettext(_CTX, "Yeni istifadəçi adı cari addan fərqli olmalıdır."),
        "taken": pgettext(_CTX, "Bu istifadəçi adı artıq istifadə olunur."),
        "suggestion_unavailable": pgettext(
            _CTX, "Ad və soyaddan standart istifadəçi adı qurmaq alınmadı — adı əl ilə yazın."
        ),
    }
    return messages.get(code) or messages["permission_denied"]


class UsernameAdminError(Exception):
    """Rədd edildi. ``code`` maşın-oxunaqlı; ``message`` tərcümə olunmuş mətn (ad qaydası öz mətnini daşıyır)."""

    def __init__(self, code: str, status: int = 403, detail: str = ""):
        super().__init__(code, status, detail)
        self.code = code
        self.status = status
        self.detail = detail

    @property
    def message(self) -> str:
        return self.detail or error_message(self.code)

    def __str__(self):
        return self.code


# ---------------------------------------------------------------------------
# Operator, hədəf, səlahiyyət
# ---------------------------------------------------------------------------


def operator_for(request, *, for_write: bool = False) -> RimActor:
    """Parol sıfırlama ilə EYNİ qapı (icazə + view-as + aktiv təşkilat); mətn ad dəyişikliyinə uyğun."""
    try:
        return pwr.operator_for(request, for_write=for_write)
    except pwr.PasswordResetError as exc:
        raise UsernameAdminError(exc.code, exc.status) from exc


def enforce_rename_rate(request) -> None:
    """ƏSL istifadəçi başına vedrə — icazə yoxlamasından ƏVVƏL (rədd edilən cəhdlər də sayılır)."""
    user = getattr(request, "real_user", None) or getattr(request, "user", None)
    rate = getattr(settings, "ACCOUNT_USERNAME_CHANGE_RATE_LIMIT", DEFAULT_RENAME_RATE)
    limited, _retry_after = record_rate_limit_hit(RENAME_RATE_SCOPE, rate, getattr(user, "pk", None))
    if limited:
        raise UsernameAdminError("rate_limited", status=429)


def check_renamable(actor: RimActor, target) -> None:
    """Hədəfin adı dəyişə bilərmi — yoxsa ``UsernameAdminError`` (bloklanmış / arxiv hesab — OLAR)."""
    try:
        assert_can_manage(actor, target)
        assert_no_foreign_authority(actor, target)
    except RimAccessError as exc:
        code, status = _RIM_CODE_MAP.get(exc.reason_code, ("permission_denied", 403))
        raise UsernameAdminError(code, status) from exc
    if pwr.status_code_of(target) == "deleted":
        raise UsernameAdminError("target_deleted", status=409)


def _resolve_target(actor: RimActor, target_id):
    if target_id in (None, ""):
        raise UsernameAdminError("target_required", status=400)
    try:
        pk = int(target_id)
    except (TypeError, ValueError):
        raise UsernameAdminError("target_not_found", status=404) from None
    target = pwr.reset_scope_queryset(actor).filter(pk=pk).first()
    if target is None:
        # Tenant daxilindədirsə dəqiq səbəb, kənardadırsa «tapılmadı» (mövcudluq sızmır) — parol sıfırlama qaydası.
        candidate = get_user_model().objects.select_related("profile").filter(pk=pk).first()
        hidden = pwr.explain_unavailable(actor, candidate)
        if hidden.code == "target_not_found" or candidate is None:
            raise UsernameAdminError("target_not_found", status=404)
        check_renamable(actor, candidate)
        raise UsernameAdminError("target_not_found", status=404)
    check_renamable(actor, target)
    return target


def normalize_reason(raw) -> str:
    try:
        return pwr.normalize_reason(raw)
    except pwr.PasswordResetError:
        raise UsernameAdminError("reason_required", status=400) from None


# ---------------------------------------------------------------------------
# «Avtomatik təklif» — ad.soyad (pulsuz)
# ---------------------------------------------------------------------------


def _email_taken(value: str, *, exclude_pk) -> bool:
    return get_user_model().objects.exclude(pk=exclude_pk).filter(email__iexact=value).exists()


def suggest_username(actor: RimActor, target_id) -> dict:
    """``{"username": …, "is_current": bool}`` — ``ad.soyad``, tutulubsa ``ad.soyad2`` … (YAZMIR)."""
    from .username_repair import name_base

    target = _resolve_target(actor, target_id)
    base = name_base(target.first_name, target.last_name)[: MAX_LENGTH - 3].strip("._-")
    if not base:
        raise UsernameAdminError("suggestion_unavailable", status=409)
    current = canonical_identity(target.username)
    for suffix in range(1, _SUGGEST_MAX_SUFFIX + 1):
        candidate = base if suffix == 1 else f"{base}{suffix}"
        if candidate == current:
            return {"username": candidate, "is_current": True}
        try:
            validate_username(candidate)
        except UsernameChangeError:
            raise UsernameAdminError("suggestion_unavailable", status=409) from None
        if not username_taken(candidate, exclude_pk=target.pk) and not _email_taken(candidate, exclude_pk=target.pk):
            return {"username": candidate, "is_current": False}
    raise UsernameAdminError("suggestion_unavailable", status=409)


# ---------------------------------------------------------------------------
# Dəyişiklik
# ---------------------------------------------------------------------------


def change_username(actor: RimActor, target_id, new_username, *, reason, request):
    """Hədəfin adını dəyişir. Qaytarır: ``(target, old_username)``. Xəta → ``UsernameAdminError`` (heç nə yazılmır).

    Rate-limit çağıranın işidir (`enforce_rename_rate`, icazə yoxlamasından ƏVVƏL).
    """
    if target_id in (None, ""):
        raise UsernameAdminError("target_required", status=400)
    reason = normalize_reason(reason)
    target = _resolve_target(actor, target_id)

    value = normalize_username(new_username)
    try:
        validate_username(value)
    except UsernameChangeError as exc:
        raise UsernameAdminError(exc.code, status=400, detail=exc.message) from None
    if value == canonical_identity(target.username):
        raise UsernameAdminError("same", status=400)

    User = get_user_model()
    with transaction.atomic():
        locked = User._default_manager.select_for_update().get(pk=target.pk)
        if username_taken(value, exclude_pk=locked.pk):
            raise UsernameAdminError("taken", status=409)
        old_username = locked.username
        locked.username = value
        try:
            with transaction.atomic():
                locked.save(update_fields=["username"])
        except IntegrityError:  # unikal ifadə indeksi / ad↔e-poçt trigger-i (yarış)
            raise UsernameAdminError("taken", status=409) from None
        log_action(
            action=AuditAction.UPDATE,
            user=actor.user,
            organization=actor.organization,
            obj=locked,
            old_values={"username": old_username},
            new_values={"username": value},
            reason=f"İstifadəçi adı dəyişdirildi (parol toxunulmadı). Səbəb: {reason}",
            changes={
                "operation": OPERATION,
                "target_user_id": str(locked.pk),
                "old_username": old_username,
                "new_username": value,
                "password_changed": False,
                "reason_text": reason,
            },
            request=request,
            resource_type="User",
            resource_id=str(locked.pk),
            resource_repr=value,
        )
        from .username_change_notify import notify_username_changed

        notify_username_changed(locked, getattr(locked, "profile", None), old_username=old_username, by_operator=True)

    target.username = value
    logger.info(
        "İstifadəçi adı dəyişdirildi: operator=%s target=%s org=%s",
        getattr(actor.user, "pk", None),
        target.pk,
        getattr(actor.organization, "pk", None),
    )
    return target, old_username


def audit_denied(actor: RimActor | None, request, target_id, code: str) -> None:
    """Rədd edilmiş cəhd (icazə/iyerarxiya) — pozuntu siqnalı üçün iz; forma xətaları yazılmır."""
    if code not in _RIM_CODE_MAP and code not in {"view_as_forbidden", "organization_pending", "target_deleted"}:
        return
    try:
        log_action(
            action=AuditAction.DENY,
            user=getattr(request, "real_user", None) or getattr(request, "user", None),
            organization=getattr(actor, "organization", None),
            reason=f"İstifadəçi adı dəyişikliyi rədd edildi: {code}",
            changes={"operation": OPERATION, "target_user_id": str(target_id or "")[:32], "code": code},
            request=request,
            resource_type="User",
            resource_id=str(target_id or "")[:64],
        )
    except Exception:  # noqa: BLE001 — audit xətası cavabı sındırmamalıdır
        logger.exception("İstifadəçi adı dəyişikliyi: rədd auditi yazılmadı")


__all__ = [
    "DEFAULT_RENAME_RATE",
    "OPERATION",
    "RENAME_RATE_SCOPE",
    "UsernameAdminError",
    "audit_denied",
    "change_username",
    "check_renamable",
    "enforce_rename_rate",
    "error_message",
    "normalize_reason",
    "operator_for",
    "suggest_username",
]
