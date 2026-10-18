"""Kurs resursu yükləməsi — tip üzrə format/ölçü siyasəti və server yoxlaması (2026-10-19).

Sahib: «Video seçdim, IMG_0189.MOV yüklədim → «Xəta baş verdi»; seçdiyim resursa görə format aşağıda
görünsün». Kök səbəb: nginx-in qlobal ``client_max_body_size 64M`` limiti iPhone videosunu HTML 413 ilə
kəsirdi, modal JS-i isə JSON gözlədiyi üçün ümumi toast göstərirdi; ipucu da hər tip üçün eyni idi.

Bu modul TƏK mənbədir: modalın ipucu/``accept`` atributu (``policy_for_template``), serverin
yoxlaması (``validate_resource_file``) və view-un gövdə tavanı (``UPLOAD_BODY_MAX_BYTES``) buradan
oxunur. nginx ``location ^~ /courses/resource-upload/`` limiti (``docker/nginx/nginx.conf``) bu
tavandan böyük olmalıdır — ``apps/courses/tests/test_resource_upload_2026_10_19.py`` yoxlayır.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from django.core.exceptions import ValidationError
from django.utils.translation import pgettext

from core.upload_security import randomize_uploaded_filename, validate_uploaded_file
from core.upload_video import VIDEO_SNIFF_BYTES, video_signature_ok

MB = 1024 * 1024

VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".m4v")
DOCUMENT_EXTENSIONS = (".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".odt", ".txt")
ARCHIVE_EXTENSIONS = (".zip", ".rar", ".7z")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")

_OCTET = "application/octet-stream"  # brauzer tipi tanımayanda göndərir — imza ayrıca yoxlanır
_DOCUMENT_MIMES = frozenset(
    {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.oasis.opendocument.text",
        "text/plain",
        _OCTET,
    }
)
_ARCHIVE_MIMES = frozenset(
    {
        "application/zip",
        "application/x-zip-compressed",
        "application/vnd.rar",
        "application/x-rar-compressed",
        "application/x-rar",
        "application/x-7z-compressed",
    }
)


@dataclass(frozen=True)
class ResourceUploadPolicy:
    kind: str
    extensions: tuple[str, ...]
    max_mb: int
    mime_types: frozenset
    mime_prefixes: tuple[str, ...]

    @property
    def max_bytes(self) -> int:
        return self.max_mb * MB

    @property
    def display_formats(self) -> str:
        """«MP4, MOV, WEBM, M4V» — ``.jpeg`` ayrıca göstərilmir (JPG onu əhatə edir)."""
        return ", ".join(ext.lstrip(".").upper() for ext in self.extensions if ext != ".jpeg")

    @property
    def accept(self) -> str:
        return ",".join(self.extensions)


#: Ölçülər nginx/ASGI məhdudiyyətlərinə görə seçilib: Daphne sorğu gövdəsini app-a ötürərkən
#: TAM yaddaşa növbələyir (``daphne.http_protocol`` — 8 KB parçalar, limitsiz ``asyncio.Queue``),
#: yəni 200 MB video replika başına ~200 MB RSS sıçrayışıdır (APP_MEM_LIMIT 2 GB). Daha böyük
#: videolar üçün əvvəlcə uvicorn (geri təzyiqli axın) və ya obyekt anbarına birbaşa yükləmə lazımdır.
POLICIES = {
    "video": ResourceUploadPolicy("video", VIDEO_EXTENSIONS, 200, frozenset({_OCTET, "application/mp4"}), ("video/",)),
    "document": ResourceUploadPolicy("document", DOCUMENT_EXTENSIONS, 50, _DOCUMENT_MIMES, ()),
    "file": ResourceUploadPolicy(
        "file",
        DOCUMENT_EXTENSIONS + ARCHIVE_EXTENSIONS + IMAGE_EXTENSIONS,
        100,
        _DOCUMENT_MIMES | _ARCHIVE_MIMES,
        ("image/",),
    ),
}

FILE_KINDS = frozenset(POLICIES)
LINK_KIND = "link"

#: Multipart zərfi + mətn sahələri (başlıq/təsvir; qlobal mətn limiti 5 MB-dır) üçün ehtiyat.
UPLOAD_ENVELOPE_BYTES = 8 * MB
#: View gövdəni parse etməzdən ƏVVƏL ``CONTENT_LENGTH``-i bununla müqayisə edir. nginx limiti (210m) bundan böyükdür.
UPLOAD_BODY_MAX_BYTES = max(policy.max_bytes for policy in POLICIES.values()) + UPLOAD_ENVELOPE_BYTES

_TEXT_MARKUP_PREFIXES = (b"<svg", b"<?xml", b"<!doctype", b"<html", b"<script", b"<body", b"<head", b"<iframe")


def kind_label(kind: str) -> str:
    labels = {
        "file": pgettext("courses.resource_type", "Fayl"),
        "link": pgettext("courses.resource_type", "Link"),
        "video": pgettext("courses.resource_type", "Video"),
        "document": pgettext("courses.resource_type", "Sənəd"),
    }
    return labels.get(kind, kind)


def format_mb(size_bytes: int) -> str:
    """312.0 → «312», 200.4 → «200,4» (AZ onluq vergülü)."""
    value = round(size_bytes / MB, 1)
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def hint_text(kind: str) -> str:
    policy = POLICIES[kind]
    text = pgettext("courses.resource_upload", "Dəstəklənən formatlar: {formats} · maks. {max_mb} MB").format(
        formats=policy.display_formats, max_mb=policy.max_mb
    )
    if kind == "video":
        text += " · " + pgettext(
            "courses.resource_upload", "iPhone videosu: mümkünsə MP4 seçin (MOV bəzi brauzerlərdə oynamır)"
        )
    return text


def policy_for_template() -> dict:
    """Modal üçün hər tipin ``accept``/ipucu/limiti (data-atributlara yazılır)."""
    data = {
        kind: {
            "accept": p.accept,
            "hint": hint_text(kind),
            "max_bytes": p.max_bytes,
            "max_mb": p.max_mb,
            "extensions": " ".join(p.extensions),
            "formats": p.display_formats,
        }
        for kind, p in POLICIES.items()
    }
    data[LINK_KIND] = {"accept": "", "hint": "", "max_bytes": 0, "max_mb": 0, "extensions": "", "formats": ""}
    return data


def _extension(file_name: str) -> str:
    return PurePosixPath((file_name or "").lower()).suffix


def _suggestion(extension: str, kind: str) -> str:
    """Uzantı başqa tipə aiddirsə düzgün tipi göstər."""
    for other in ("video", "document", "file"):
        if other != kind and extension in POLICIES[other].extensions:
            return " " + pgettext("courses.resource_upload", "Bu fayl üçün «{kind}» tipini seçin.").format(
                kind=kind_label(other)
            )
    return ""


def _read_head(uploaded_file, size: int) -> bytes:
    try:
        position = uploaded_file.tell()
    except Exception:
        position = None
    try:
        uploaded_file.seek(0)
        return uploaded_file.read(size) or b""
    except Exception:
        return b""
    finally:
        if position is not None:
            try:
                uploaded_file.seek(position)
            except Exception:
                pass


def _content_ok(extension: str, head: bytes) -> bool:
    if extension in VIDEO_EXTENSIONS:
        return video_signature_ok(extension, head)
    if extension == ".odt":
        return head.startswith(b"PK\x03\x04")
    if extension == ".txt":
        # İkili fayl (NUL baytı) və ya «.txt» adı altında HTML/SVG markup — rədd. UTF-16 BOM-lu
        # mətn NUL daşıyır, onu ikili saymırıq.
        is_utf16 = head.startswith((b"\xff\xfe", b"\xfe\xff"))
        if b"\x00" in head and not is_utf16:
            return False
        stripped = head.lstrip(b"\xef\xbb\xbf\xff\xfe\x00 \t\r\n").lower()
        return not stripped.startswith(_TEXT_MARKUP_PREFIXES)
    return True  # PDF/ofis/arxiv/şəkil imzalarını core.upload_security yoxlayır


def validate_resource_file(uploaded_file, kind: str) -> None:
    """Tip üzrə uzantı → ölçü → məzmun imzası → ``core.upload_security`` (MIME/bloklanan tiplər).

    Xəta mesajları müəllimə nəyin səhv olduğunu və nə edəcəyini deyir — ümumi «Xəta baş verdi» yox.
    """
    policy = POLICIES[kind]
    extension = _extension(getattr(uploaded_file, "name", ""))
    if extension not in policy.extensions:
        shown = extension or pgettext("courses.resource_upload", "(uzantısız)")
        message = pgettext(
            "courses.resource_upload", "Bu format «{kind}» üçün qəbul edilmir: {ext}. İcazə verilənlər: {formats}"
        ).format(kind=kind_label(kind), ext=shown, formats=policy.display_formats)
        raise ValidationError(message + _suggestion(extension, kind))

    size = int(getattr(uploaded_file, "size", 0) or 0)
    if size <= 0:
        raise ValidationError(pgettext("courses.resource_upload", "Fayl boşdur."))
    if size > policy.max_bytes:
        raise ValidationError(
            pgettext("courses.resource_upload", "Fayl çox böyükdür: {size} MB (maks. {max_mb} MB)").format(
                size=format_mb(size), max_mb=policy.max_mb
            )
        )

    head = _read_head(uploaded_file, max(VIDEO_SNIFF_BYTES, 512))
    if not _content_ok(extension, head):
        raise ValidationError(
            pgettext(
                "courses.resource_upload",
                "Faylın məzmunu {ext} formatına uyğun deyil — fayl zədələnib və ya uzantısı dəyişdirilib.",
            ).format(ext=extension)
        )

    validate_uploaded_file(
        uploaded_file,
        allowed_extensions=set(policy.extensions),
        max_size_mb=policy.max_mb,
        allowed_mime_types=set(policy.mime_types),
        allowed_mime_prefixes=policy.mime_prefixes,
        verify_image=False,
    )


def prepare_resource_file(uploaded_file, kind: str):
    """Yoxla və saxlanmadan əvvəl adı təsadüfi UUID ilə əvəz et (orijinal ad diskdə qalmır)."""
    validate_resource_file(uploaded_file, kind)
    return randomize_uploaded_filename(uploaded_file)


__all__ = [
    "FILE_KINDS",
    "LINK_KIND",
    "POLICIES",
    "UPLOAD_BODY_MAX_BYTES",
    "VIDEO_EXTENSIONS",
    "format_mb",
    "hint_text",
    "kind_label",
    "policy_for_template",
    "prepare_resource_file",
    "validate_resource_file",
]
