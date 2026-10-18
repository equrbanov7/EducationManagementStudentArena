"""Video yükləmələri üçün məzmun imzası (magic bytes) — 2026-10-19.

``core.upload_security`` şəkil/sənəd imzalarını yoxlayır, video konteynerlərini isə tanımır
(``.mp4`` adı ilə istənilən məzmun keçirdi). Burada iki ailə var:

* **ISO BMFF / QuickTime** (``.mp4``, ``.m4v``, ``.mov``): fayl «box»-larla başlayır — ilk 4 bayt
  ölçü, sonrakı 4 bayt box tipi. Demək olar hər fayl ``ftyp`` ilə açılır (iPhone ``.MOV``: ``ftypqt  ``);
  köhnə QuickTime yazıcıları birbaşa ``moov``/``mdat``/``wide``/``free``/``skip`` ilə başlayır.
* **WebM / Matroska** (``.webm``): EBML başlığı ``1A 45 DF A3``.

Kodek yoxlanmır (HEVC/H.264 fərqi brauzerin işidir) — məqsəd «video adı altında başqa məzmun»u
(icra olunan fayl, HTML, arxiv) rədd etməkdir.
"""

from __future__ import annotations

import mimetypes
import struct

VIDEO_EXTENSIONS = frozenset({".mp4", ".m4v", ".mov", ".webm"})

_ISO_BMFF_EXTENSIONS = frozenset({".mp4", ".m4v", ".mov"})
_ISO_BMFF_FIRST_BOXES = frozenset({b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip", b"pnot"})
_EBML_MAGIC = b"\x1a\x45\xdf\xa3"

#: İmza üçün kifayət edən baş hissə.
VIDEO_SNIFF_BYTES = 64


def _iso_bmff_ok(head: bytes) -> bool:
    if len(head) < 8 or head[4:8] not in _ISO_BMFF_FIRST_BOXES:
        return False
    (size,) = struct.unpack(">I", head[:4])
    # 0 = «faylın sonuna qədər», 1 = 64-bit ölçü sonra gəlir; qalanları ən azı başlığın özü (8 bayt).
    return size in (0, 1) or size >= 8


def video_signature_ok(extension: str, head: bytes) -> bool:
    """``extension`` (nöqtəli, kiçik hərf) üçün ``head`` gözlənilən video konteyneri ilə başlayırmı."""
    extension = (extension or "").lower()
    if extension in _ISO_BMFF_EXTENSIONS:
        return _iso_bmff_ok(head)
    if extension == ".webm":
        return head.startswith(_EBML_MAGIC)
    return False


#: Prod image (python:3.12-slim) ``/etc/mime.types`` daşımır — Python-un daxili cədvəlində ``.m4v`` YOXDUR,
#: ``protected_media`` onu ``application/octet-stream`` + ``attachment`` kimi verirdi. Çatışmayanlar əlavə olunur.
_VIDEO_MIME_TYPES = {".mp4": "video/mp4", ".m4v": "video/x-m4v", ".mov": "video/quicktime", ".webm": "video/webm"}


def register_video_mimetypes() -> None:
    """İdempotent: yalnız ``mimetypes`` tanımayan video uzantılarını qeydiyyata alır."""
    for extension, mime_type in _VIDEO_MIME_TYPES.items():
        if mimetypes.guess_type(f"video{extension}")[0] is None:
            mimetypes.add_type(mime_type, extension)


__all__ = ["VIDEO_EXTENSIONS", "VIDEO_SNIFF_BYTES", "register_video_mimetypes", "video_signature_ok"]
