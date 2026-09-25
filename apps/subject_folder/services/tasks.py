"""Tapşırıqlar: ev tapşırığı CRUD, sərbəst iş slotunun redaktəsi, qoşmalar, dərc.

Sərbəst iş slotu YARADILMIR (yalnız sillabus sinxronu yaradır) — müəllim
başlıq, təlimat, mövzu, fayl limitlərini dəyişə bilər; ``kind``/``slot_index``/
``max_points`` sillabusun strukturudur. Ev tapşırığının sayı məhdud deyil.
Göndərişi olan tapşırıq silinmir — arxivlənir.
"""

from __future__ import annotations

from django.db import transaction

from core.constants import AuditAction

from ..constants import (
    DEFAULT_MAX_FILES,
    DEFAULT_SUBMISSION_MAX_MB,
    MATERIAL_EXTENSIONS,
    MAX_FILES_CAP,
    MAX_INSTRUCTIONS_CHARS,
    MAX_TASK_ATTACHMENTS,
    SUBMISSION_EXTENSIONS,
    SUBMISSION_MAX_MB_CAP,
    TaskKind,
)
from ..errors import FolderError
from ..models import FolderTask, TaskAttachment
from . import access, notify
from .events import audit_change
from .folders import clean_text, clean_title, next_order
from .topics import topic_in_folder
from .uploads import material_max_mb, prepare_upload


def clean_extensions(values) -> list[str]:
    """``["pdf", ".DOCX"]`` → ``[".docx", ".pdf"]``; icazəli siyahıdan kənar uzantı → xəta."""
    cleaned = set()
    for raw in values or []:
        ext = "." + str(raw or "").strip().lower().lstrip(".")
        if ext == ".":
            continue
        if ext not in SUBMISSION_EXTENSIONS:
            raise FolderError.of("task.extensions_invalid", ext=ext)
        cleaned.add(ext)
    return sorted(cleaned)


def _limits(max_file_mb, max_files) -> tuple[int, int]:
    try:
        size = int(max_file_mb)
        count = int(max_files)
    except (TypeError, ValueError) as exc:
        raise FolderError.of("task.limits_invalid", max_files=MAX_FILES_CAP, max_mb=SUBMISSION_MAX_MB_CAP) from exc
    if not (1 <= size <= SUBMISSION_MAX_MB_CAP and 1 <= count <= MAX_FILES_CAP):
        raise FolderError.of("task.limits_invalid", max_files=MAX_FILES_CAP, max_mb=SUBMISSION_MAX_MB_CAP)
    return size, count


def create_homework(
    folder,
    *,
    by_user,
    title: str,
    instructions: str = "",
    topic=None,
    allowed_extensions=None,
    max_file_mb=None,
    max_files=None,
    allow_text_answer: bool = True,
    allow_files: bool = True,
    is_published: bool = False,
    request=None,
) -> FolderTask:
    """Yeni EV TAPŞIRIĞI (sərbəst iş slotu bu yolla yaradılmır)."""
    access.ensure_can_manage(by_user, folder)
    if not allow_text_answer and not allow_files:
        raise FolderError.of("task.nothing_to_submit")
    size, count = _limits(
        DEFAULT_SUBMISSION_MAX_MB if max_file_mb is None else max_file_mb,
        DEFAULT_MAX_FILES if max_files is None else max_files,
    )
    task = FolderTask.objects.create(
        organization_id=folder.organization_id,
        folder=folder,
        topic=topic_in_folder(folder, topic),
        kind=TaskKind.HOMEWORK,
        title=clean_title(title),
        instructions=clean_text(instructions, limit=MAX_INSTRUCTIONS_CHARS),
        allowed_extensions=clean_extensions(allowed_extensions),
        max_file_mb=size,
        max_files=count,
        allow_text_answer=bool(allow_text_answer),
        allow_files=bool(allow_files),
        order=next_order(folder.tasks.filter(kind=TaskKind.HOMEWORK)),
        is_published=False,
        created_by=by_user,
    )
    audit_change(task, actor=by_user, action=AuditAction.CREATE, changes={"kind": task.kind}, request=request)
    if is_published:
        set_task_published(task, by_user=by_user, published=True, request=request)
    return task


def create_task(folder, *, by_user, kind: str, **fields) -> FolderTask:
    """Ümumi giriş: ``selfwork`` → ``task.selfwork_slots_fixed`` (struktur sillabusdandır)."""
    if kind == TaskKind.SELFWORK:
        raise FolderError.of("task.selfwork_slots_fixed")
    if kind != TaskKind.HOMEWORK:
        raise FolderError.of("task.kind_unknown")
    return create_homework(folder, by_user=by_user, **fields)


def _ensure_editable(task) -> None:
    if task.is_archived:
        raise FolderError.of("task.archived")


