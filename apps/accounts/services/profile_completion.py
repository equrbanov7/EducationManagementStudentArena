"""«Məlumatlarınızı tamamlayın» — yazma servisi (sahib 2026-10-17).

Siyasət ``apps/accounts/profile_completion.py``-dadır; bu modul YALNIZ boş sahələri yoxlayır və yazır:

* dolu sahəyə (ATİS / RİM-dən gələn rəsmi dəyər) toxunulmur — forma onu göstərmir, POST-da gəlsə də atılır;
* FİN qlobal unikaldır (``UserProfile.fin``): başqa hesabdakı FİN rədd olunur, kimə aid olduğu SÖYLƏNMİR;
  münaqişə audit-ə düşür (RİM iki hesabın birləşdirilməsinə baxa bilsin);
* e-poçt kanonik unikal indekslə yoxlanılır (ilk-giriş axını ilə eyni forma); yazılan ünvan ``email_verified``
  sayılmır — növbəti OTP axını onu təsdiqləyir (RİM / profil redaktəsi ilə eyni qayda);
* audit və log YALNIZ sahə adlarını saxlayır — FİN, telefon, e-poçt DƏYƏRLƏRİ heç vaxt yazılmır.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import pgettext

from apps.audit.public import log_action
from core.constants import AuditAction
from core.rate_limit import record_rate_limit_hit

from .. import profile_completion as policy

logger = logging.getLogger(__name__)
User = get_user_model()

_CTX = "accounts.profile_completion"

AUDIT_REASON_SAVED = "profile_completion"
AUDIT_REASON_CONFLICT = "profile_completion_conflict"

#: FİN / e-poçt unikallıq yoxlaması hesab başına məhdud (SEC-1 F1, 2026-10-17): «başqa hesabda var» cavabı
#: başqasının FİN-ini təxmin etmək üçün işlədilməsin. Normal istifadəçi 1–2 cəhddə bitirir.
IDENTITY_CHECK_SCOPE = "profile_completion_identity"
_DEFAULT_IDENTITY_CHECK_RATE = "8/1h"


@dataclass
class CompletionResult:
    saved: list = field(default_factory=list)
    errors: dict = field(default_factory=dict)
    remaining: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _fin_conflict_message() -> str:
    return pgettext(
        _CTX,
        "Bu FİN kod başqa hesabda qeydə alınıb. Düzgün yazdığınıza əminsinizsə, RİM-ə müraciət edin — "
        "hesablarınız yoxlanılıb birləşdiriləcək.",
    )


def _rate_limited_message(retry_after: int | None) -> str:
    minutes = max(1, -(-int(retry_after or 60) // 60))
    return pgettext(_CTX, "Çox sayda cəhd edildi. %(minutes)s dəqiqə sonra yenidən yoxlayın.") % {"minutes": minutes}


def _identity_check_limited(user) -> tuple[bool, int | None]:
    rate = getattr(settings, "PROFILE_COMPLETION_IDENTITY_RATE_LIMIT", _DEFAULT_IDENTITY_CHECK_RATE)
    return record_rate_limit_hit(IDENTITY_CHECK_SCOPE, rate, user.pk)


def _email_conflict_message() -> str:
    return pgettext(_CTX, "Bu e-poçt ünvanı istifadə oluna bilməz. Başqa ünvan yazın.")


def _fin_taken(fin: str, user) -> bool:
    from ..models import UserProfile

    return UserProfile.objects.filter(fin=fin).exclude(user_id=user.pk).exists()


def _email_taken(email: str, user) -> bool:
    from ..identity import canonical_identity_queryset

    return canonical_identity_queryset(User.objects.all(), "email", email).exclude(pk=user.pk).exists()


def _audit(request, user, *, reason: str, fields: list, extra: dict | None = None) -> None:
    changes = {"fields": sorted(fields)}
    changes.update(extra or {})
    try:
        log_action(
            action=AuditAction.UPDATE,
            user=user,
            organization=getattr(request, "organization", None),
            obj=user,
            reason=reason,
            changes=changes,
            request=request,
        )
    except Exception:  # noqa: BLE001 — audit xətası istifadəçini bloklamamalıdır
        logger.exception("profile completion audit failed")


def _clean(missing_keys, data) -> tuple[dict, dict]:
    values, errors = {}, {}
    for key in missing_keys:
        try:
            values[key] = policy.CLEANERS[key](data.get(key))
        except ValidationError as exc:
            errors[key] = exc.messages[0]
    return values, errors


def _conflicts(values: dict, user) -> dict:
    errors = {}
    if policy.FIELD_FIN in values and _fin_taken(values[policy.FIELD_FIN], user):
        errors[policy.FIELD_FIN] = _fin_conflict_message()
    if policy.FIELD_EMAIL in values and _email_taken(values[policy.FIELD_EMAIL], user):
        errors[policy.FIELD_EMAIL] = _email_conflict_message()
    return errors


def _write(user, values: dict, *, completed: bool) -> None:
    profile = user.profile
    profile_fields = ["updated_at"]
    if policy.FIELD_FIN in values:
        profile.fin = values[policy.FIELD_FIN]
        # Özü yazdığı FİN təsdiqlənməmişdir — rəsmi idxal fərqli adla gəlsə üstün gəlir (SEC-1 F2).
        profile.fin_self_reported = True
        profile_fields += ["fin", "fin_self_reported"]
    if policy.FIELD_PHONE in values:
        profile.phone = values[policy.FIELD_PHONE]
        profile_fields.append("phone")
    if policy.FIELD_EMAIL in values:
        user.email = values[policy.FIELD_EMAIL]
        user.save(update_fields=["email"])
        profile.email_verified = False
        profile_fields.append("email_verified")
    if completed:
        profile.profile_completed_at = timezone.now()
        profile_fields.append("profile_completed_at")
    profile.save(update_fields=profile_fields)


def complete_profile(request, data) -> CompletionResult:
    """Boş sahələri yoxlayıb yazır; xəta varsa HEÇ NƏ yazılmır."""
    user = request.user
    missing_keys = [spec.key for spec in policy.missing_for_request(request)]
    if not missing_keys:
        return CompletionResult()

    values, errors = _clean(missing_keys, data)
    if errors:
        # Unikallıq yalnız BÜTÜN sahələr düzgün olanda yoxlanılır — «phone=x» ilə FİN sınamaq olmasın (SEC-1 F1).
        return CompletionResult(errors=errors, remaining=missing_keys)
    if any(key in values for key in (policy.FIELD_FIN, policy.FIELD_EMAIL)):
        limited, retry_after = _identity_check_limited(user)
        if limited:
            message = _rate_limited_message(retry_after)
            keys = [key for key in (policy.FIELD_FIN, policy.FIELD_EMAIL) if key in values]
            return CompletionResult(errors={key: message for key in keys}, remaining=missing_keys)
    conflicts = _conflicts(values, user)
    if conflicts:
        _audit(request, user, reason=AUDIT_REASON_CONFLICT, fields=list(conflicts), extra={"outcome": "duplicate"})
    errors.update(conflicts)
    if errors:
        return CompletionResult(errors=errors, remaining=missing_keys)

    try:
        with transaction.atomic():
            _write(user, values, completed=True)
    except IntegrityError:
        # Yoxlama ilə yazı arasında eyni FİN / e-poçt başqa hesaba yazılıb (yarış) — unikal indeks qoruyur.
        user.refresh_from_db(fields=["email"])
        user.profile.refresh_from_db()
        conflict_fields = [key for key in (policy.FIELD_FIN, policy.FIELD_EMAIL) if key in values]
        _audit(request, user, reason=AUDIT_REASON_CONFLICT, fields=conflict_fields, extra={"outcome": "race"})
        errors = {
            key: (_fin_conflict_message() if key == policy.FIELD_FIN else _email_conflict_message())
            for key in conflict_fields
        }
        return CompletionResult(errors=errors, remaining=missing_keys)

    saved = sorted(values)
    _audit(request, user, reason=AUDIT_REASON_SAVED, fields=saved)
    logger.info("profile completion saved", extra={"user_id": user.pk, "fields": saved})
    return CompletionResult(saved=saved)


__all__ = [
    "AUDIT_REASON_CONFLICT",
    "AUDIT_REASON_SAVED",
    "IDENTITY_CHECK_SCOPE",
    "CompletionResult",
    "complete_profile",
]
