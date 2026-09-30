"""«Akademik fəaliyyət» qeydlərinin qoşma faylı (2026-10-01, sahib).

Hər qeyddə ən çox BİR fayl: PDF və ya şəkil (JPG/JPEG/PNG/WEBP), ≤ 10 MB.

Yoxlama iki qatdır:
1. ``core.upload_security.validate_uploaded_file`` — uzantı ağ siyahısı, bloklanan
   tiplər (SVG/HTML/icra olunan), ikiqat uzantı, markup/magic-bytes yoxlaması;
2. burada SƏRT məzmun yoxlaması — PDF faylın ``%PDF-`` başlığı ilə BAŞLAMALIDIR,
   şəkil Pillow ilə açılıb ``verify()`` olunur və format uzantı ailəsinə uyğun
   gəlməlidir.

Şəkillər yenidən kodlanır (EXIF/GPS metadata atılır, oriyentasiya düzəlir, çox
böyük ölçü 4000px-ə endirilir) və siyahılar üçün kiçik JPEG önizləmə (thumb)
yaradılır — profil səhifəsi tam faylı yükləmir.

GİRİŞ SİYASƏTİ (``check_attachment_media_access``): qoşma, qeydin özünü açıq
profildə görə bilən HƏR DAXİL OLMUŞ istifadəçiyə açıqdır (açıq profil bütün
qeydləri göstərir); anonim baxan faylı görmür — ``protected_media`` onu girişə
yönləndirir (avatarlarla eyni qayda). Yol reyestrdə olmayan və ya başqa qeydə
aid fayl → 404. Başqa məxfi media prefikslərinə toxunulmur.
"""

from __future__ import annotations

import io
import logging
import posixpath
import unicodedata

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils.translation import pgettext

from apps.accounts.academic_models import ACADEMIC_ATTACHMENT_PREFIX, AcademicProfileItem
from core.upload_security import validate_uploaded_file

logger = logging.getLogger(__name__)

Kind = AcademicProfileItem.Kind

#: Fayl qoşmaq mənalı olan növlər. «Tədris etdiyi fənn» və «Peşəkar təcrübə»
#: DAXİL DEYİL (sənəd yoxdur / şəxsi iş sənədləri açıq profilə çıxmasın).
ATTACHMENT_KINDS = frozenset(
    {
        Kind.EDUCATION,
        Kind.PUBLICATION,
        Kind.BOOK,
        Kind.CONFERENCE,
        Kind.PROJECT,
        Kind.PATENT,
        Kind.CERTIFICATE,
        Kind.AWARD,
    }
)

MAX_ATTACHMENT_MB = 10
MAX_ATTACHMENT_BYTES = MAX_ATTACHMENT_MB * 1024 * 1024
PDF_EXTENSION = ".pdf"
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
ALLOWED_EXTENSIONS = frozenset({PDF_EXTENSION} | IMAGE_EXTENSIONS)

#: Uzantı → Pillow formatları (MPO = kameraların çox-kadrlı JPEG-i).
_IMAGE_FORMATS = {
    ".jpg": {"JPEG", "MPO"},
    ".jpeg": {"JPEG", "MPO"},
    ".png": {"PNG"},
    ".webp": {"WEBP"},
}
#: Yenidən kodlanmış faylın formatı → saxlanma uzantısı.
_FORMAT_EXTENSION = {"JPEG": ".jpg", "MPO": ".jpg", "PNG": ".png", "WEBP": ".webp"}

#: Şəkil sərhədləri: dekompressiya bombasına qarşı piksel tavanı və saxlanan
#: şəklin ən uzun tərəfi; önizləmə ölçüsü.
MAX_IMAGE_PIXELS = 50_000_000
MAX_IMAGE_SIDE = 4000
THUMB_SIDE = 320
DISPLAY_NAME_MAX = 120


def kind_allows_attachment(kind) -> bool:
    return str(kind or "") in {str(k.value) for k in ATTACHMENT_KINDS}


def _error(message):
    return False, None, message


def _extension(name) -> str:
    return posixpath.splitext(str(name or "").lower())[1]


def _display_name(raw_name) -> str:
    """Göstəriş adı: yalnız əsas ad, idarəedici simvollar atılır, uzunluq tavanı."""
    base = posixpath.basename(str(raw_name or "").replace("\\", "/"))
    base = "".join(ch for ch in base if unicodedata.category(ch)[0] != "C")
    base = " ".join(base.split())
    if len(base) > DISPLAY_NAME_MAX:
        stem, ext = posixpath.splitext(base)
        base = stem[: DISPLAY_NAME_MAX - len(ext)] + ext
    return base


