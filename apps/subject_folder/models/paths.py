"""Qorunan media saxlama yolları (``upload_to``).

Orijinal ad QƏSDƏN diskə yazılmır: istifadəçi adı (PII) və traversal riski
fayl sistemindən uzaq qalır, ad isə təsadüfi UUID-dir — yol təxmin edilə
bilmir. Göstərmək üçün ``original_name`` sahəsi var. Prefikslər
``core.media_policies``-ə (``AppConfig.ready``) qeyd olunan prefikslərlə EYNİDİR.
"""

from __future__ import annotations

import os
import uuid

from ..constants import MATERIALS_MEDIA_PREFIX, SUBMISSIONS_MEDIA_PREFIX


def _extension(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower()[:10]


def material_file_path(instance, filename: str) -> str:
    """``subject_folder/materials/<org>/<folder>/<uuid><ext>``."""
    return f"{MATERIALS_MEDIA_PREFIX}{instance.organization_id}/{instance.folder_id}/{uuid.uuid4().hex}{_extension(filename)}"


def task_attachment_path(instance, filename: str) -> str:
    """``subject_folder/materials/<org>/<folder>/tasks/<uuid><ext>`` — müəllim qoşması."""
    folder_id = getattr(instance.task, "folder_id", "x")
    return (
        f"{MATERIALS_MEDIA_PREFIX}{instance.organization_id}/{folder_id}/tasks/{uuid.uuid4().hex}{_extension(filename)}"
    )


def submission_file_path(instance, filename: str) -> str:
    """``subject_folder/submissions/<org>/<task>/<submission>/<uuid><ext>``."""
    task_id = getattr(instance.submission, "task_id", "x")
    return (
        f"{SUBMISSIONS_MEDIA_PREFIX}{instance.organization_id}/{task_id}/"
        f"{instance.submission_id}/{uuid.uuid4().hex}{_extension(filename)}"
    )


__all__ = ["material_file_path", "submission_file_path", "task_attachment_path"]
