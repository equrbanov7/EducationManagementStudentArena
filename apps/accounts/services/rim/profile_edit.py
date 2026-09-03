"""RİM tərəfindən şəxsi məlumatların redaktəsi (ad/soyad/ata adı/email/telefon/FİN).

Köhnə sistemin idxalında ad-soyad transliterasiyası, boş ata adı və səhv email
adi haldır. RİM operatoru bunları düzəldir; hər dəyişiklik audit-ə köhnə/yeni
dəyərlə düşür.

KRİTİK: email dəyişəndə ``email_verified=False`` olur. Səbəb — email parol
bərpasının kökündədir; təsdiqlənməmiş yeni ünvan üzərindən bərpa mümkün olsaydı,
operator (və ya ələ keçirilmiş operator hesabı) emaili öz ünvanına dəyişib
hesabı tam mənimsəyə bilərdi. İstifadəçi yeni ünvanı OTP ilə özü təsdiqləyir.
"""

from __future__ import annotations

import logging
import re

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction

from apps.audit.public import log_action
from core.constants import AuditAction

from .policy import PERM_EDIT, RimAccessError, RimActor, assert_can_manage, require_permission

logger = logging.getLogger(__name__)
User = get_user_model()

# HÜDUD (Əsasnamə X + Proqram inzibatçısı təlimatı §34 — «səlahiyyətində olmayan
# məlumat məzmununu özbaşına dəyişməmək»): bu allow-list yalnız ŞƏXSİ
# İDENTİFİKASİYA sahələrini əhatə edir. Akademik məzmun (qiymət, davamiyyət,
# jurnal, imtahan nəticəsi) buraya ƏLAVƏ EDİLMİR — onun sahibi dekanlıq/kafedradır
# və düzəlişi sənədli jurnal korreksiya axınından keçir.
#: User modelindəki sahələr.
USER_FIELDS = ("first_name", "last_name", "email")
#: UserProfile-dakı sahələr.
PROFILE_FIELDS = ("patronymic", "phone", "fin")
EDITABLE_FIELDS = USER_FIELDS + PROFILE_FIELDS

FIELD_LABELS = {
    "first_name": "Ad",
    "last_name": "Soyad",
    "patronymic": "Ata adı",
    "email": "Email",
    "phone": "Telefon",
    "fin": "FİN",
}

_MAX_LENGTHS = {
    "first_name": 150,
    "last_name": 150,
    "email": 254,
    "patronymic": 100,
    "phone": 20,
    "fin": 7,
}

#: FİN — kanonik forma `core.validators`-dadır (7 simvol, A-Z0-9, NULL-unique).
#: Buradakı naxış yalnız erkən istifadəçi rəyi üçündür; yekun yoxlama modeldədir.
_FIN_PATTERN = re.compile(r"^[A-Za-z0-9]{7}$")
_PHONE_PATTERN = re.compile(r"^[0-9+()\-\s]{5,20}$")


def _clean_value(field_name: str, raw_value) -> str:
    value = " ".join(str(raw_value or "").strip().split())
    return value[: _MAX_LENGTHS.get(field_name, 150)]


def _validate(field_name: str, value: str) -> str:
    if field_name == "email" and value:
        try:
            validate_email(value)
        except ValidationError as exc:
            raise RimAccessError("invalid_email", "Email ünvanı düzgün deyil.", status=400) from exc
        return value.lower()
    if field_name == "fin" and value and not _FIN_PATTERN.match(value):
        raise RimAccessError("invalid_fin", "FİN 7 simvol olmalıdır (yalnız hərf və rəqəm).", status=400)
    if field_name == "phone" and value and not _PHONE_PATTERN.match(value):
        raise RimAccessError("invalid_phone", "Telefon nömrəsi düzgün deyil.", status=400)
    return value