def _read_head(uploaded, size=16):
    try:
        uploaded.seek(0)
        return uploaded.read(size) or b""
    finally:
        uploaded.seek(0)


def _invalid_content():
    return pgettext("accounts.academic_items.attachment", "Faylın məzmunu PDF və ya şəkil formatına uyğun deyil.")


def _process_image(uploaded, extension):
    """Şəkli yoxlayır, metadata-sız yenidən kodlayır, önizləmə yaradır.

    Qaytarır: (ok, (main_bytes, main_ext, thumb_bytes) | None, xəta).
    """
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        uploaded.seek(0)
        with Image.open(uploaded) as probe:
            detected = (probe.format or "").upper()
            width, height = probe.size
            probe.verify()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return _error(_invalid_content())
    if detected not in _IMAGE_FORMATS.get(extension, set()):
        return _error(_invalid_content())
    if not width or not height or width * height > MAX_IMAGE_PIXELS:
        return _error(
            pgettext("accounts.academic_items.attachment", "Şəklin ölçüsü çox böyükdür — daha kiçik şəkil seçin.")
        )

    try:
        uploaded.seek(0)
        with Image.open(uploaded) as source:
            if detected in {"JPEG", "MPO"}:
                source.draft("RGB", (MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            image = ImageOps.exif_transpose(source)
            image.load()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return _error(_invalid_content())
    finally:
        uploaded.seek(0)

    if max(image.size) > MAX_IMAGE_SIDE:
        image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))

    out_format = "JPEG" if detected == "MPO" else detected
    if out_format == "JPEG" and image.mode not in {"RGB", "L"}:
        image = image.convert("RGB")
    main = io.BytesIO()
    save_kwargs = {"JPEG": {"quality": 88, "optimize": True}, "WEBP": {"quality": 88}, "PNG": {}}[out_format]
    image.save(main, format=out_format, **save_kwargs)

    thumb_image = image.copy()
    thumb_image.thumbnail((THUMB_SIDE, THUMB_SIDE))
    if thumb_image.mode in {"RGBA", "LA", "P"}:
        rgba = thumb_image.convert("RGBA")
        thumb_image = Image.new("RGB", rgba.size, (255, 255, 255))
        thumb_image.paste(rgba, mask=rgba.split()[-1])
    elif thumb_image.mode != "RGB":
        thumb_image = thumb_image.convert("RGB")
    thumb = io.BytesIO()
    thumb_image.save(thumb, format="JPEG", quality=80, optimize=True)
    return True, (main.getvalue(), _FORMAT_EXTENSION[out_format], thumb.getvalue()), ""


def prepare_attachment(uploaded):
    """Yüklənən faylı yoxlayıb saxlanmaya hazırlayır.

    Qaytarır: (ok, payload | None, xəta). ``payload`` —
    ``{"content", "extension", "thumb", "name", "size"}`` (thumb yalnız şəkildə).
    """
    if uploaded is None:
        return _error(pgettext("accounts.academic_items.attachment", "Fayl seçilməyib."))
    size = int(getattr(uploaded, "size", 0) or 0)
    if size <= 0:
        return _error(pgettext("accounts.academic_items.attachment", "Fayl boşdur."))
    if size > MAX_ATTACHMENT_BYTES:
        return _error(
            pgettext("accounts.academic_items.attachment", "Fayl %(limit)s MB-dan böyük ola bilməz.")
            % {"limit": MAX_ATTACHMENT_MB}
        )
    extension = _extension(getattr(uploaded, "name", ""))
    if extension not in ALLOWED_EXTENSIONS:
        return _error(
            pgettext("accounts.academic_items.attachment", "Yalnız PDF və ya şəkil (JPG, PNG, WEBP) yükləmək olar.")
        )

    try:
        validate_uploaded_file(
            uploaded,
            allowed_extensions=ALLOWED_EXTENSIONS,
            max_size_mb=MAX_ATTACHMENT_MB,
            # MIME brauzerin iddiasıdır — qərar məzmun imzasına görə verilir (aşağıda).
            allowed_mime_types={"application/pdf", "application/x-pdf", "application/octet-stream"},
            allowed_mime_prefixes=("image/",),
            verify_image=False,
        )
    except ValidationError as exc:
        return _error(exc.messages[0] if exc.messages else _invalid_content())

    display_name = _display_name(getattr(uploaded, "name", "")) or f"file{extension}"
    if extension == PDF_EXTENSION:
        head = _read_head(uploaded, 16).lstrip(b"\xef\xbb\xbf \t\r\n")
        if not head.startswith(b"%PDF-"):
            return _error(_invalid_content())
        uploaded.seek(0)
        payload = {"content": uploaded, "extension": PDF_EXTENSION, "thumb": None, "name": display_name, "size": size}
        return True, payload, ""

    ok, processed, error = _process_image(uploaded, extension)
    if not ok:
        return _error(error)
    main_bytes, main_ext, thumb_bytes = processed
    payload = {
        "content": ContentFile(main_bytes),
        "extension": main_ext,
        "thumb": ContentFile(thumb_bytes),
        "name": display_name,
        "size": len(main_bytes),
    }
    return True, payload, ""


