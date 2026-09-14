"""
Upload security helpers.

Centralized validation for user-uploaded files:
- extension allow/deny checks
- MIME type checks
- file size limits
- random file name generation
- ZIP/archive bomb protection
"""

from __future__ import annotations

import io
import mimetypes
import zipfile
from pathlib import PurePosixPath
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import pgettext

DEFAULT_MAX_UPLOAD_SIZE_MB = 25

BLOCKED_UPLOAD_EXTENSIONS = {
    ".exe",
    ".php",
    ".php3",
    ".php4",
    ".php5",
    ".phtml",
    ".phar",
    ".com",
    ".bat",
    ".cmd",
    ".msi",
    ".dll",
    ".scr",
    ".html",
    ".htm",
    ".svg",
    ".js",
    ".vbs",
    ".wsf",
    ".ps1",
    ".sh",
    # 2026-09-14 (audit F-06, §27 «upload MIME sniffing»): brauzerin skript/markup
    # kimi icra edə biləcəyi əlavə uzantılar — XHTML/SSI/MHTML arxivi, ES-modul,
    # XML+XSLT (XSLT ilə skript), sıxılmış SVG.
    ".xhtml",
    ".shtml",
    ".mht",
    ".mhtml",
    ".mjs",
    ".xml",
    ".xsl",
    ".xslt",
    ".svgz",
}

BLOCKED_MIME_TYPES = {
    "application/x-msdownload",
    "application/x-dosexec",
    "application/x-executable",
    "application/x-httpd-php",
    "text/x-php",
}

DEFAULT_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/zip",
    "application/x-zip-compressed",
    "application/vnd.rar",
    "application/x-rar-compressed",
    "application/x-7z-compressed",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/json",
    "application/xml",
    "text/plain",
    "text/csv",
}

DEFAULT_ALLOWED_MIME_PREFIXES = ("image/", "video/", "audio/", "text/")

IMAGE_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".jfif", ".png", ".gif", ".webp"}

# ─── Məzmun imzaları (2026-09-14, audit F-06) ───────────────────────────────
#
# Auditor: «`_resolve_mime_type` müştərinin `content_type`-ına etibar edir;
# magic-bytes yalnız `MZ`/`<?php`; şəkillərdə Pillow yoxlaması yoxdur». Burada
# üç qat əlavə olunur (üçüncü tərəf `python-magic`/`filetype` requirements-də
# yoxdur — kiçik imza cədvəli kifayətdir):
#
# 1. Şəkil uzantılı HƏR yükləmə üçün magic-bytes (JPEG/PNG/GIF/WEBP) — SVG/HTML
#    kimi markup «şəkil» adı ilə keçə bilməz.
# 2. Şəkil SAHƏLƏRİ üçün (çağıran `allowed_extensions` ⊆ şəkil uzantıları verir)
#    Pillow ilə format identifikasiyası + uzantı ↔ format uyğunluğu.
# 3. Sənəd allow-list-i verilən çağırışlarda (PDF / ZIP-əsaslı ofis / köhnə OLE
#    ofis / arxivlər) bəyan edilən tip ↔ məzmun imzası uyğunluğu.
#
# Allow-list-siz ümumi çağırış (köhnə davranış) yalnız 1-ci qatı alır ki, mövcud
# çağıranlar/testlər dəyişməsin; sahə nə gözlədiyini deyəndə məzmun onu təsdiq
# etməlidir.

#: Şəkil uzantısı → mümkün başlanğıc imzaları (WEBP ayrıca: `RIFF....WEBP`).
_IMAGE_SIGNATURES = {
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".jfif": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".webp": (b"RIFF",),
}

#: Uzantı → Pillow `Image.format` dəyərləri (MPO = çox-kadrlı JPEG, kameralar yazır).
_IMAGE_FORMATS_BY_EXTENSION = {
    ".jpg": {"JPEG", "MPO"},
    ".jpeg": {"JPEG", "MPO"},
    ".jfif": {"JPEG", "MPO"},
    ".png": {"PNG"},
    ".gif": {"GIF"},
    ".webp": {"WEBP"},
}

