"""PDF mətn-fallback idxal bundle-ı: gömülü raster şəkillər DOCX bundle formatında.

W4 2026-09-14 (w3import yarımçıq 6). Layout inamsız PDF (`stash_math_images`
→ `LayoutConfidenceError`) mətn yoluna düşür; əvvəl sənədin şəkilləri itirdi.
İndi `stash_pdf_image_bundle` həmin faylın mətnini (mövcud təhlükəsizlik +
highlight yolu — `extract_text_from_upload`) və `parsing/pdf_images` ilə sual
bölgəsinə bağlanmış şəkilləri **DOCX manifest formatında** (`kind="docx"`,
schema 3, `source.origin="pdf"`) stash-a yazır. Sonrakı hər şey —
`bind_import_manifest` → `bind_docx_manifest`, `attach_import_media_batch` →
`attach_docx_media_batch`, preview PNG — DOCX ilə EYNİ kod yoludur; yeni
manifest növü yaradılmır.

Şəkil yoxdursa ``None`` qaytarır ki, çağıran (``try_visual_import``) köhnə
mətn yoluna düşsün (davranış dəyişmir, ikinci mətn çıxarışı olmur — şəkil
skanı ucuzdur və mətndən ƏVVƏL aparılır).
"""

from __future__ import annotations

import hashlib
import logging
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.exams.services.import_media_docx import (
    MANIFEST_KIND,
    MANIFEST_VERSION,
    _image_filename,
    _write_manifest,
)
from apps.exams.services.import_media_store import (
    bundle_name,
    delete_name,
    delete_tree,
    metadata_id,
    prefix,
    read_upload,
)
from apps.exams.services.parsing.extraction.constants import MAX_UPLOAD_BYTES
from apps.exams.services.parsing.extraction.safety import _ensure_within_size_limit
from apps.exams.services.parsing.pdf_images import extract_pdf_question_images, pdf_has_raster_images

logger = logging.getLogger(__name__)

SOURCE_ORIGIN = "pdf"


def _rewind(uploaded_file) -> None:
    try:
        uploaded_file.seek(0)
    except Exception:  # noqa: BLE001 — seek dəstəkləməyən stream-lər
        pass


def stash_pdf_image_bundle(
    uploaded_file,
    *,
    owner_id: object = None,
    organization_id: object = None,
) -> tuple[str, str] | None:
    """Mətn-fallback PDF-in şəkillərini bundle-a yaz → ``(markerli mətn, token)``; şəkilsiz → ``None``."""

    _ensure_within_size_limit(uploaded_file, MAX_UPLOAD_BYTES)
    original = read_upload(uploaded_file)
    if not pdf_has_raster_images(original):
        return None

    # Mətn mövcud PDF yolundan gəlir: imza, aktiv kontent, şifrə yoxlamaları,
    # highlight ilə düz cavab işarələməsi — hamısı olduğu kimi.
    from apps.exams.services.parsing import extract_text_from_upload

    _rewind(uploaded_file)
    text = extract_text_from_upload(uploaded_file)
    extract = extract_pdf_question_images(original, text)
    if not extract.images:
        return None

    raw_name = str(getattr(uploaded_file, "name", "") or "").replace("\\", "/")
    manifest: dict[str, object] = {
        "kind": MANIFEST_KIND,
        "schema_version": MANIFEST_VERSION,
        "canonical_text": extract.text,
        "images": [
            {
                "index": image.index,
                "name": _image_filename(image.index, image.content_type),
                "content_type": image.content_type,
                "width": image.width,
                "height": image.height,
                "sha256": hashlib.sha256(image.data).hexdigest(),
            }
            for image in extract.images
        ],
        "warnings": list(extract.warnings),
        "formula_count": 0,
        "formula_fallbacks": [],
        "bindings": {},
        "source": {
            "origin": SOURCE_ORIGIN,
            "filename": raw_name.rsplit("/", 1)[-1] or "source.pdf",
            "original_byte_size": len(original),
            "original_sha256": hashlib.sha256(original).hexdigest(),
        },
    }
    for key, value in (("owner_id", metadata_id(owner_id)), ("organization_id", metadata_id(organization_id))):
        if value is not None:
            manifest["source"][key] = value

    token = uuid.uuid4().hex
    saved: list[str] = []
    try:
        for image in extract.images:
            name = bundle_name(token, _image_filename(image.index, image.content_type))
            actual = default_storage.save(name, ContentFile(image.data))
            saved.append(actual)
            if actual != name:
                raise OSError(f"Storage canonical adı saxlamadı: {name}")
        _write_manifest(token, manifest)
    except Exception:
        for name in reversed(saved):
            delete_name(name)
        delete_tree(prefix(token), suppress_errors=True)
        raise
    logger.info("PDF mətn-fallback bundle: %s şəkil, %s yerləşim", len(extract.images), len(extract.placements))
    return extract.text, token


__all__ = ["SOURCE_ORIGIN", "stash_pdf_image_bundle"]
