"""Canonical visual-import source/manifest və atomik media bağlama axını."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import posixpath
import re
import unicodedata
import uuid
import warnings
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from PIL import Image, ImageOps, UnidentifiedImageError

from apps.exams.services.pdf_layout import extract_pdf_layout
from apps.exams.services.visual_import_security import validate_visual_upload

logger = logging.getLogger(__name__)
_IMPORT_SUBDIR = "question_imports"
_MANIFEST_VERSION = 2
_SOURCE_NAME = "source.pdf"
_MANIFEST_NAME = "manifest.json"
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_VISUAL_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg")
_IMAGE_PDF_DPI = 300
_MAX_IMAGE_PIXELS = 50_000_000


@dataclass(frozen=True)
class _Target:
    instance: Any
    source_index: int
    label: str | None
    segment: Mapping[str, object]


@dataclass(frozen=True)
class _Snapshot:
    instance: Any
    image_name: str
    replaces_text: bool


def _valid_token(token: object) -> bool:
    return isinstance(token, str) and bool(_TOKEN_RE.fullmatch(token))


def _prefix(token: str) -> str:
    if not _valid_token(token):
        raise ValueError("İdxal token-i yanlışdır")
    return posixpath.join(_IMPORT_SUBDIR, token)


def _bundle_name(token: str, filename: str) -> str:
    return posixpath.join(_prefix(token), filename)


def _read_upload(uploaded_file) -> bytes:
    try:
        original_position = uploaded_file.tell()
    except (AttributeError, OSError):
        original_position = None
    try:
        try:
            uploaded_file.seek(0)
        except (AttributeError, OSError):
            pass
        data = uploaded_file.read()
    finally:
        if original_position is not None:
            try:
                uploaded_file.seek(original_position)
            except (AttributeError, OSError):
                pass
    if not isinstance(data, bytes) or not data:
        raise ValueError("Vizual mənbə məlumatı boşdur")
    return data


def _metadata_id(value: object) -> int | str | None:
    if value is None:
        return None
    value = getattr(value, "pk", value)
    if isinstance(value, (int, str)):
        return value
    return str(value)


def _image_to_pdf(data: bytes) -> bytes:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as probe:
                probe.verify()
            with Image.open(BytesIO(data)) as opened:
                width, height = opened.size
                if width <= 0 or height <= 0 or width * height > _MAX_IMAGE_PIXELS:
                    raise ValueError("Şəkil ölçüləri təhlükəsiz limitə uyğun deyil")
                opened.load()
                oriented = ImageOps.exif_transpose(opened)
                rgba = oriented.convert("RGBA")
                rgb = Image.new("RGB", rgba.size, "white")
                rgb.paste(rgba, mask=rgba.getchannel("A"))
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
    ) as exc:
        raise ValueError("Şəkil təhlükəsiz şəkildə oxunmadı") from exc

    normalized = BytesIO()
    rgb.save(normalized, format="PNG")
    import fitz

    document = fitz.open()
    try:
        page = document.new_page(
            width=rgb.width * 72 / _IMAGE_PDF_DPI,
            height=rgb.height * 72 / _IMAGE_PDF_DPI,
        )
        page.insert_image(page.rect, stream=normalized.getvalue(), keep_proportion=False)
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()


def _source_metadata(
    uploaded_file,
    original: bytes,
    canonical_pdf: bytes,
    *,
    owner_id: object = None,
    organization_id: object = None,
) -> dict[str, object]:
    raw_name = str(getattr(uploaded_file, "name", "") or "").replace("\\", "/")
    metadata: dict[str, object] = {
        "filename": raw_name.rsplit("/", 1)[-1] or _SOURCE_NAME,
        "original_byte_size": len(original),
        "original_sha256": hashlib.sha256(original).hexdigest(),
        "canonical_pdf_byte_size": len(canonical_pdf),
        "canonical_pdf_sha256": hashlib.sha256(canonical_pdf).hexdigest(),
    }
    for key, value in (
        ("owner_id", _metadata_id(owner_id)),
        ("organization_id", _metadata_id(organization_id)),
    ):
        if value is not None:
            metadata[key] = value
    return metadata


def _validate_manifest(manifest: object) -> dict[str, object]:
    if not isinstance(manifest, dict):
        raise ValueError("İdxal manifesti obyekt deyil")
    if manifest.get("schema_version") != _MANIFEST_VERSION:
        raise ValueError("İdxal manifest versiyası dəstəklənmir")
    confidence = manifest.get("confidence")
    questions = manifest.get("questions")
    source = manifest.get("source")
    if not isinstance(confidence, Mapping) or confidence.get("is_confident") is not True:
        raise ValueError("PDF layout manifesti etibarlı deyil")
    if not isinstance(questions, list) or not questions:
        raise ValueError("PDF layout manifestində sual yoxdur")
    if not isinstance(source, Mapping):
        raise ValueError("İdxal manifestində source metadata yoxdur")
    first_q_no = questions[0].get("q_no") if isinstance(questions[0], Mapping) else None
    if isinstance(first_q_no, bool) or not isinstance(first_q_no, int) or first_q_no < 1:
        raise ValueError("Manifest başlanğıc sual nömrəsi yanlışdır")
    for index, question in enumerate(questions):
        if not isinstance(question, Mapping):
            raise ValueError("Manifestdə sual strukturu yanlışdır")
        if question.get("ordinal") != index + 1 or question.get("q_no") != first_q_no + index:
            raise ValueError("Manifest ordinal və çap sual sırası ardıcıl deyil")
        if not isinstance(question.get("stem"), Mapping):
            raise ValueError("Manifestdə stem segmenti yoxdur")
        options = question.get("options")
        if not isinstance(options, Mapping) or list(options) not in (
            ["A", "B", "C", "D"],
            ["A", "B", "C", "D", "E"],
        ):
            raise ValueError("Manifest variant ardıcıllığı A-D[/E] deyil")
        if not all(isinstance(segment, Mapping) for segment in options.values()):
            raise ValueError("Manifest variant segmenti yanlışdır")
    return manifest


def _assert_manifest_scope(
    manifest: Mapping[str, object],
    *,
    owner_id: object = None,
    organization_id: object = None,
) -> None:
    source = manifest.get("source")
    if not isinstance(source, Mapping):
        raise ValueError("İdxal source metadata-sı yanlışdır")
    for key, expected in (
        ("owner_id", _metadata_id(owner_id)),
        ("organization_id", _metadata_id(organization_id)),
    ):
        if expected is None:
            continue
        actual = source.get(key)
        if actual is None or not hmac.compare_digest(str(actual), str(expected)):
            raise PermissionDenied(f"İdxal manifestinin {key} scope-u uyğun deyil")


def stash_math_images(
    uploaded_file,
    *,
    owner_id: object = None,
    organization_id: object = None,
) -> str | None:
    """Vizual upload-u private ``source.pdf + manifest.json`` bundle kimi saxla."""

    filename = str(getattr(uploaded_file, "name", "") or "").lower()
    if not filename.endswith(_VISUAL_EXTENSIONS):
        return None

    validate_visual_upload(uploaded_file)
    original = _read_upload(uploaded_file)
    canonical_pdf = original if filename.endswith(".pdf") else _image_to_pdf(original)
    typed_manifest = extract_pdf_layout(canonical_pdf, fail_closed=True)
    manifest = typed_manifest.to_dict()
    manifest["schema_version"] = _MANIFEST_VERSION
    manifest["source"] = _source_metadata(
        uploaded_file,
        original,
        canonical_pdf,
        owner_id=owner_id,
        organization_id=organization_id,
    )
    _validate_manifest(manifest)

    token = uuid.uuid4().hex
    source_name = _bundle_name(token, _SOURCE_NAME)
    manifest_name = _bundle_name(token, _MANIFEST_NAME)
    manifest_bytes = json.dumps(
        manifest,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    saved: list[str] = []
    try:
        for expected_name, content in (
            (source_name, canonical_pdf),
            (manifest_name, manifest_bytes),
        ):
            actual_name = default_storage.save(expected_name, ContentFile(content))
            saved.append(actual_name)
            if actual_name != expected_name or not default_storage.exists(expected_name):
                raise OSError(f"Storage canonical adı saxlamadı: {expected_name}")
    except Exception:
        for name in reversed(saved):
            _delete_name(name)
        _delete_tree(_prefix(token), suppress_errors=True)
        raise
    return token


def _read_storage(name: str) -> bytes:
    with default_storage.open(name, "rb") as handle:
        data = handle.read()
    if not isinstance(data, bytes):
        raise ValueError(f"Storage binary məlumat qaytarmadı: {name}")
    return data


def _load_manifest(token: str) -> dict[str, object]:
    raw = _read_storage(_bundle_name(token, _MANIFEST_NAME))
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("İdxal manifesti oxunmur") from exc
    return _validate_manifest(manifest)


def _normalized_content(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(normalized.split())


def _content_signature(question: Mapping[str, object]) -> tuple[object, ...]:
    options = question.get("options")
    correct = question.get("correct")
    if not isinstance(options, Mapping) or not isinstance(correct, (list, tuple, set)):
        raise ValueError("Parsed sualın options/correct strukturu yanlışdır")
    option_signature = tuple(
        (str(label).strip().upper(), _normalized_content(text))
        for label, text in sorted(options.items(), key=lambda item: str(item[0]))
    )
    correct_signature = tuple(sorted({str(label).strip().upper() for label in correct}))
    return (
        _normalized_content(question.get("text")),
        option_signature,
        correct_signature,
        str(question.get("answer_mode") or "").strip(),
    )


def _canonical_parsed(manifest: Mapping[str, object]) -> list[dict]:
    canonical_text = manifest.get("canonical_text")
    if not isinstance(canonical_text, str) or not canonical_text.strip():
        raise ValueError("Manifest canonical mətni saxlamır")
    # Lazy import parsing ↔ import-media startup dövrü yaratmır.
    from apps.exams.services.parsing import parse_bulk_mcq

    parsed = parse_bulk_mcq(canonical_text)
    if not isinstance(parsed, list):
        raise ValueError("Manifest canonical mətni parse olunmadı")
    return parsed


def get_stashed_import_text(
    token: str,
    owner_id: object = None,
    organization_id: object = None,
) -> str:
    """Scope yoxlamasından sonra stash manifestinin canonical mətnini qaytar."""

    manifest = _load_manifest(token)
    _assert_manifest_scope(
        manifest,
        owner_id=owner_id,
        organization_id=organization_id,
    )
    canonical_text = manifest.get("canonical_text")
    if not isinstance(canonical_text, str) or not canonical_text.strip():
        raise ValueError("Manifest canonical mətni saxlamır")
    return canonical_text


def bind_import_manifest(
    token: str,
    parsed: Sequence[MutableMapping[str, object]],
    *,
    owner_id: object = None,
    organization_id: object = None,
) -> Sequence[MutableMapping[str, object]]:
    """Parsed məzmunu yoxla və hər item-ə 0-based source index bağla."""

    manifest = _load_manifest(token)
    _assert_manifest_scope(
        manifest,
        owner_id=owner_id,
        organization_id=organization_id,
    )
    questions = manifest["questions"]
    canonical_parsed = _canonical_parsed(manifest)
    if len(parsed) != len(questions) or len(parsed) != len(canonical_parsed):
        raise ValueError(
            "Parsed/manifest sual sayı uyğun deyil: "
            f"parsed={len(parsed)}, manifest={len(questions)}, canonical={len(canonical_parsed)}"
        )

    bindings: list[tuple[MutableMapping[str, object], int]] = []
    for source_index, (item, question, canonical) in enumerate(zip(parsed, questions, canonical_parsed)):
        if (
            not isinstance(item, MutableMapping)
            or not isinstance(question, Mapping)
            or not isinstance(canonical, Mapping)
        ):
            raise ValueError("Parsed sual strukturu yanlışdır")
        parsed_q_no = item.get("q_no")
        manifest_q_no = question.get("q_no")
        if parsed_q_no is None or str(parsed_q_no).strip() != str(manifest_q_no):
            raise ValueError(
                "Parsed/manifest sual nömrəsi uyğun deyil: "
                f"index={source_index}, parsed={parsed_q_no!r}, manifest={manifest_q_no!r}"
            )
        if _content_signature(item) != _content_signature(canonical):
            raise ValueError(f"Parsed/manifest sual məzmunu uyğun deyil: index={source_index}")
        bindings.append((item, source_index))

    for item, source_index in bindings:
        item["source_index"] = source_index
        item["has_visual_source"] = True
    return parsed


def _load_source(token: str, manifest: Mapping[str, object]) -> bytes:
    data = _read_storage(_bundle_name(token, _SOURCE_NAME))
    source = manifest.get("source")
    if not isinstance(source, Mapping):
        raise ValueError("İdxal source metadata-sı yanlışdır")
    if source.get("canonical_pdf_byte_size") != len(data):
        raise ValueError("Canonical PDF ölçüsü manifestlə uyğun deyil")
    digest = hashlib.sha256(data).hexdigest()
    if source.get("canonical_pdf_sha256") != digest:
        raise ValueError("Canonical PDF hash-i manifestlə uyğun deyil")
    return data


def _question_targets(
    source_index: int,
    question,
    source_question: Mapping[str, object],
) -> list[_Target]:
    if getattr(question, "pk", None) is None or getattr(question, "_state", None) is None:
        raise ValueError("Media yalnız saxlanmış question instance-ına bağlana bilər")
    if not hasattr(question, "image") or not hasattr(question, "image_replaces_text"):
        raise ValueError("Question modelində vizual media sahələri yoxdur")

    raw_options = source_question.get("options")
    stem = source_question.get("stem")
    if not isinstance(raw_options, Mapping) or not isinstance(stem, Mapping):
        raise ValueError("Manifest sual segmentləri yanlışdır")

    model_options: dict[str, object] = {}
    for option in question.options.all():
        label = str(getattr(option, "label", "") or "").strip().upper()
        if label in model_options:
            raise ValueError(f"Question variant label-i təkrarlanır: {label!r}")
        model_options[label] = option
    if set(model_options) != set(raw_options):
        raise ValueError(
            "Model/manifest variantları uyğun deyil: " f"model={list(model_options)}, manifest={list(raw_options)}"
        )

    targets: list[_Target] = []
    if not question.image:
        targets.append(_Target(question, source_index, None, stem))
    for label, segment in raw_options.items():
        option = model_options[label]
        if not hasattr(option, "image_replaces_text"):
            raise ValueError("Option modelində vizual media flag-i yoxdur")
        if not option.image:
            targets.append(_Target(option, source_index, str(label), segment))
    return targets


def _prepare_targets(
    manifest: Mapping[str, object],
    batch: Sequence[tuple[int, object]],
) -> list[_Target]:
    questions = manifest.get("questions")
    if not isinstance(questions, list):
        raise ValueError("Manifest questions siyahısı saxlamır")
    targets: list[_Target] = []
    seen_indices: set[int] = set()
    seen_instances: set[int] = set()
    for source_index, question in batch:
        if isinstance(source_index, bool) or not isinstance(source_index, int):
            raise ValueError("source_index tam ədəd olmalıdır")
        if source_index < 0 or source_index >= len(questions):
            raise ValueError(f"source_index manifest xaricindədir: {source_index}")
        identity = id(question)
        if source_index in seen_indices or identity in seen_instances:
            raise ValueError("Batch-də təkrarlanan source_index/question var")
        seen_indices.add(source_index)
        seen_instances.add(identity)
        source_question = questions[source_index]
        if not isinstance(source_question, Mapping):
            raise ValueError("Manifest sual strukturu yanlışdır")
        targets.extend(_question_targets(source_index, question, source_question))
    return targets


def _image_filename(token: str, batch_id: str, target: _Target) -> str:
    suffix = "stem" if target.label is None else f"option_{target.label}"
    return f"pdf_{token[:8]}_{batch_id}_q{target.source_index + 1}_{suffix}.png"


def _restore_snapshots(snapshots: Sequence[_Snapshot]) -> None:
    for snapshot in snapshots:
        snapshot.instance.image.name = snapshot.image_name or None
        snapshot.instance.image._committed = bool(snapshot.image_name)
        snapshot.instance.image_replaces_text = snapshot.replaces_text


def attach_import_media_batch(
    token: str,
    bindings: Sequence[tuple[int, object]],
    *,
    owner_id: object = None,
    organization_id: object = None,
) -> int:
    """Manifest segmentlərini atomik render batch-i ilə model media-sına bağla."""
    batch = list(bindings)
    if not batch:
        return 0
    manifest = _load_manifest(token)
    _assert_manifest_scope(
        manifest,
        owner_id=owner_id,
        organization_id=organization_id,
    )
    targets = _prepare_targets(manifest, batch)
    if not targets:
        return 0
    source = _load_source(token, manifest)

    from apps.exams.services.pdf_layout import render_segments

    batch_id = uuid.uuid4().hex[:12]
    snapshots = [
        _Snapshot(
            target.instance,
            str(target.instance.image.name or ""),
            bool(target.instance.image_replaces_text),
        )
        for target in targets
    ]
    created_files: list[tuple[object, str]] = []
    try:
        with transaction.atomic():
            for offset in range(0, len(targets), 120):
                chunk = targets[offset : offset + 120]
                rendered = render_segments(source, [target.segment for target in chunk])
                if len(rendered) != len(chunk) or any(
                    not isinstance(png, bytes) or not png.startswith(_PNG_SIGNATURE) for png in rendered
                ):
                    raise ValueError("Renderer etibarlı və tam PNG batch-i qaytarmadı")
                for target, png in zip(chunk, rendered):
                    instance = target.instance
                    instance.image.save(
                        _image_filename(token, batch_id, target),
                        ContentFile(png),
                        save=False,
                    )
                    created_files.append((instance.image.storage, instance.image.name))
                    instance.image_replaces_text = True
                    instance.save(update_fields=["image", "image_replaces_text"])
    except Exception:
        for storage, name in reversed(created_files):
            try:
                storage.delete(name)
            except Exception as cleanup_error:  # pragma: no cover - backend outage
                logger.error("Partial import media silinmədi (%s): %s", name, cleanup_error)
        _restore_snapshots(snapshots)
        raise
    return len(batch)


def attach_math_images(token: str, q_no: str, question) -> None:
    """Köhnə printed-q_no API-sini canonical batch attach-a uyğunlaşdır."""

    if not _valid_token(token):
        return
    manifest_name = _bundle_name(token, _MANIFEST_NAME)
    if not default_storage.exists(manifest_name):
        return
    manifest = _load_manifest(token)
    questions = manifest["questions"]
    matches = [
        index
        for index, source_question in enumerate(questions)
        if isinstance(source_question, Mapping) and str(source_question.get("q_no")) == str(q_no).strip()
    ]
    if len(matches) != 1:
        raise ValueError(f"Manifestdə unikal sual nömrəsi tapılmadı: {q_no!r}")
    attach_import_media_batch(token, [(matches[0], question)])


def _delete_name(name: str) -> None:
    try:
        default_storage.delete(name)
    except Exception as exc:  # pragma: no cover - backend outage
        logger.warning("İdxal stash obyekti silinmədi (%s): %s", name, exc)


def _delete_tree(prefix: str, *, suppress_errors: bool) -> None:
    try:
        directories, files = default_storage.listdir(prefix)
    except (FileNotFoundError, NotImplementedError):
        directories, files = (), ()
    except Exception:
        if not suppress_errors:
            raise
        directories, files = (), ()

    for filename in files:
        _delete_name(posixpath.join(prefix, filename))
    for directory in directories:
        _delete_tree(posixpath.join(prefix, directory), suppress_errors=suppress_errors)
    _delete_name(prefix)


def clear_stash(token: str) -> None:
    """İdxal bundle-ını storage backend-dən asılı olmadan rekursiv təmizlə."""

    if not _valid_token(token):
        return
    _delete_name(_bundle_name(token, _SOURCE_NAME))
    _delete_name(_bundle_name(token, _MANIFEST_NAME))
    _delete_tree(_prefix(token), suppress_errors=True)