def _stored_names(item):
    return [name for name in (str(item.attachment.name or ""), str(item.attachment_thumb.name or "")) if name]


def delete_files_on_commit(storage, names):
    """Fayl(lar)ı tranzaksiya UĞURLA bitəndən sonra saxlanmadan silir."""
    names = [name for name in names if name and name.startswith(ACADEMIC_ATTACHMENT_PREFIX)]
    if not names:
        return

    def _delete():
        for name in names:
            try:
                storage.delete(name)
            except Exception:  # noqa: BLE001 — fayl itkisi qeydi bloklamamalıdır
                logger.warning("academic attachment delete failed: %s", name, exc_info=True)

    transaction.on_commit(_delete)


def apply_attachment(item, payload):
    """Qeydə yeni faylı yazır (save=False); köhnə fayl adlarını qaytarır.

    Çağıran ``item.save()``-dən sonra köhnə adları ``delete_files_on_commit``-ə verir.
    """
    old_names = _stored_names(item)
    item.attachment.save(f"attachment{payload['extension']}", payload["content"], save=False)
    if payload.get("thumb") is not None:
        item.attachment_thumb.save("thumb.jpg", payload["thumb"], save=False)
    else:
        item.attachment_thumb = ""
    item.attachment_name = payload["name"][:160]
    item.attachment_size = int(payload.get("size") or 0) or None
    return old_names


def clear_attachment(item):
    """Qeydin qoşmasını boşaldır (save=False); köhnə fayl adlarını qaytarır."""
    old_names = _stored_names(item)
    item.attachment = ""
    item.attachment_thumb = ""
    item.attachment_name = ""
    item.attachment_size = None
    return old_names


def discard_new_files(item, old_names):
    """Qeyd yadda saxlanmayanda YENİ yazılmış faylları geri silir."""
    for name in _stored_names(item):
        if name not in old_names:
            try:
                item.attachment.storage.delete(name)
            except Exception:  # noqa: BLE001
                logger.warning("academic attachment rollback delete failed: %s", name, exc_info=True)


ATTACHMENT_FIELDS = ["attachment", "attachment_thumb", "attachment_name", "attachment_size"]


def cleanup_files_on_item_delete(sender, instance, **kwargs):  # noqa: ARG001 — siqnal imzası
    """``post_delete``: qeyd (və ya istifadəçi kaskadı) silinəndə faylları da sil."""
    delete_files_on_commit(instance.attachment.storage, _stored_names(instance))


def check_attachment_media_access(user, path: str) -> bool:
    """``academic_attachments/<user_id>/<fayl>`` üçün ``protected_media`` siyasəti.

    Yalnız HAZIRDA hansısa qeydə bağlı fayl verilir (köhnə/silinmiş → 404).
    Sahib həmişə görür; başqa daxil olmuş istifadəçi — qeyd açıq profildə
    göründüyü üçün — fayl növü qoşmaya icazəlidirsə görür.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    clean = posixpath.normpath(str(path or "")).lstrip("/")
    parts = clean.split("/")
    if len(parts) != 3 or f"{parts[0]}/" != ACADEMIC_ATTACHMENT_PREFIX or not parts[1].isdigit():
        return False
    item = (
        AcademicProfileItem.objects.filter(user_id=int(parts[1]))
        .filter(Q(attachment=clean) | Q(attachment_thumb=clean))
        .only("id", "user_id", "kind")
        .first()
    )
    if item is None:
        return False
    if item.user_id == user.id:
        return True
    return kind_allows_attachment(item.kind)
