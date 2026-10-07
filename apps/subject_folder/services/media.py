"""Qorunan fayllar: ``core.media_views`` üçün icazə yoxlayıcıları + endirmə cavabı.

İki prefiks ``AppConfig.ready()``-də ``register_media_policy`` ilə qeyd olunur:
  * ``subject_folder/materials/`` — material faylları və tapşırıq qoşmaları:
    qovluq sahibi, təyin olunmuş qrupların müəllimləri, əhatəli əməkdaş,
    tələbə (yalnız AKTİV təyinatın DƏRC edilmiş, gizli olmayan məzmunu);
  * ``subject_folder/submissions/`` — göndəriş faylları: tələbənin ÖZÜ,
    qrupun müəllimi (yoxlayan), qovluq sahibi, əhatəli əməkdaş.

Default DENY: sətir tapılmasa və ya dublikat uyğunluq olsa ``False``. Fayl heç
vaxt ``file.url`` ilə verilmir (S3 imzalı URL yoxlamanı keçərdi) — endirmə
``views`` və ya ``core.media_urls.protected_media_url`` ilə gedir.
"""

from __future__ import annotations

from django.http import FileResponse

from core.download_types import attachment_file_response

from ..models import FolderMaterial, SubmissionFile, TaskAttachment
from . import access


def _single(queryset, **lookup):
    try:
        return queryset.get(**lookup)
    except (queryset.model.DoesNotExist, queryset.model.MultipleObjectsReturned):
        return None


def check_material_media_access(user, path: str) -> bool:
    material = _single(FolderMaterial.objects.select_related("folder", "folder__organization", "topic"), file=path)
    if material is not None:
        return access.can_view_material(user, material)
    attachment = _single(
        TaskAttachment.objects.select_related("task", "task__folder", "task__folder__organization", "task__topic"),
        file=path,
    )
    if attachment is not None:
        return access.can_view_task(user, attachment.task)
    return False


def check_submission_media_access(user, path: str) -> bool:
    row = _single(
        SubmissionFile.objects.select_related(
            "submission",
            "submission__assignment",
            "submission__assignment__folder",
            "submission__assignment__folder__organization",
            "submission__assignment__offering",
            "submission__assignment__offering__organization",
        ),
        file=path,
    )
    return row is not None and access.can_view_submission(user, row.submission)


def file_response(field_file, *, filename: str, content_type: str = "") -> FileResponse:
    """ƏLAVƏ kimi (``attachment``) verilir — brauzer faylı mənbə origin-ində icra etməsin.

    Audit 2026-09-28 SF-3: ``Content-Type`` saxlanmış (klientin bəyan etdiyi)
    dəyərdən deyil, fayl adının UZANTISINDAN çıxarılır (``core.download_types``
    ağ siyahısı); ``content_type`` parametri geriyə uyğunluq üçün qalır və
    nəzərə alınmır.
    """
    del content_type
    return attachment_file_response(field_file, filename=filename)


__all__ = ["check_material_media_access", "check_submission_media_access", "file_response"]
