"""Pano (clipboard) / sürükləmə ilə yapışdırılan şəkil → idxal stash-ı.

W8 2026-09-14 (w3import yarımçıq 7, NIGHT_WAVES §5 maddə 11). Toplu sual iş
masasında müəllim mətni yazarkən şəkli panodan yapışdırır (Ctrl+V) və ya
redaktora sürüşdürür. Şəkil DOCX bundle formatında (`kind="docx"`, schema 3,
`source.origin="paste"`) stash-a yazılır, mətnə isə `[[img:N]]` markeri düşür —
sonrakı hər şey (`bind_import_manifest` → `bind_docx_manifest`,
`attach_import_media_batch` → `attach_docx_media_batch`, önizləmə PNG) DOCX ilə
EYNİ kod yoludur; yeni manifest növü, yeni yükləmə yolu yoxdur.

Validasiya da DOCX-dəki ilə eynidir: `normalize_image_bytes` (raster format,
≤12 MB, ≤50 MP, >2000 px kiçildilir, EXIF silinir), `MAX_IMAGES` tavanı.
Manifest oxu-dəyiş-yaz olduğu üçün eyni token-ə PARALEL yapışdırma JS tərəfdə
növbəyə salınır (bax `bulk_workbench_paste.js`).
"""

from __future__ import annotations

import base64
import hashlib
import io
import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.translation import pgettext

from PIL import Image

from apps.exams.services.import_media_docx import (
    MANIFEST_KIND,
    MANIFEST_VERSION,
    _image_filename,
    _write_manifest,
    is_docx_manifest,
)
from apps.exams.services.import_media_store import (
    assert_manifest_scope,
    bundle_name,
    clear_stash,
    delete_name,
    delete_tree,
    load_raw_manifest,
    metadata_id,
    prefix,
    read_upload,
    valid_token,
)
from apps.exams.services.parsing.docx_reader import (
    MARKER_TEMPLATE,
    MAX_IMAGE_BYTES,
    MAX_IMAGES,
    normalize_image_bytes,
)
from apps.exams.services.parsing.extraction.safety import _ensure_within_size_limit

SOURCE_ORIGIN = "paste"
_ERR = "exams.service.import.paste.error"
_THUMB_SIDE = 96


@dataclass(frozen=True)
class PastedImage:
    token: str
    index: int
    marker: str
    content_type: str
    width: int
    height: int
    thumb: str  # data: URL — çip önizləməsi (səhifə yenidən render olunanda da qalsın)


