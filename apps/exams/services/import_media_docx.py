"""DOCX idxal bundle-ı: şəkil stash-ı, parse-a bağlama, modelə yazma, preview.

W3 2026-09-14. PDF axını «vizual-first»dir (sual hissələri şəkil kimi kəsilir,
mətn əvəz olunur). DOCX axını «mətn-first»dir: mətn (düsturlar LaTeX kimi)
bazaya düşür, sənədin içindəki şəkillər isə sual/variantın ``image`` sahəsinə
ƏLAVƏ bağlanır (``image_replaces_text=False``) — Moodle Word import / QTI
``<img>`` yanaşması.

Bundle: ``question_imports/<token>/manifest.json`` (``kind="docx"``) +
``img_<N>.png|jpg``. Bağlama (``bindings``) preview/save zamanı parse olunmuş
``media_refs``-dən qurulur və manifestə yazılır ki, ``_save_bank_questions``
yalnız ``(source_index, instance)`` ötürəndə də şəkillər tapılsın.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import uuid
from collections.abc import Mapping, MutableMapping, Sequence

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils.translation import pgettext

from PIL import Image, ImageDraw

from apps.exams.services.import_media_store import (
    MANIFEST_NAME,
    assert_manifest_scope,
    bundle_name,
    delete_name,
    delete_tree,
    load_raw_manifest,
    metadata_id,
    prefix,
    read_storage,
    read_upload,
)
from apps.exams.services.parsing.docx_reader import read_docx
from apps.exams.services.parsing.extraction.constants import MAX_UPLOAD_BYTES
from apps.exams.services.parsing.extraction.safety import _ensure_within_size_limit

logger = logging.getLogger(__name__)

MANIFEST_KIND = "docx"
MANIFEST_VERSION = 3
_MAX_IMAGES_PER_TARGET = 4
_STACK_GAP = 8
_LABEL_WIDTH = 44
_WARN_CTX = "exams.service.parsing.docx.warning"


def is_docx_manifest(manifest: Mapping[str, object]) -> bool:
    return isinstance(manifest, Mapping) and manifest.get("kind") == MANIFEST_KIND


def _validate(manifest: object) -> dict[str, object]:
    if not is_docx_manifest(manifest):
        raise ValueError("DOCX idxal manifesti deyil")
    if manifest.get("schema_version") != MANIFEST_VERSION:
        raise ValueError("DOCX manifest versiyası dəstəklənmir")
    images = manifest.get("images")
    if not isinstance(images, list):
        raise ValueError("DOCX manifestində şəkil siyahısı yoxdur")
    if not isinstance(manifest.get("source"), Mapping):
        raise ValueError("İdxal manifestində source metadata yoxdur")
    if not isinstance(manifest.get("canonical_text"), str):
        raise ValueError("Manifest canonical mətni saxlamır")
    return manifest


def load_docx_manifest(token: str) -> dict[str, object]:
    return _validate(load_raw_manifest(token))


def _image_filename(index: int, content_type: str) -> str:
    return f"img_{index}.{'jpg' if content_type == 'image/jpeg' else 'png'}"


def _write_manifest(token: str, manifest: Mapping[str, object]) -> None:
    name = bundle_name(token, MANIFEST_NAME)
    payload = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if default_storage.exists(name):
        default_storage.delete(name)
    actual = default_storage.save(name, ContentFile(payload))
    if actual != name:
        raise OSError(f"Storage canonical adı saxlamadı: {name}")


def stash_docx_bundle(
    uploaded_file,
    *,
    owner_id: object = None,
    organization_id: object = None,
) -> tuple[str, str]:
    """DOCX-i oxu; şəkil varsa bundle yarat. ``(mətn, token)`` (şəkilsiz → token boş)."""

    # PDF/şəkil yolundakı ölçü limiti burada da tətbiq olunur (45 MB, settings).
    _ensure_within_size_limit(uploaded_file, MAX_UPLOAD_BYTES)
    original = read_upload(uploaded_file)
    extract = read_docx(original)
    if not extract.images:
        return extract.text, ""

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
        "formula_count": extract.formula_count,
        "formula_fallbacks": list(extract.formula_fallbacks),
        "bindings": {},
        "source": {
            "filename": raw_name.rsplit("/", 1)[-1] or "source.docx",
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
    return extract.text, token


def _load_image(token: str, manifest: Mapping[str, object], index: int) -> bytes | None:
    for entry in manifest.get("images") or ():
        if isinstance(entry, Mapping) and entry.get("index") == index:
            data = read_storage(bundle_name(token, str(entry.get("name"))))
            if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
                raise ValueError(f"Stash şəkil hash-i manifestlə uyğun deyil: {index}")
            return data
    return None


def _valid_indices(manifest: Mapping[str, object]) -> set[int]:
    return {
        entry.get("index")
        for entry in manifest.get("images") or ()
        if isinstance(entry, Mapping) and isinstance(entry.get("index"), int)
    }


def bind_docx_manifest(
    token: str,
    parsed: Sequence[MutableMapping[str, object]],
    *,
    owner_id: object = None,
    organization_id: object = None,
) -> Sequence[MutableMapping[str, object]]:
    """Parse olunmuş ``media_refs``-i manifestə yaz; hər item-ə ``source_index`` ver.

    Naməlum istinad (müəllim markeri dəyişib) → sualda xəbərdarlıq, bağlama
    yox. Düstur fallback-ı olan sual da burada işarələnir (``formula_fallback``).
    """

    manifest = load_docx_manifest(token)
    assert_manifest_scope(manifest, owner_id=owner_id, organization_id=organization_id)
    known = _valid_indices(manifest)
    fallbacks = [text for text in manifest.get("formula_fallbacks") or () if isinstance(text, str) and text]
    bindings: dict[str, dict[str, list[int]]] = {}
    for source_index, item in enumerate(parsed):
        if not isinstance(item, MutableMapping):
            raise ValueError("Parsed sual strukturu yanlışdır")
        item["source_index"] = source_index
        item.setdefault("warnings", [])
        refs = item.get("media_refs") or {}
        clean: dict[str, list[int]] = {}
        unknown: list[int] = []
        for slot, indices in refs.items():
            kept = [index for index in indices if index in known][:_MAX_IMAGES_PER_TARGET]
            unknown.extend(index for index in indices if index not in known)
            if kept:
                clean[str(slot)] = kept
        if unknown:
            item["warnings"].append(
                {
                    "type": "image_ref_unknown",
                    "severity": "warning",
                    "msg": pgettext(_WARN_CTX, "image_ref_unknown").format(
                        refs=", ".join(str(index) for index in unknown)
                    ),
                }
            )
        if clean:
            bindings[str(source_index)] = clean
            item["has_media"] = True
            item["media_slots"] = sorted(clean)
        haystack = " ".join([str(item.get("text") or ""), *[str(v) for v in (item.get("options") or {}).values()]])
        if fallbacks and any(fallback in haystack for fallback in fallbacks):
            item["formula_fallback"] = True
            item["warnings"].append(
                {
                    "type": "formula_fallback",
                    "severity": "warning",
                    "msg": pgettext(_WARN_CTX, "formula_fallback"),
                }
            )
    manifest["bindings"] = bindings
    _write_manifest(token, manifest)
    return parsed


def _compose(images: Sequence[bytes], *, label: str | None = None) -> bytes:
    """Bir hədəfin şəkillərini şaquli yığ (bir ``image`` sahəsi var)."""

    opened = [Image.open(io.BytesIO(data)).convert("RGBA") for data in images]
    width = max(image.width for image in opened) + (_LABEL_WIDTH if label else 0)
    height = sum(image.height for image in opened) + _STACK_GAP * (len(opened) - 1)
    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    y = 0
    for image in opened:
        canvas.alpha_composite(image, (_LABEL_WIDTH if label else 0, y))
        y += image.height + _STACK_GAP
    if label:
        ImageDraw.Draw(canvas).text((10, 10), f"{label})", fill=(0, 0, 0, 255))
    buffer = io.BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _target_png(token: str, manifest: Mapping[str, object], indices: Sequence[int], *, label=None) -> bytes | None:
    blobs = [blob for blob in (_load_image(token, manifest, index) for index in indices) if blob]
    if not blobs:
        return None
    if len(blobs) == 1 and label is None:
        return blobs[0]
    return _compose(blobs, label=label)


def _binding_for(manifest: Mapping[str, object], source_index: int) -> dict[str, list[int]]:
    bindings = manifest.get("bindings")
    if not isinstance(bindings, Mapping):
        return {}
    entry = bindings.get(str(source_index))
    return dict(entry) if isinstance(entry, Mapping) else {}


def _option_rows(instances: Sequence[object]) -> dict[int, dict[str, object]]:
    """Bütün yaradılan sualların variantlarını TƏK sorğu ilə oxu (n-dən asılı deyil)."""

    if not instances:
        return {}
    related = instances[0]._meta.get_field("options").related_model
    rows: dict[int, dict[str, object]] = {}
    for option in related.objects.filter(question_id__in=[instance.pk for instance in instances]):
        rows.setdefault(option.question_id, {})[str(option.label or "").strip().upper()] = option
    return rows


def attach_docx_media_batch(
    token: str,
    bindings: Sequence[tuple[int, object]],
    *,
    owner_id: object = None,
    organization_id: object = None,
) -> int:
    """Manifest bağlamalarına görə şəkilləri model ``image`` sahələrinə yaz.

    Sorğu büdcəsi sual sayından asılı deyil: variantlar bir sorğu ilə oxunur,
    dəyişən sətirlər ``bulk_update`` ilə yazılır; fayl xətasında yaradılanlar silinir.
    """

    batch = [(index, instance) for index, instance in bindings if isinstance(index, int)]
    if not batch:
        return 0
    manifest = load_docx_manifest(token)
    assert_manifest_scope(manifest, owner_id=owner_id, organization_id=organization_id)
    instances = [instance for _index, instance in batch]
    option_rows = _option_rows(instances)
    stem_updates: list[object] = []
    option_updates: list[object] = []
    created: list[tuple[object, str]] = []
    try:
        for source_index, question in batch:
            binding = _binding_for(manifest, source_index)
            if not binding:
                continue
            stem_refs = binding.get("stem") or []
            if stem_refs and not question.image:
                png = _target_png(token, manifest, stem_refs)
                if png:
                    name = f"docx_{token[:8]}_q{source_index + 1}_stem.png"
                    question.image.save(name, ContentFile(png), save=False)
                    created.append((question.image.storage, question.image.name))
                    question.image_replaces_text = False
                    stem_updates.append(question)
            options = option_rows.get(question.pk, {})
            for option in options.values():
                # `upload_to` (bank_option_media_path) `option.question`-a baxır —
                # lazy FK sorğusu əvəzinə əldəki instansı keşlə (sual sayına görə N sorğu olmasın).
                option.question = question
            for label, refs in binding.items():
                option = options.get(label)
                if label == "stem" or option is None or option.image or not refs:
                    continue
                png = _target_png(token, manifest, refs)
                if not png:
                    continue
                name = f"docx_{token[:8]}_q{source_index + 1}_option_{label}.png"
                option.image.save(name, ContentFile(png), save=False)
                created.append((option.image.storage, option.image.name))
                option.image_replaces_text = False
                option_updates.append(option)
        with transaction.atomic():
            if stem_updates:
                type(stem_updates[0]).objects.bulk_update(stem_updates, ["image", "image_replaces_text"])
            if option_updates:
                type(option_updates[0]).objects.bulk_update(option_updates, ["image", "image_replaces_text"])
    except Exception:
        for storage, name in reversed(created):
            try:
                storage.delete(name)
            except Exception as cleanup_error:  # pragma: no cover - backend outage
                logger.error("Partial DOCX media silinmədi (%s): %s", name, cleanup_error)
        raise
    return len(stem_updates) + len(option_updates)


def render_docx_question_preview(
    token: str,
    source_index: int,
    *,
    owner_id: object = None,
    organization_id: object = None,
) -> bytes:
    """Preview üçün: sualın stem + variant şəkillərini bir PNG-də göstər."""

    manifest = load_docx_manifest(token)
    assert_manifest_scope(manifest, owner_id=owner_id, organization_id=organization_id)
    binding = _binding_for(manifest, source_index)
    if not binding:
        raise ValueError("source_index üçün bağlama yoxdur")
    parts: list[bytes] = []
    stem = _target_png(token, manifest, binding.get("stem") or [])
    if stem:
        parts.append(stem)
    for label in sorted(key for key in binding if key != "stem"):
        png = _target_png(token, manifest, binding[label], label=label)
        if png:
            parts.append(png)
    if not parts:
        raise ValueError("Bağlanmış şəkil tapılmadı")
    return parts[0] if len(parts) == 1 else _compose(parts)


__all__ = [
    "MANIFEST_KIND",
    "attach_docx_media_batch",
    "bind_docx_manifest",
    "is_docx_manifest",
    "load_docx_manifest",
    "render_docx_question_preview",
    "stash_docx_bundle",
]