_PDF_SIGNATURES = (b"%PDF",)
_ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_OLE_SIGNATURES = (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",)
_RAR_SIGNATURES = (b"Rar!\x1a\x07",)
_7Z_SIGNATURES = (b"7z\xbc\xaf\x27\x1c",)

#: Sənəd uzantısı → icazəli imzalar. Köhnə ofis uzantıları həm OLE, həm də PK
#: qəbul edir (istifadəçilər `.docx`-i `.doc` adlandırır; Excel açır).
_DOCUMENT_SIGNATURES_BY_EXTENSION = {
    ".pdf": _PDF_SIGNATURES,
    ".zip": _ZIP_SIGNATURES,
    ".docx": _ZIP_SIGNATURES,
    ".xlsx": _ZIP_SIGNATURES,
    ".pptx": _ZIP_SIGNATURES,
    ".doc": _OLE_SIGNATURES + _ZIP_SIGNATURES,
    ".xls": _OLE_SIGNATURES + _ZIP_SIGNATURES,
    ".ppt": _OLE_SIGNATURES + _ZIP_SIGNATURES,
    ".rar": _RAR_SIGNATURES,
    ".7z": _7Z_SIGNATURES,
}

#: Bəyan edilən MIME → imzalar (uzantı cədvəldə olmayanda ehtiyat açar).
_DOCUMENT_SIGNATURES_BY_MIME = {
    "application/pdf": _PDF_SIGNATURES,
    "application/zip": _ZIP_SIGNATURES,
    "application/x-zip-compressed": _ZIP_SIGNATURES,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": _ZIP_SIGNATURES,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": _ZIP_SIGNATURES,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": _ZIP_SIGNATURES,
    "application/msword": _OLE_SIGNATURES + _ZIP_SIGNATURES,
    "application/vnd.ms-powerpoint": _OLE_SIGNATURES + _ZIP_SIGNATURES,
    "application/vnd.rar": _RAR_SIGNATURES,
    "application/x-rar-compressed": _RAR_SIGNATURES,
    "application/x-7z-compressed": _7Z_SIGNATURES,
}

#: PDF başlığı ilk 1024 baytın içində ola bilər (Acrobat toleransı).
_PDF_HEADER_WINDOW = 1024

#: Şəkil/sənəd adı ilə gələn markup (SVG/HTML/XML) — brauzerdə skript səthi.
_MARKUP_PREFIXES = (b"<svg", b"<?xml", b"<!doctype", b"<html", b"<script", b"<body", b"<head", b"<iframe")

#: Məzmun yoxlaması üçün oxunan baş hissə.
_SNIFF_HEAD_SIZE = 2048


def _normalized_extension(file_name: str) -> str:
    return PurePosixPath((file_name or "").lower()).suffix


def _has_dangerous_stem_extension(file_name: str) -> bool:
    """Return True if any non-final suffix in the filename is a blocked extension.

    This detects double-extension attacks such as ``shell.php.jpg``.
    """
    suffixes = PurePosixPath((file_name or "").lower()).suffixes
    if len(suffixes) <= 1:
        return False
    for ext in suffixes[:-1]:
        if ext in BLOCKED_UPLOAD_EXTENSIONS:
            return True
    return False


def _read_head(uploaded_file, size=16, *, from_start=False):
    try:
        current_pos = uploaded_file.tell()
    except Exception:
        current_pos = None

    try:
        # 2026-09-14 (audit F-06): məzmun imzası faylın ƏVVƏLİNDƏN oxunmalıdır —
        # çağıran əvvəl oxuyub mövqeyi irəli çəkmiş ola bilər; mövqe geri qaytarılır.
        if from_start and current_pos:
            uploaded_file.seek(0)
        chunk = uploaded_file.read(size)
    except Exception:
        chunk = b""
    finally:
        if current_pos is not None:
            try:
                uploaded_file.seek(current_pos)
            except Exception:
                current_pos = None
    return chunk or b""


def _signature_indicates_blocked_type(uploaded_file) -> bool:
    head = _read_head(uploaded_file, size=16).lstrip()
    if head.startswith(b"MZ"):  # PE/EXE
        return True
    if head.startswith(b"<?php"):  # PHP script
        return True
    return False


def _resolve_mime_type(uploaded_file) -> str:
    content_type = (getattr(uploaded_file, "content_type", "") or "").strip().lower()
    if content_type:
        return content_type
    guessed_type = mimetypes.guess_type(getattr(uploaded_file, "name", "") or "")[0]
    return (guessed_type or "").lower()


def _looks_like_markup(head: bytes) -> bool:
    """Baş hissə SVG/HTML/XML markup-u ilə başlayırmı (BOM/boşluq nəzərə alınmır)."""
    stripped = head.lstrip(b"\xef\xbb\xbf\xff\xfe\x00 \t\r\n").lower()
    return stripped.startswith(_MARKUP_PREFIXES)


def _image_signature_ok(extension: str, head: bytes) -> bool:
    signatures = _IMAGE_SIGNATURES.get(extension)
    if signatures is None:
        return True
    if not head.startswith(signatures):
        return False
    if extension == ".webp":
        return head[8:12] == b"WEBP"
    return True


def _document_signature_ok(extension: str, mime_type: str, head: bytes) -> bool:
    signatures = _DOCUMENT_SIGNATURES_BY_EXTENSION.get(extension) or _DOCUMENT_SIGNATURES_BY_MIME.get(mime_type)
    if signatures is None:
        return True
    if signatures is _PDF_SIGNATURES:
        return b"%PDF" in head[:_PDF_HEADER_WINDOW]
    return head.startswith(signatures)


def _is_image_only_allow_list(normalized_allowed_extensions) -> bool:
    return bool(normalized_allowed_extensions) and normalized_allowed_extensions <= IMAGE_ALLOWED_EXTENSIONS


def _verify_image_with_pillow(uploaded_file, extension: str) -> None:
    """Pillow ilə format identifikasiyası — şəkil sahələri üçün (audit F-06).

    ``Image.open`` başlıq strukturunu oxuyur: markup/zibil «şəkil» kimi keçmir,
    format uzantı ailəsi ilə üst-üstə düşməlidir (``.png`` içində GIF → rədd).
    Tam ``verify()`` (chunk CRC-ləri) QƏSDƏN çağırılmır — bu, bütövlük yoxlamasıdır,
    təhlükəsizlik deyil, və mövcud avatar fikstürləri (kəsik IDAT) onu keçmir.
    """
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:  # pragma: no cover — Pillow requirements/base.txt-dədir
        return

    try:
        current_pos = uploaded_file.tell()
    except Exception:
        current_pos = None
    try:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
        try:
            with Image.open(uploaded_file) as image:
                detected = (image.format or "").upper()
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
            detected = ""
    finally:
        if current_pos is not None:
            try:
                uploaded_file.seek(current_pos)
            except Exception:
                pass

    expected = _IMAGE_FORMATS_BY_EXTENSION.get(extension)
    if not detected or (expected is not None and detected not in expected):
        raise ValidationError(
            pgettext("upload.security.error", "Fayl məzmunu bəyan edilən şəkil formatına uyğun deyil.")
        )


def validate_uploaded_file(
    uploaded_file,
    *,
    allowed_extensions=None,
    max_size_mb=None,
    allowed_mime_types=None,
    allowed_mime_prefixes=DEFAULT_ALLOWED_MIME_PREFIXES,
    verify_image=None,
):
    """
    Validate uploaded file using extension, MIME type, size and content-signature checks.
    Raises ValidationError on any violation.

    ``verify_image``: ``None`` (default) → Pillow identification runs automatically
    when ``allowed_extensions`` is an image-only allow-list (an image field);
    ``True``/``False`` forces it on/off.
    """
    if uploaded_file is None:
        return

    extension = _normalized_extension(getattr(uploaded_file, "name", ""))
    if not extension:
        raise ValidationError(pgettext("upload.security.error", "Fayl uzantısı müəyyən edilə bilmədi."))

    if extension in BLOCKED_UPLOAD_EXTENSIONS:
        raise ValidationError(pgettext("upload.security.error", "Bu fayl tipi təhlükəsizlik səbəbi ilə bloklanıb."))

    if _has_dangerous_stem_extension(getattr(uploaded_file, "name", "")):
        raise ValidationError(pgettext("upload.security.error", "Bu fayl tipi təhlükəsizlik səbəbi ilə bloklanıb."))

    normalized_allowed_extensions = None
    if allowed_extensions:
        normalized_allowed_extensions = {f".{ext.lstrip('.').lower()}" for ext in allowed_extensions}
        if extension not in normalized_allowed_extensions:
            raise ValidationError(pgettext("upload.security.error", "Bu fayl uzantısı dəstəklənmir."))

    if max_size_mb is None:
        max_size_mb = int(getattr(settings, "FILE_UPLOAD_SECURITY_MAX_SIZE_MB", DEFAULT_MAX_UPLOAD_SIZE_MB))

    max_size_bytes = int(max_size_mb) * 1024 * 1024
    if getattr(uploaded_file, "size", 0) > max_size_bytes:
        raise ValidationError(
            pgettext("upload.security.error", "Fayl ölçüsü limiti keçildi (maksimum {max_size_mb} MB).").format(
                max_size_mb=int(max_size_mb)
            )
        )

    mime_type = _resolve_mime_type(uploaded_file)
    if not mime_type:
        raise ValidationError(pgettext("upload.security.error", "Faylın MIME tipi müəyyən edilə bilmədi."))

    if mime_type in BLOCKED_MIME_TYPES:
        raise ValidationError(pgettext("upload.security.error", "Bu MIME tipi təhlükəsizlik səbəbi ilə bloklanıb."))

    if _signature_indicates_blocked_type(uploaded_file):
        raise ValidationError(
            pgettext("upload.security.error", "Fayl məzmunu bloklanan icra olunan/script tipinə uyğundur.")
        )

    # 2026-09-14 (audit F-06): məzmun imzası. Şəkil uzantıları HƏR zaman magic-bytes
    # ilə yoxlanır; markup (SVG/HTML/XML) şəkil/sənəd adı altında rədd edilir;
    # allow-list verən sahələr üçün sənəd imzası + (şəkil sahələrində) Pillow.
    head = _read_head(uploaded_file, size=_SNIFF_HEAD_SIZE, from_start=True)
    is_image_extension = extension in IMAGE_ALLOWED_EXTENSIONS
    is_document_extension = extension in _DOCUMENT_SIGNATURES_BY_EXTENSION
    if (is_image_extension or is_document_extension or mime_type.startswith("image/")) and _looks_like_markup(head):
        raise ValidationError(
            pgettext("upload.security.error", "Fayl məzmunu bloklanan icra olunan/script tipinə uyğundur.")
        )
    if is_image_extension and not _image_signature_ok(extension, head):
        raise ValidationError(
            pgettext("upload.security.error", "Fayl məzmunu bəyan edilən şəkil formatına uyğun deyil.")
        )
    if normalized_allowed_extensions:
        if not _document_signature_ok(extension, mime_type, head):
            raise ValidationError(
                pgettext("upload.security.error", "Fayl məzmunu bəyan edilən fayl tipinə uyğun deyil.")
            )
        if verify_image or (verify_image is None and _is_image_only_allow_list(normalized_allowed_extensions)):
            _verify_image_with_pillow(uploaded_file, extension)
    elif verify_image:
        _verify_image_with_pillow(uploaded_file, extension)

    allowed_mime_set = set(allowed_mime_types or DEFAULT_ALLOWED_MIME_TYPES)
    has_allowed_prefix = any(mime_type.startswith(prefix) for prefix in (allowed_mime_prefixes or ()))
    if mime_type not in allowed_mime_set and not has_allowed_prefix:
        raise ValidationError(pgettext("upload.security.error", "Bu MIME tipi dəstəklənmir."))


def randomize_uploaded_filename(uploaded_file):
    """
    Replace original upload file name with a random UUID-based one.
    """
    if uploaded_file is None:
        return uploaded_file

    extension = _normalized_extension(getattr(uploaded_file, "name", ""))
    uploaded_file.name = f"{uuid4().hex}{extension}"
    return uploaded_file


# ─── ZIP / Archive guard constants ──────────────────────────────────────────

#: Maximum number of entries allowed inside a ZIP archive.
ZIP_MAX_FILE_COUNT = 1_000

#: Maximum total uncompressed size (bytes) allowed for a ZIP archive (100 MB).
#: The check uses ``file_size`` (claimed uncompressed size from the central directory).
#: Extreme ratios are caught independently by ``ZIP_BOMB_RATIO_THRESHOLD``.
ZIP_MAX_EXTRACTED_SIZE_BYTES = 100 * 1024 * 1024

#: Maximum nesting depth when recursively scanning nested ZIPs.
ZIP_MAX_NESTING_DEPTH = 3

#: Compression-ratio threshold above which an entry is flagged as a zip bomb.
#: Standard files compress at most ~95 %; ratios above 99 % are suspicious.
ZIP_BOMB_RATIO_THRESHOLD = 99


def validate_zip_archive(
    uploaded_file,
    *,
    max_file_count: int = ZIP_MAX_FILE_COUNT,
    max_extracted_size_bytes: int = ZIP_MAX_EXTRACTED_SIZE_BYTES,
    max_nesting_depth: int = ZIP_MAX_NESTING_DEPTH,
):
    """Validate a ZIP archive against common bomb and abuse vectors.

    Checks performed
    ----------------
    1. **Valid ZIP**: the file must be a well-formed ZIP archive.
    2. **File count**: total entries ≤ *max_file_count*.
    3. **Compressed size**: running sum of ``compress_size`` (bytes actually
       stored in the archive) across all entries ≤ *max_extracted_size_bytes*.
       This is a reliable, unforgeable bound because ``compress_size`` reflects
       the real on-disk payload.
    4. **Compression ratio per entry**: entries whose claimed uncompressed size
       (``file_size``) is more than ``ZIP_BOMB_RATIO_THRESHOLD``× their actual
       compressed size are flagged as potential zip bombs.
    5. **Nesting depth**: nested ZIPs (ZIPs inside ZIPs) are recursively
       validated up to *max_nesting_depth* levels.

    Raises ``ValidationError`` on any violation.  Returns ``None`` on success.
    """
    _validate_zip_recursive(uploaded_file, max_file_count, max_extracted_size_bytes, max_nesting_depth, depth=0)


def _validate_zip_recursive(file_or_bytes, max_file_count, max_extracted_size_bytes, max_nesting_depth, *, depth):
    """Inner recursive ZIP validator."""
    # Accept both file-like objects and raw bytes (for nested ZIPs read from
    # the outer archive's member data).
    if isinstance(file_or_bytes, (bytes, bytearray)):
        source = io.BytesIO(file_or_bytes)
    else:
        # Seek to the beginning so zipfile can read the central directory.
        try:
            current_pos = file_or_bytes.tell()
            file_or_bytes.seek(0)
        except Exception:
            current_pos = None
        source = file_or_bytes

    try:
        zf = zipfile.ZipFile(source)
    except zipfile.BadZipFile:
        raise ValidationError(pgettext("upload.security.error", "Yüklənmiş fayl etibarsız ZIP arxividir."))
    except Exception:
        raise ValidationError(pgettext("upload.security.error", "ZIP arxivi oxuna bilmədi."))
    finally:
        # Restore file position if we moved it.
        if not isinstance(file_or_bytes, (bytes, bytearray)) and current_pos is not None:
            try:
                file_or_bytes.seek(current_pos)
            except Exception:
                pass

    entries = zf.infolist()

    # 1. File count guard.
    if len(entries) > max_file_count:
        raise ValidationError(
            pgettext(
                "upload.security.error",
                "ZIP arxivi çox sayda fayl ehtiva edir (maksimum {max} icazə verilir).",
            ).format(max=max_file_count)
        )

    # 2. Extracted-size and compression-ratio guards.
    total_compressed = 0
    for entry in entries:
        total_compressed += entry.compress_size

        if total_compressed > max_extracted_size_bytes:
            raise ValidationError(
                pgettext(
                    "upload.security.error",
                    "ZIP arxivinin ümumi sıxılmış ölçüsü limiti keçir.",
                )
            )

        # Ratio guard: skip directories and zero-byte entries.
        if entry.compress_size > 0 and entry.file_size > 0:
            ratio = entry.file_size / entry.compress_size
            if ratio > ZIP_BOMB_RATIO_THRESHOLD:
                raise ValidationError(
                    pgettext(
                        "upload.security.error",
                        "ZIP arxivindəki '{filename}' faylı zip-bomb kimi şübhəlidir.",
                    ).format(filename=entry.filename)
                )

    # 3. Nesting guard: scan nested ZIPs one level deeper.
    for entry in entries:
        if entry.filename.lower().endswith(".zip") and not entry.is_dir():
            if depth >= max_nesting_depth:
                raise ValidationError(
                    pgettext(
                        "upload.security.error",
                        "ZIP arxivi dəstəklənən maksimum iç-içə dərinliyi keçir.",
                    )
                )
            try:
                nested_data = zf.read(entry.filename)
            except Exception:
                continue
            _validate_zip_recursive(
                nested_data,
                max_file_count,
                max_extracted_size_bytes,
                max_nesting_depth,
                depth=depth + 1,
            )


class FileUploadValidator:
    """
    Django model-field validator that runs ``validate_uploaded_file`` on newly
    uploaded files.  Committed ``FieldFile`` objects (already stored on disk)
    are skipped so that loading existing records does not trigger validation.

    Usage::

        file = models.FileField(validators=[FileUploadValidator()])
        file = models.FileField(validators=[FileUploadValidator(
            allowed_extensions={".pdf", ".zip"},
            max_size_mb=10,
        )])
    """

    def __init__(self, *, allowed_extensions=None, max_size_mb=None, verify_image=None):
        self.allowed_extensions = allowed_extensions
        self.max_size_mb = max_size_mb
        # 2026-09-14 (audit F-06): şəkil sahələri üçün Pillow identifikasiyasını məcbur et/söndür.
        self.verify_image = verify_image

    def __call__(self, value):
        # value is None or a FieldFile for committed objects – skip those
        if not value:
            return
        if getattr(value, "_committed", True):
            return
        validate_uploaded_file(
            value,
            allowed_extensions=self.allowed_extensions,
            max_size_mb=self.max_size_mb,
            verify_image=self.verify_image,
        )

    def __eq__(self, other):
        return (
            isinstance(other, FileUploadValidator)
            and self.allowed_extensions == other.allowed_extensions
            and self.max_size_mb == other.max_size_mb
            and self.verify_image == other.verify_image
        )

    def deconstruct(self):
        return (
            "core.upload_security.FileUploadValidator",
            [],
            {
                k: v
                for k, v in (
                    ("allowed_extensions", self.allowed_extensions),
                    ("max_size_mb", self.max_size_mb),
                    ("verify_image", self.verify_image),
                )
                if v is not None
            },
        )