def _thumb_data_url(data: bytes) -> str:
    """Çip üçün ≤96 px PNG thumbnail (manifestdə saxlanır ki, preview POST-dan sonra bərpa olunsun)."""

    with Image.open(io.BytesIO(data)) as opened:
        opened.load()
        thumb = opened.convert("RGBA")
        thumb.thumbnail((_THUMB_SIDE, _THUMB_SIDE), Image.LANCZOS)
        buffer = io.BytesIO()
        thumb.save(buffer, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _new_manifest(*, owner_id: object, organization_id: object) -> dict[str, object]:
    manifest: dict[str, object] = {
        "kind": MANIFEST_KIND,
        "schema_version": MANIFEST_VERSION,
        # Yapışdırma bundle-ında «sənəd mətni» yoxdur — canonical mətn markerlərin
        # siyahısıdır (boş ola bilməz: `get_stashed_import_text` boş mətni rədd edir).
        "canonical_text": "",
        "images": [],
        "warnings": [],
        "formula_count": 0,
        "formula_fallbacks": [],
        "bindings": {},
        "source": {"origin": SOURCE_ORIGIN, "filename": "clipboard"},
    }
    for key, value in (("owner_id", metadata_id(owner_id)), ("organization_id", metadata_id(organization_id))):
        if value is not None:
            manifest["source"][key] = value
    return manifest


def _load_appendable(token: str, *, owner_id: object, organization_id: object) -> dict[str, object]:
    """Mövcud token-i yalnız DOCX-formatlı (docx/pdf-fallback/paste) bundle olanda qəbul et."""

    if not valid_token(token):
        raise ValueError(pgettext(_ERR, "paste_token_invalid"))
    manifest = load_raw_manifest(token)
    if not is_docx_manifest(manifest) or manifest.get("schema_version") != MANIFEST_VERSION:
        # PDF vizual-first bundle: suallar şəkil kəsikləridir, mətn sr-only —
        # ona şəkil yapışdırmağın mənası yoxdur; müəllim «Təmizlə» ilə başlasın.
        raise ValueError(pgettext(_ERR, "paste_into_visual_bundle"))
    assert_manifest_scope(manifest, owner_id=owner_id, organization_id=organization_id)
    if not isinstance(manifest.get("images"), list):
        raise ValueError("DOCX manifestində şəkil siyahısı yoxdur")
    return manifest


def _next_index(manifest: Mapping[str, object]) -> int:
    indices = [
        entry.get("index")
        for entry in manifest.get("images") or ()
        if isinstance(entry, Mapping) and isinstance(entry.get("index"), int)
    ]
    return (max(indices) if indices else 0) + 1


def stash_pasted_image(
    uploaded_file,
    *,
    token: str = "",
    owner_id: object = None,
    organization_id: object = None,
) -> PastedImage:
    """Bir şəkli stash-a əlavə et: mövcud token-ə (DOCX formatlı) və ya yeni bundle-a."""

    _ensure_within_size_limit(uploaded_file, MAX_IMAGE_BYTES)
    original = read_upload(uploaded_file)
    normalized = normalize_image_bytes(original)
    if normalized is None:
        raise ValueError(pgettext(_ERR, "paste_image_unsupported"))
    data, content_type, width, height = normalized

    manifest = None
    if token:
        try:
            manifest = _load_appendable(token, owner_id=owner_id, organization_id=organization_id)
        except FileNotFoundError:
            # Köhnəlmiş token (yadda saxlanandan / retention-dan sonra silinib) —
            # gizli sahədə qalıb; yeni bundle ilə davam edilir.
            manifest = None
    created_bundle = manifest is None
    if created_bundle:
        manifest = _new_manifest(owner_id=owner_id, organization_id=organization_id)
        token = uuid.uuid4().hex

    images = manifest["images"]
    if len(images) >= MAX_IMAGES:
        raise ValueError(pgettext(_ERR, "paste_image_limit").format(limit=MAX_IMAGES))

    index = _next_index(manifest)
    marker = MARKER_TEMPLATE.format(index=index)
    images.append(
        {
            "index": index,
            "name": _image_filename(index, content_type),
            "content_type": content_type,
            "width": width,
            "height": height,
            "sha256": hashlib.sha256(data).hexdigest(),
            "origin": SOURCE_ORIGIN,
            "thumb": _thumb_data_url(data),
        }
    )
    canonical = str(manifest.get("canonical_text") or "")
    manifest["canonical_text"] = f"{canonical}\n{marker}".strip("\n")

    name = bundle_name(token, _image_filename(index, content_type))
    saved = ""
    try:
        saved = default_storage.save(name, ContentFile(data))
        if saved != name:
            raise OSError(f"Storage canonical adı saxlamadı: {name}")
        _write_manifest(token, manifest)
    except Exception:
        if saved:
            delete_name(saved)
        if created_bundle:
            delete_tree(prefix(token), suppress_errors=True)
        raise
    return PastedImage(
        token=token,
        index=index,
        marker=marker,
        content_type=content_type,
        width=width,
        height=height,
        thumb=str(images[-1]["thumb"]),
    )


def remove_pasted_image(
    token: str,
    index: int,
    *,
    owner_id: object = None,
    organization_id: object = None,
) -> str:
    """Şəkli stash-dan çıxar; bundle boşalırsa tam silinir və ``""`` qaytarılır."""

    manifest = _load_appendable(token, owner_id=owner_id, organization_id=organization_id)
    images = [entry for entry in manifest["images"] if isinstance(entry, Mapping)]
    keep = [entry for entry in images if entry.get("index") != index]
    if len(keep) == len(images):
        raise ValueError(pgettext(_ERR, "paste_image_not_found"))
    if not keep:
        clear_stash(token)
        return ""
    for entry in images:
        if entry.get("index") == index:
            delete_name(bundle_name(token, str(entry.get("name"))))
    manifest["images"] = keep
    marker = MARKER_TEMPLATE.format(index=index)
    manifest["canonical_text"] = "\n".join(
        line for line in str(manifest.get("canonical_text") or "").splitlines() if line.strip() != marker
    )
    # Köhnə bağlama həmin indeksə istinad edə bilər — növbəti preview yenidən qurur.
    manifest["bindings"] = {}
    _write_manifest(token, manifest)
    return token


def pasted_image_chips(
    token: str,
    *,
    owner_id: object = None,
    organization_id: object = None,
) -> list[dict[str, object]]:
    """Səhifə yenidən render olunanda çipləri bərpa etmək üçün ``[{index, marker, thumb}]``.

    Yalnız yapışdırılmış (``origin="paste"``) şəkillər — DOCX-dən çıxarılanların
    öz kart önizləməsi var. Token yoxdursa / oxunmursa boş siyahı (fail-soft).
    """

    if not valid_token(token):
        return []
    try:
        manifest = _load_appendable(token, owner_id=owner_id, organization_id=organization_id)
    except (OSError, ValueError):
        return []
    chips: list[dict[str, object]] = []
    for entry in manifest["images"]:
        if not isinstance(entry, Mapping) or entry.get("origin") != SOURCE_ORIGIN:
            continue
        index = entry.get("index")
        if not isinstance(index, int):
            continue
        chips.append(
            {
                "index": index,
                "marker": MARKER_TEMPLATE.format(index=index),
                "thumb": str(entry.get("thumb") or ""),
            }
        )
    return chips


__all__ = [
    "PastedImage",
    "SOURCE_ORIGIN",
    "pasted_image_chips",
    "remove_pasted_image",
    "stash_pasted_image",
]
