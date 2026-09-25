"""Tədris materialları: yaratma (növə görə yoxlama), redaktə, dərc, gizlətmə, sıralama.

«Bütün data saxlanılsın» qaydası: material SİLİNMİR, ``is_archived`` ilə
gizlədilir; fayl dəyişdiriləndə köhnə fayl saxlama yerində qalır.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction

from core.constants import AuditAction

from ..constants import (
    ALLOWED_URL_SCHEMES,
    MATERIAL_EXTENSIONS,
    MAX_CODE_CHARS,
    MAX_URL_CHARS,
    CodeLanguage,
    MaterialKind,
)
from ..errors import FolderError
from ..models import FolderMaterial
from . import access
from .events import audit_change
from .folders import clean_text, clean_title, next_order
from .topics import topic_in_folder
from .uploads import material_max_mb, prepare_upload

_FILE_KINDS = (MaterialKind.FILE, MaterialKind.IMAGE)
_LINK_KINDS = (MaterialKind.LINK, MaterialKind.VIDEO_LINK)


def clean_url(value) -> str:
    """Yalnız http/https; ``javascript:``/``data:`` və s. rədd olunur."""
    url = str(value or "").strip()
    if not url or len(url) > MAX_URL_CHARS:
        raise FolderError.of("material.url_invalid")
    if urlsplit(url).scheme.lower() not in ALLOWED_URL_SCHEMES:
        raise FolderError.of("material.url_invalid")
    try:
        URLValidator(schemes=list(ALLOWED_URL_SCHEMES))(url)
    except ValidationError as exc:
        raise FolderError.of("material.url_invalid") from exc
    return url


def _clean_code(text, language) -> tuple[str, str]:
    code = str(text or "")
    if not code.strip():
        raise FolderError.of("material.code_required")
    if len(code) > MAX_CODE_CHARS:
        raise FolderError.of("text.too_long", max=MAX_CODE_CHARS)
    lang = str(language or "").strip()
    return code, (lang if lang in CodeLanguage.values else CodeLanguage.OTHER.value)


def _attach_file(material, uploaded, *, image_only: bool) -> None:
    meta = prepare_upload(
        uploaded, allowed_extensions=MATERIAL_EXTENSIONS, max_mb=material_max_mb(), image_only=image_only
    )
    material.file = uploaded
    material.original_name = meta["original_name"]
    material.size = meta["size"]
    material.content_type = meta["content_type"]
    material.sha256 = meta["sha256"]


def create_material(
    folder,
    *,
    by_user,
    kind: str,
    title: str,
    description: str = "",
    topic=None,
    file=None,
    url: str = "",
    code_text: str = "",
    code_language: str = "",
    is_published: bool = False,
    request=None,
) -> FolderMaterial:
    """Növə görə məcburi sahələr: fayl/şəkil → ``file``; keçid/video → ``url``;
    kod → ``code_text``; qeyd → ``description``."""
    access.ensure_can_manage(by_user, folder)
    if kind not in MaterialKind.values:
        raise FolderError.of("material.kind_unknown")
    topic_obj = topic_in_folder(folder, topic)
    material = FolderMaterial(
        organization_id=folder.organization_id,
        folder=folder,
        topic=topic_obj,
        kind=kind,
        title=clean_title(title),
        description=clean_text(description),
        order=next_order(folder.materials.filter(topic=topic_obj)),
        is_published=bool(is_published),
        created_by=by_user,
    )
    if kind in _FILE_KINDS:
        _attach_file(material, file, image_only=(kind == MaterialKind.IMAGE))
    elif kind in _LINK_KINDS:
        material.url = clean_url(url)
    elif kind == MaterialKind.CODE:
        material.code_text, material.code_language = _clean_code(code_text, code_language)
    elif kind == MaterialKind.NOTE and not material.description:
        raise FolderError.of("material.note_required")
    material.save()
    audit_change(
        material,
        actor=by_user,
        action=AuditAction.CREATE,
        changes={"kind": kind, "title": material.title, "published": material.is_published},
        request=request,
    )
    return material


def update_material(
    material,
    *,
    by_user,
    title=None,
    description=None,
    topic="__keep__",
    file=None,
    url=None,
    code_text=None,
    code_language=None,
    request=None,
) -> FolderMaterial:
    """Qismən redaktə — ``None`` = dəyişmir; ``topic=None`` mövzudan ayırır."""
    folder = material.folder
    access.ensure_can_manage(by_user, folder)
    changed = []
    if title is not None:
        material.title = clean_title(title)
        changed.append("title")
    if description is not None:
        material.description = clean_text(description)
        changed.append("description")
    if topic != "__keep__":
        material.topic = topic_in_folder(folder, topic)
        changed.append("topic")
    if file is not None and material.kind in _FILE_KINDS:
        _attach_file(material, file, image_only=(material.kind == MaterialKind.IMAGE))
        changed.append("file")
    if url is not None and material.kind in _LINK_KINDS:
        material.url = clean_url(url)
        changed.append("url")
    if (code_text is not None or code_language is not None) and material.kind == MaterialKind.CODE:
        material.code_text, material.code_language = _clean_code(
            material.code_text if code_text is None else code_text,
            material.code_language if code_language is None else code_language,
        )
        changed.append("code")
    if material.kind == MaterialKind.NOTE and not material.description:
        raise FolderError.of("material.note_required")
    if changed:
        material.save()
        audit_change(material, actor=by_user, changes={"fields": changed}, request=request)
    return material


def set_material_published(material, *, by_user, published: bool, request=None) -> FolderMaterial:
    access.ensure_can_manage(by_user, material.folder)
    if material.is_published != bool(published):
        material.is_published = bool(published)
        material.save(update_fields=["is_published", "updated_at"])
        audit_change(material, actor=by_user, changes={"published": material.is_published}, request=request)
    return material


def archive_material(material, *, by_user, archived: bool = True, request=None) -> FolderMaterial:
    """«Sil» düyməsi — material gizlədilir (data və fayl saxlanılır); ``archived=False`` geri qaytarır."""
    access.ensure_can_manage(by_user, material.folder)
    if material.is_archived != bool(archived):
        material.is_archived = bool(archived)
        material.save(update_fields=["is_archived", "updated_at"])
        audit_change(material, actor=by_user, changes={"archived": material.is_archived}, request=request)
    return material


@transaction.atomic
def reorder_materials(folder, *, by_user, ordered_ids, request=None) -> int:
    """Verilən ardıcıllıq → ``order`` = 10, 20, … (qovluğa aid olmayan id → xəta)."""
    access.ensure_can_manage(by_user, folder)
    materials = {str(row.pk): row for row in folder.materials.all()}
    ordered = []
    for raw in ordered_ids or []:
        row = materials.get(str(raw))
        if row is None:
            raise FolderError.of("material.not_in_folder")
        ordered.append(row)
    for index, row in enumerate(ordered, start=1):
        row.order = index * 10
    FolderMaterial.objects.bulk_update(ordered, ["order"])
    audit_change(folder, actor=by_user, changes={"reorder_materials": len(ordered)}, request=request)
    return len(ordered)


__all__ = [
    "archive_material",
    "clean_url",
    "create_material",
    "reorder_materials",
    "set_material_published",
    "update_material",
]