def update_task(
    task,
    *,
    by_user,
    title=None,
    instructions=None,
    topic="__keep__",
    allowed_extensions=None,
    max_file_mb=None,
    max_files=None,
    allow_text_answer=None,
    allow_files=None,
    request=None,
) -> FolderTask:
    """Qismən redaktə (``None`` = dəyişmir). Sərbəst işdə də eyni sahələr; növ/slot/bal dəyişmir."""
    access.ensure_can_manage(by_user, task.folder)
    _ensure_editable(task)
    changed = []
    if title is not None:
        task.title = clean_title(title)
        changed.append("title")
    if instructions is not None:
        task.instructions = clean_text(instructions, limit=MAX_INSTRUCTIONS_CHARS)
        changed.append("instructions")
    if topic != "__keep__":
        task.topic = topic_in_folder(task.folder, topic)
        changed.append("topic")
    if allowed_extensions is not None:
        task.allowed_extensions = clean_extensions(allowed_extensions)
        changed.append("allowed_extensions")
    if max_file_mb is not None or max_files is not None:
        task.max_file_mb, task.max_files = _limits(
            task.max_file_mb if max_file_mb is None else max_file_mb,
            task.max_files if max_files is None else max_files,
        )
        changed.append("limits")
    if allow_text_answer is not None:
        task.allow_text_answer = bool(allow_text_answer)
        changed.append("allow_text_answer")
    if allow_files is not None:
        task.allow_files = bool(allow_files)
        changed.append("allow_files")
    if not task.allow_text_answer and not task.allow_files:
        raise FolderError.of("task.nothing_to_submit")
    if changed:
        task.save()
        audit_change(task, actor=by_user, changes={"fields": changed}, request=request)
    return task


def set_task_published(task, *, by_user, published: bool, request=None) -> FolderTask:
    """Dərc/geri çəkmə. İlk dəfə dərc olunanda aktiv təyinatların tələbələrinə TOPLU bildiriş gedir."""
    access.ensure_can_manage(by_user, task.folder)
    if published:
        _ensure_editable(task)
    if task.is_published == bool(published):
        return task
    task.is_published = bool(published)
    task.save(update_fields=["is_published", "updated_at"])
    audit_change(task, actor=by_user, changes={"published": task.is_published}, request=request)
    if task.is_published:
        notify.task_published(task)
    return task


def archive_task(task, *, by_user, archived: bool = True, request=None) -> FolderTask:
    """Gizlətmə (göndərişlər saxlanılır). Sərbəst iş slotu arxivdən qaytarılanda slot boş olmalıdır."""
    access.ensure_can_manage(by_user, task.folder)
    if task.is_archived == bool(archived):
        return task
    if not archived and task.kind == TaskKind.SELFWORK:
        occupied = task.folder.tasks.filter(kind=TaskKind.SELFWORK, is_archived=False, slot_index=task.slot_index)
        if occupied.exclude(pk=task.pk).exists():
            raise FolderError.of("task.selfwork_slots_fixed")
    task.is_archived = bool(archived)
    if task.is_archived:
        task.is_published = False
    task.save(update_fields=["is_archived", "is_published", "updated_at"])
    audit_change(task, actor=by_user, changes={"archived": task.is_archived}, request=request)
    return task


def delete_task(task, *, by_user, request=None) -> None:
    """Yalnız GÖNDƏRİŞSİZ ev tapşırığı silinir; qalan hallarda arxivləyin."""
    access.ensure_can_manage(by_user, task.folder)
    if task.kind == TaskKind.SELFWORK:
        raise FolderError.of("task.selfwork_slots_fixed")
    if task.submissions.exists():
        raise FolderError.of("task.has_submissions")
    audit_change(task, actor=by_user, action=AuditAction.DELETE, changes={"title": task.title}, request=request)
    task.delete()


@transaction.atomic
def reorder_tasks(folder, *, by_user, ordered_ids, request=None) -> int:
    access.ensure_can_manage(by_user, folder)
    tasks = {str(row.pk): row for row in folder.tasks.all()}
    ordered = []
    for raw in ordered_ids or []:
        row = tasks.get(str(raw))
        if row is None:
            raise FolderError.of("task.not_in_folder")
        ordered.append(row)
    for index, row in enumerate(ordered, start=1):
        row.order = index * 10
    FolderTask.objects.bulk_update(ordered, ["order"])
    audit_change(folder, actor=by_user, changes={"reorder_tasks": len(ordered)}, request=request)
    return len(ordered)


def add_task_attachment(task, *, by_user, file, request=None) -> TaskAttachment:
    """Müəllimin tapşırığa qoşması (şərt/şablon) — material qaydaları ilə yoxlanır."""
    access.ensure_can_manage(by_user, task.folder)
    _ensure_editable(task)
    if task.attachments.count() >= MAX_TASK_ATTACHMENTS:
        raise FolderError.of("task.attachments_limit", max=MAX_TASK_ATTACHMENTS)
    meta = prepare_upload(file, allowed_extensions=MATERIAL_EXTENSIONS, max_mb=material_max_mb())
    attachment = TaskAttachment(
        organization_id=task.organization_id,
        task=task,
        original_name=meta["original_name"],
        size=meta["size"],
        content_type=meta["content_type"],
        sha256=meta["sha256"],
        uploaded_by=by_user,
    )
    attachment.file = file
    attachment.save()
    audit_change(task, actor=by_user, changes={"attachment_added": attachment.original_name}, request=request)
    return attachment


def remove_task_attachment(attachment, *, by_user, request=None) -> None:
    """Qoşma sətri silinir (fiziki fayl saxlama yerində qalır — audit izi üçün)."""
    task = attachment.task
    access.ensure_can_manage(by_user, task.folder)
    audit_change(task, actor=by_user, changes={"attachment_removed": attachment.original_name}, request=request)
    attachment.delete()


__all__ = [
    "add_task_attachment",
    "archive_task",
    "clean_extensions",
    "create_homework",
    "create_task",
    "delete_task",
    "remove_task_attachment",
    "reorder_tasks",
    "set_task_published",
    "update_task",
]
