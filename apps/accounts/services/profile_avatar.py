"""Profil şəkli (avatar) — yerində yükləmə / dəyişmə / silmə (2026-10-01, sahib).

«Profil şəkli tərəfini yenidən düzəlt … şəkli qoymaq olduğu kimi silmək də
mümkün olsun». Yoxlama mövcud ``validate_profile_avatar_upload``-dır (uzantı ağ
siyahısı, məzmun imzası, ölçü tavanı); fayl adı təsadüfiləşdirilir.

Köhnə fayl dəyişdiriləndə və ya silinəndə saxlanmadan da silinir — amma yalnız
tranzaksiya UĞURLA bitəndən sonra (``on_commit``): DB geri qayıdarsa fayl itmir.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.urls import reverse

from core.upload_security import randomize_uploaded_filename

from .profile_actions import validate_profile_avatar_upload

logger = logging.getLogger(__name__)

AVATAR_PREFIX = "avatars/"


def schedule_file_delete(storage, name, *, keep=""):
    """``name`` faylını commit-dən sonra silir (yalnız ``avatars/`` altında)."""
    name = str(name or "")
    if not name or name == str(keep or "") or not name.startswith(AVATAR_PREFIX):
        return

    def _delete():
        try:
            storage.delete(name)
        except Exception:  # noqa: BLE001 — köhnə fayl qalığı istifadəçini bloklamamalıdır
            logger.warning("profile avatar delete failed: %s", name, exc_info=True)

    transaction.on_commit(_delete)


def replace_avatar(profile, uploaded):
    """Yeni şəkli yoxlayıb yazır; (ok, event, xəta). event: "uploaded" | "replaced"."""
    error = validate_profile_avatar_upload(uploaded)
    if error:
        return False, "", error
    randomize_uploaded_filename(uploaded)
    old_name = str(profile.avatar.name or "") if profile.avatar else ""
    storage = profile.avatar.storage
    profile.avatar = uploaded
    with transaction.atomic():
        profile.save(update_fields=["avatar", "updated_at"])
        schedule_file_delete(storage, old_name, keep=profile.avatar.name)
    return True, ("replaced" if old_name else "uploaded"), ""


def remove_avatar(profile):
    """Şəkli silir (initials-ə qayıdır); şəkil yox idisə False qaytarır."""
    if not profile.avatar:
        return False
    old_name = str(profile.avatar.name or "")
    storage = profile.avatar.storage
    profile.avatar = None
    with transaction.atomic():
        profile.save(update_fields=["avatar", "updated_at"])
        schedule_file_delete(storage, old_name)
    return True


def initials_for(user):
    """Şablonlardakı initials məntiqinin güzgüsü (ad + soyad baş hərfləri)."""
    first = (user.first_name or user.username or "")[:1]
    last = (user.last_name or "")[:1]
    return (first + last).upper()


def avatar_state(user, profile):
    """JS-in bütün avatar yerlərini (başlıq, redaktə, navbar) yeniləməsi üçün vəziyyət."""
    has_avatar = bool(profile.avatar)
    url = ""
    if has_avatar:
        url = f"{reverse('accounts:profile_avatar', args=[user.id])}?v={int(profile.updated_at.timestamp())}"
    return {
        "has_avatar": has_avatar,
        "avatar_url": url,
        "initials": initials_for(user),
        "initial": initials_for(user)[:1],
    }
