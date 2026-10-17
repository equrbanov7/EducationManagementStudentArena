"""Profil şəklinin (avatar) yükləmədə kiçildilməsi — PERF-2 H5 (2026-10-17).

PROBLEM
-------
Avatar olduğu kimi saxlanılırdı (10 MB-a qədər; lokal mediada 8.9 MB PNG-lər var),
navbar isə onu 22–40 px-də, HƏR səhifədə göstərir.

HƏLL
----
Yoxlamadan (``validate_profile_avatar_upload``) KEÇMİŞ fayl Pillow ilə açılır:

* PİKSEL TAVANI (``AVATAR_MAX_PIXELS``, 40M) DEKODDAN ƏVVƏL yoxlanılır və
  ``DecompressionBombWarning`` xətaya çevrilir — 445 KB-lıq 12000×12000 PNG əvvəl
  1,75 GB yaddaş tuturdu (review 2026-10-17). Tavanı aşan şəkli yoxlama özü rədd edir
  (``avatar_pixels_error``); burada da ``AvatarImageError`` atılır, ORİJİNAL saxlanmır;
* əvvəl kiçildilir (``thumbnail`` yerində), SONRA EXIF oriyentasiyası tətbiq olunur
  və rəng rejimi çevrilir; metadata atılır (EXIF/GPS köçmür), ICC profili saxlanılır;
* uzun tərəf ``AVATAR_MAX_SIDE`` (512 px) ilə məhdudlaşır (kiçik şəkil böyüdülmür);
* WebP-yə (q ``AVATAR_WEBP_QUALITY``) kodlaşdırılır — şəffaflıq saxlanılır;
  animasiyalı GIF-in ilk kadrı götürülür.

Başqa emal xətasında (nadir format / zədəli məlumat) — ORİJİNAL (artıq yoxlanılmış)
fayl saxlanılır və xəbərdarlıq loglanır: yükləmə istifadəçi üçün uğursuz olmur.

Mövcud fayllar üçün: ``manage.py shrink_avatars`` (default — dry-run).
"""

from __future__ import annotations

import logging
import warnings
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

AVATAR_MAX_SIDE = 512
AVATAR_MAX_PIXELS = 40_000_000
AVATAR_WEBP_QUALITY = 82
AVATAR_FORMAT_EXTENSION = ".webp"
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
AVATAR_PIXELS_ERROR = "Şəklin ölçüləri çox böyükdür (ən çox 40 meqapiksel). Daha kiçik şəkil seçin."

# Palitralı / 1-bit rejimdə Pillow `resize` NEAREST-ə keçir (pilləli kənarlar) — bunlar
# kiçildilmədən ƏVVƏL çevrilir (yaddaş piksel tavanı ilə məhduddur).
_PRE_CONVERT_MODES = ("P", "PA", "1")


class AvatarImageError(ValueError):
    """Şəkil təhlükəsizlik tavanını aşır — saxlanmamalıdır."""


def _has_alpha(image) -> bool:
    if image.mode in ("RGBA", "LA", "PA"):
        return True
    return image.mode == "P" and "transparency" in image.info


def _pixels_ok(size) -> bool:
    width, height = size
    return width > 0 and height > 0 and width * height <= AVATAR_MAX_PIXELS


def avatar_pixels_error(width, height) -> str:
    """Yoxlama üçün: ölçülər tavanı aşırsa istifadəçi mesajı, əks halda boş sətir."""
    return "" if _pixels_ok((width or 0, height or 0)) else AVATAR_PIXELS_ERROR


def encode_avatar_bytes(fileobj) -> bytes:
    """Şəkli oxuyub kiçildilmiş WebP baytlarını qaytarır.

    Tavanı aşan / «bomba» şəkil üçün ``AvatarImageError``, digər xətalarda Pillow istisnası.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with Image.open(fileobj) as source:
                if not _pixels_ok(source.size):  # yalnız başlıq oxunub — dekod yoxdur
                    raise AvatarImageError(AVATAR_PIXELS_ERROR)
                icc_profile = source.info.get("icc_profile")
                alpha = _has_alpha(source)
                image = source.convert("RGBA" if alpha else "RGB") if source.mode in _PRE_CONVERT_MODES else source
                # JPEG-də dekodu birbaşa kiçik ölçüdə aparır (yaddaş + CPU); digər formatlarda no-op.
                image.draft("RGB", (AVATAR_MAX_SIDE * 2, AVATAR_MAX_SIDE * 2))
                image.thumbnail((AVATAR_MAX_SIDE, AVATAR_MAX_SIDE), Image.Resampling.LANCZOS)
                if image is source:
                    # Palitralı formatlarda (GIF / palitralı PNG) EXIF oriyentasiyası olmur.
                    image = ImageOps.exif_transpose(image)
                image = image.convert("RGBA" if alpha or _has_alpha(image) else "RGB")
                buffer = BytesIO()
                save_kwargs = {"format": "WEBP", "quality": AVATAR_WEBP_QUALITY, "method": 4}
                if icc_profile:
                    save_kwargs["icc_profile"] = icc_profile
                image.save(buffer, **save_kwargs)
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise AvatarImageError(AVATAR_PIXELS_ERROR) from exc
    return buffer.getvalue()


def normalize_avatar_upload(uploaded):
    """Yoxlanılmış yükləməni kiçik WebP ``ContentFile``-a çevirir.

    Tavanı aşan şəkil üçün ``AvatarImageError`` yuxarı ötürülür (yoxlama onu onsuz da
    rədd edir); digər emal xətasında orijinal (yoxlanılmış) fayl qaytarılır.
    """
    if uploaded is None:
        return uploaded
    try:
        uploaded.seek(0)
        data = encode_avatar_bytes(uploaded)
    except AvatarImageError:
        raise
    except Exception:  # noqa: BLE001 — emal uğursuzsa yoxlanılmış orijinal saxlanılır
        logger.warning("avatar normalize failed; storing the original upload", exc_info=True)
        try:
            uploaded.seek(0)
        except Exception:  # noqa: BLE001
            pass
        return uploaded
    stem = Path(getattr(uploaded, "name", "") or "avatar").stem or "avatar"
    return ContentFile(data, name=f"{stem}{AVATAR_FORMAT_EXTENSION}")


def avatar_version(updated_at) -> str:
    """Avatar URL-inin ``?v=`` dəyəri — ``updated_at`` MİKROSANİYƏ dəqiqliyi ilə (tam ədəd).

    Əvvəl saniyə idi (``date:'U'``): eyni saniyədə iki dəyişiklik eyni immutable URL-i
    paylaşa bilərdi. Float yox, tam hesab — şablon və view eyni sətri alır.
    """
    if not updated_at:
        return ""
    delta = updated_at - _EPOCH if updated_at.tzinfo else updated_at - _EPOCH.replace(tzinfo=None)
    return str(delta // timedelta(microseconds=1))