def _assert_email_available(email: str, target_user) -> None:
    """Email başqa hesabda istifadə olunursa dəyişiklik rədd olunur.

    Django-nun `User.email` sahəsi unikal DEYİL, amma
    `EmailOrUsernameBackend` email ilə giriş verir — dublikat email iki hesabı
    eyni açara bağlayardı (backend `.first()` götürür, yəni digər hesab
    əlçatmaz qalar).
    """
    if not email:
        return
    clash = User.objects.filter(email__iexact=email).exclude(pk=target_user.pk).exists()
    if clash:
        raise RimAccessError(
            "email_taken",
            "Bu email ünvanı başqa hesabda istifadə olunur.",
            status=409,
        )


def update_user_fields(actor: RimActor, target_user, *, data, request=None, reason=""):
    """Hədəfin şəxsi məlumatlarını yeniləyir.

    Args:
        data: ``{field_name: value}`` — yalnız ``EDITABLE_FIELDS`` nəzərə alınır.
              Göndərilməyən sahə DƏYİŞMİR (partial update).

    Returns:
        dict — ``{field: {"old": ..., "new": ...}}`` faktiki dəyişikliklər.
    """
    require_permission(actor, PERM_EDIT)
    assert_can_manage(actor, target_user)

    if not isinstance(data, dict):
        raise RimAccessError("invalid_payload", "Göndərilən məlumat düzgün deyil.", status=400)

    profile = getattr(target_user, "profile", None)
    if profile is None:
        from apps.accounts.models import UserProfile

        profile, _created = UserProfile.objects.get_or_create(user=target_user)

    changes: dict = {}
    email_changed = False

    for field_name in EDITABLE_FIELDS:
        if field_name not in data:
            continue
        new_value = _validate(field_name, _clean_value(field_name, data[field_name]))
        owner = target_user if field_name in USER_FIELDS else profile
        old_value = str(getattr(owner, field_name, "") or "")
        if field_name == "email":
            old_value = old_value.lower()
        if old_value == new_value:
            continue
        if field_name == "email":
            _assert_email_available(new_value, target_user)
            email_changed = True
        # FİN NULL-unique-dir: boş dəyər `""` yox, `None` yazılmalıdır, əks
        # halda ikinci boş FİN unikallıq pozuntusu verir (core/validators).
        setattr(owner, field_name, (new_value or None) if field_name == "fin" else new_value)
        changes[field_name] = {"old": old_value, "new": new_value}

    if not changes:
        return {}

    with transaction.atomic():
        user_updates = [name for name in USER_FIELDS if name in changes]
        if user_updates:
            target_user.save(update_fields=user_updates)

        profile_updates = [name for name in PROFILE_FIELDS if name in changes]
        if email_changed:
            # Yeni ünvan istifadəçi tərəfindən OTP ilə təsdiqlənməlidir.
            profile.email_verified = False
            profile_updates.append("email_verified")
            changes["email_verified"] = {"old": True, "new": False}
        if profile_updates:
            profile.save(update_fields=[*profile_updates, "updated_at"])

        log_action(
            action=AuditAction.UPDATE,
            user=actor.user,
            organization=actor.organization,
            obj=target_user,
            reason=f"RİM: şəxsi məlumat redaktəsi. Səbəb: {str(reason or '-')[:300]}",
            old_values={name: value["old"] for name, value in changes.items()},
            new_values={name: value["new"] for name, value in changes.items()},
            changes={
                "target_username": target_user.username,
                "target_user_id": str(target_user.pk),
                "operation": "edit_profile",
                "fields": sorted(changes),
                "reason_text": str(reason or "")[:300],
            },
            request=request,
            resource_type="User",
            resource_id=str(target_user.pk),
            resource_repr=target_user.username,
        )

    logger.info(
        "RİM: profile fields %s updated by actor=%s for target=%s",
        sorted(changes),
        getattr(actor.user, "pk", None),
        target_user.pk,
    )
    return changes


__all__ = [
    "EDITABLE_FIELDS",
    "FIELD_LABELS",
    "PROFILE_FIELDS",
    "USER_FIELDS",
    "update_user_fields",
]
