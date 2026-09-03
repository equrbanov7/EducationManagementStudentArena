"""RİM parol təyini — köhnə sistemdən idxal olunmuş hesabların açarı.

Miqrasiya edilmiş 8000+ hesabın parolu YOXDUR (unusable password — kredensiallar
qəsdən köçürülmür). İstifadəçi sistemə yalnız RİM-in təyin etdiyi BİRDƏFƏLİK
parolla girə bilir və dərhal `password_change_required` axınına düşür.

TƏHLÜKƏSİZLİK QAYDALARI (pozulmaz):

* Parol audit log-a **YAZILMIR** — audit-də yalnız «parol təyin edildi» faktı,
  aktor, hədəf, vaxt və səbəb qalır.
* Parol çağırana YALNIZ BİR DƏFƏ, cavab gövdəsində qaytarılır; heç bir yerdə
  saxlanılmır (nə DB-də, nə keşdə, nə log-da).
* Təyindən sonra `password_change_required=True` qalır → istifadəçi ilk girişdə
  OTP ilə emailini təsdiqləyib ÖZ parolunu qurmağa məcburdur.
* `email_verified` QƏSDƏN sıfırlanmır: hesabın emaili artıq təsdiqlidirsə
  operator onu ləğv etməməlidir (yalnız email DƏYİŞƏNDƏ sıfırlanır — bax
  `profile_edit.py`).
* Parol dəyişikliyi Django-nun sessiya-hash mexanizmi ilə hədəfin BÜTÜN açıq
  sessiyalarını etibarsız edir (ələ keçirilmiş sessiya qapanır).
"""

from __future__ import annotations

import logging
import secrets

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.audit.public import log_action
from core.constants import AuditAction
from core.rate_limit import is_rate_limited, record_rate_limit_hit

from .policy import PERM_CREDENTIALS, RimAccessError, RimActor, assert_can_manage, require_permission

logger = logging.getLogger(__name__)

#: Oxunaqlı əlifba — səsli/vizual qarışan simvollar (0/O, 1/l/I) YOXDUR, çünki
#: operator parolu telefonda diktə edir.
_ALPHABET_UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_ALPHABET_LOWER = "abcdefghijkmnpqrstuvwxyz"
_ALPHABET_DIGITS = "23456789"
_ALPHABET_SYMBOLS = "!@#$%*+-"

TEMP_PASSWORD_LENGTH = 12
_MAX_GENERATION_ATTEMPTS = 12

#: Rate-limit: bir aktor saatda neçə parol təyin edə bilər.
DEFAULT_CREDENTIALS_RATE = "30/h"
RATE_LIMIT_SCOPE = "rim_set_password"


def generate_temporary_password(length: int = TEMP_PASSWORD_LENGTH) -> str:
    """Hər kateqoriyadan ən azı bir simvol daşıyan təsadüfi parol."""
    length = max(10, int(length))
    pools = (_ALPHABET_UPPER, _ALPHABET_LOWER, _ALPHABET_DIGITS, _ALPHABET_SYMBOLS)
    characters = [secrets.choice(pool) for pool in pools]
    everything = "".join(pools)
    characters += [secrets.choice(everything) for _ in range(length - len(characters))]
    # `secrets.SystemRandom().shuffle` — kateqoriya sırasını gizlədir.
    secrets.SystemRandom().shuffle(characters)
    return "".join(characters)


def _generate_valid_password(target_user) -> str:
    """Django parol validatorlarından keçən parol istehsal edir.

    Təsadüfi parol nadir hallarda `UserAttributeSimilarityValidator`-a ilişə
    bilər (məs. istifadəçi adı parolun içinə düşəndə) — ona görə təkrar cəhd.
    """
    last_error = None
    for _attempt in range(_MAX_GENERATION_ATTEMPTS):
        candidate = generate_temporary_password()
        try:
            validate_password(candidate, user=target_user)
        except ValidationError as exc:  # noqa: PERF203 — nadir hal
            last_error = exc
            continue
        return candidate
    logger.error("RİM: parol generasiyası validatordan keçmədi: %s", last_error)
    raise RimAccessError(
        "password_generation_failed",
        "Parol yaradıla bilmədi. Yenidən cəhd edin.",
        status=500,
    )


def _rate_limit_key(actor: RimActor):
    return (getattr(actor.user, "pk", "anonymous"),)


def set_temporary_password(actor: RimActor, target_user, *, request=None, reason=""):
    """Hədəfə birdəfəlik parol təyin edir və onu **bir dəfə** qaytarır.

    Returns:
        str — xam parol. Çağıran tərəf onu YALNIZ cavabda göstərməli, heç yerdə
        saxlamamalıdır.

    Raises:
        RimAccessError — icazə, iyerarxiya və ya rate-limit pozuntusu.
    """
    require_permission(actor, PERM_CREDENTIALS)
    assert_can_manage(actor, target_user)

    profile = getattr(target_user, "profile", None)
    if profile is not None and getattr(profile, "is_deleted", False):
        raise RimAccessError(
            "target_is_deleted",
            "Silinmiş hesaba parol təyin etmək olmaz — əvvəlcə hesabı bərpa edin.",
            status=409,
        )

    rate = getattr(settings, "RIM_PASSWORD_RESET_RATE_LIMIT", DEFAULT_CREDENTIALS_RATE)
    key_parts = _rate_limit_key(actor)
    limited, retry_after = is_rate_limited(RATE_LIMIT_SCOPE, rate, *key_parts)
    if limited:
        raise RimAccessError(
            "rate_limited",
            "Çox sayda parol təyini. Bir az sonra yenidən cəhd edin.",
            status=429,
        )

    raw_password = _generate_valid_password(target_user)

    with transaction.atomic():
        target_user.set_password(raw_password)
        target_user.save(update_fields=["password"])

        if profile is not None:
            # İstifadəçi ilk girişdə OTP + öz parolunu qurmağa məcburdur.
            profile.password_change_required = True
            profile.save(update_fields=["password_change_required", "updated_at"])

        # DİQQƏT: `changes` içində parol dəyəri YOXDUR və olmamalıdır.
        log_action(
            action=AuditAction.UPDATE,
            user=actor.user,
            organization=actor.organization,
            obj=target_user,
            reason=f"RİM: müvəqqəti parol təyin edildi. Səbəb: {str(reason or '-')[:300]}",
            changes={
                "target_username": target_user.username,
                "target_user_id": str(target_user.pk),
                "operation": "set_temporary_password",
                "password_change_required": True,
                "reason_text": str(reason or "")[:300],
            },
            request=request,
            resource_type="User",
            resource_id=str(target_user.pk),
            resource_repr=target_user.username,
        )

    record_rate_limit_hit(RATE_LIMIT_SCOPE, rate, *key_parts)
    logger.info(
        "RİM: temporary password issued by actor=%s for target=%s",
        getattr(actor.user, "pk", None),
        target_user.pk,
    )
    return raw_password


__all__ = [
    "DEFAULT_CREDENTIALS_RATE",
    "RATE_LIMIT_SCOPE",
    "TEMP_PASSWORD_LENGTH",
    "generate_temporary_password",
    "set_temporary_password",
]
