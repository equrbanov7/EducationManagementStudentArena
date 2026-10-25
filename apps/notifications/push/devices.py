"""Cihaz qeydiyyatı — mobil tətbiq girişdən sonra FCM tokenini verir, çıxışda silir.

* İDEMPOTENT: eyni token yenidən gələndə sətir yenilənir (platforma, versiya, dil, ``last_seen``, aktivlik).
* Token başqa hesabdadırsa YENİ istifadəçiyə keçir (eyni telefonda hesab dəyişdi — köhnə hesabın bildirişi
  o telefona getməsin).
* İstifadəçi başına ən çox :data:`MAX_DEVICES_PER_USER` aktiv cihaz — artıq olanda ən köhnə görünən deaktiv olur.
* Sətrə yalnız ``user`` süzgəci ilə toxunulur (``bypass_rls`` — cədvəl tenant-sızdır, bax model şərhi).
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.notifications.models import NotificationType, PushDevice, PushPlatform
from core.rls import bypass_rls

MAX_DEVICES_PER_USER = 10
TOKEN_MIN_LENGTH = 20
TOKEN_MAX_LENGTH = 512


class DeviceError(ValueError):
    """Yararsız sorğu — ``code`` API cavabındakı maşın kodu."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def clean_token(value) -> str:
    token = str(value or "").strip()
    if not (TOKEN_MIN_LENGTH <= len(token) <= TOKEN_MAX_LENGTH) or any(ch.isspace() for ch in token):
        raise DeviceError("invalid_token")
    return token


def clean_platform(value) -> str:
    platform = str(value or "").strip().lower()
    if platform not in PushPlatform.values:
        raise DeviceError("invalid_platform")
    return platform


def clean_muted_types(value) -> list:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise DeviceError("invalid_muted_types")
    unknown = [item for item in value if item not in NotificationType.values]
    if unknown:
        raise DeviceError("invalid_muted_types")
    return sorted(set(value))


def register_device(*, user, token, platform, app_version="", language="", muted_types=None) -> tuple[PushDevice, bool]:
    """``(cihaz, yaradıldımı)``. ``muted_types=None`` → mövcud seçim saxlanır."""
    token = clean_token(token)
    platform = clean_platform(platform)
    muted = None if muted_types is None else clean_muted_types(muted_types)
    now = timezone.now()
    fields = {
        "user": user,
        "platform": platform,
        "app_version": str(app_version or "")[:40],
        "language": str(language or "").strip()[:10],
        "is_active": True,
        "last_seen": now,
        "deactivated_at": None,
        "deactivated_reason": "",
    }
    if muted is not None:
        fields["muted_types"] = muted
    with bypass_rls(), transaction.atomic():
        device, created = PushDevice.objects.update_or_create(token=token, defaults=fields)
        _enforce_limit(user, keep_pk=device.pk, now=now)
    return device, created


def _enforce_limit(user, *, keep_pk, now) -> None:
    active = list(
        PushDevice.objects.filter(user=user, is_active=True)
        .exclude(pk=keep_pk)
        .order_by("-last_seen", "-pk")
        .values_list("pk", flat=True)
    )
    surplus = active[MAX_DEVICES_PER_USER - 1 :]
    if surplus:
        PushDevice.objects.filter(pk__in=surplus).update(
            is_active=False, deactivated_at=now, deactivated_reason="limit"
        )


def unregister_device(*, user, token) -> int:
    """Çıxışda: bu istifadəçinin həmin tokenli cihazını deaktiv edir; qaytarır: dəyişən sətir sayı (0/1)."""
    token = clean_token(token)
    with bypass_rls():
        return PushDevice.objects.filter(user=user, token=token, is_active=True).update(
            is_active=False, deactivated_at=timezone.now(), deactivated_reason="logout"
        )


def user_devices(*, user) -> list[PushDevice]:
    with bypass_rls():
        return list(PushDevice.objects.filter(user=user, is_active=True).order_by("-last_seen"))


def device_payload(device: PushDevice) -> dict:
    """API cavabı — token QAYTARILMIR (yalnız son 6 simvol, tətbiq «bu cihaz» sətrini tanısın)."""
    return {
        "id": device.pk,
        "platform": device.platform,
        "app_version": device.app_version,
        "language": device.language,
        "muted_types": device.muted_types if isinstance(device.muted_types, list) else [],
        "token_tail": device.token[-6:],
        "last_seen": device.last_seen.isoformat() if device.last_seen else None,
        "last_success_at": device.last_success_at.isoformat() if device.last_success_at else None,
    }


__all__ = [
    "MAX_DEVICES_PER_USER",
    "DeviceError",
    "device_payload",
    "register_device",
    "unregister_device",
    "user_devices",
]
