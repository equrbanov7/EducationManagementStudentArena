"""Qovluğun həyat dövrü: yaratma (idempotent), redaktə, status, növbəti semestrə köçürmə.

Bütün yazılar BURADAN keçir — view/UI qatı modelə birbaşa toxunmur. Hər
dəyişiklik ``core.audit.log_action``-a düşür (``events.audit_change``).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.files import File
from django.db import IntegrityError, transaction
from django.db.models import Max

from core.constants import AuditAction

from ..constants import MAX_DESCRIPTION_CHARS, MAX_TITLE_CHARS, FolderStatus, TaskKind, TopicSource
from ..errors import FolderError
from ..models import FolderMaterial, FolderTask, FolderTopic, SubjectFolder, TaskAttachment
from . import access, lookups
from .events import audit_change
from .sync import sync_from_syllabus


def clean_title(value, *, required: bool = True) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise FolderError.of("title.required")
    if len(text) > MAX_TITLE_CHARS:
        raise FolderError.of("text.too_long", max=MAX_TITLE_CHARS)
    return text


def clean_text(value, *, limit: int = MAX_DESCRIPTION_CHARS) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        raise FolderError.of("text.too_long", max=limit)
    return text


def same_org(organization, *objects) -> None:
    for obj in objects:
        if obj is not None and getattr(obj, "organization_id", None) != organization.pk:
            raise FolderError.of("folder.organization_mismatch")


def create_folder(
    *,
    organization,
    subject,
    owner,
    by_user,
    period=None,
    title: str = "",
    description: str = "",
    offering=None,
    request=None,
    require_teaching: bool = True,
) -> tuple[SubjectFolder, bool, dict]:
    """Qovluq yaradır və ya MÖVCUDU qaytarır → ``(folder, created, sync_summary)``.

    İcazə: inzibatçı istənilən müəllim üçün; müəllim YALNIZ özü üçün və yalnız
    tədris etdiyi fənn üzrə (``teaches_subject``; köçürmədə ``require_teaching=False``
    — növbəti semestrin açılışları hələ yoxdur). Yaradılan kimi sillabusdan
    mövzular + sərbəst iş slotları çəkilir.
    """
    same_org(organization, subject, period, offering)
    if not lookups.is_org_admin(by_user, organization):
        if owner.pk != getattr(by_user, "pk", None):
            raise FolderError.of("permission.denied")
        if not lookups.has_instructor_authority(owner, organization):
            raise FolderError.of("folder.not_teaching_subject")
        if require_teaching and not lookups.teaches_subject(
            owner, organization=organization, subject=subject, period=period
        ):
            raise FolderError.of("folder.not_teaching_subject")
    existing = SubjectFolder.objects.filter(
        organization=organization, subject=subject, owner=owner, period=period
    ).first()
    if existing is not None:
        return existing, False, {}
    try:
        with transaction.atomic():
            folder = SubjectFolder.objects.create(
                organization=organization,
                subject=subject,
                owner=owner,
                period=period,
                title=clean_title(title, required=False) or subject.name[:MAX_TITLE_CHARS],
                description=clean_text(description),
            )
    except IntegrityError:  # paralel ikinci yaratma — birincini qaytar
        folder = SubjectFolder.objects.get(organization=organization, subject=subject, owner=owner, period=period)
        return folder, False, {}
    audit_change(
        folder,
        actor=by_user,
        action=AuditAction.CREATE,
        changes={"subject": str(subject.pk), "period": str(getattr(period, "pk", "") or "")},
        request=request,
    )
    summary = sync_from_syllabus(folder, by_user=by_user, offering=offering)
    return folder, True, summary


def update_folder(folder, *, by_user, title=None, description=None, request=None) -> SubjectFolder:
    access.ensure_can_manage(by_user, folder)
    changes = {}
    if title is not None:
        folder.title = clean_title(title)
        changes["title"] = folder.title
    if description is not None:
        folder.description = clean_text(description)
        changes["description"] = True
    if changes:
        folder.save(update_fields=["title", "description", "updated_at"])
        audit_change(folder, actor=by_user, changes=changes, request=request)
    return folder


def set_folder_status(folder, *, by_user, status: str, request=None) -> SubjectFolder:
    """Qaralama ↔ aktiv ↔ arxiv. Arxivdən çıxarmaq da YALNIZ sahib/inzibatçıya açıqdır."""
    if status not in FolderStatus.values:
        raise FolderError.of("folder.status_invalid")
    if not access.can_manage_folder(by_user, folder):
        raise FolderError.of("permission.not_owner")
    if folder.status != status:
        previous = folder.status
        folder.status = status
        folder.save(update_fields=["status", "updated_at"])
        audit_change(folder, actor=by_user, changes={"status": [previous, status]}, request=request)
    return folder


def resync(folder, *, by_user, offering=None, request=None) -> dict:
    """Sillabus dəyişəndə strukturu yenidən uzlaşdırır (idempotent)."""
    access.ensure_can_manage(by_user, folder)
    summary = sync_from_syllabus(folder, by_user=by_user, offering=offering)
    audit_change(folder, actor=by_user, changes={"resync": summary.get("version_id")}, request=request)
    return summary


def _copy_file(field_file, target_field, name_hint: str) -> None:
    """Saxlanmış faylı YENİ təsadüfi adla köçürür (iki sətir eyni fiziki faylı paylaşmasın)."""
    field_file.open("rb")
    try:
        target_field.save(name_hint or "fayl", File(field_file.file), save=False)
    finally:
        field_file.close()


def _clone_topics(source, target) -> dict:
    """Müəllimin ÖZ mövzularını köçürür; sillabus mövzuları hədəfin öz sillabusundan gəlir."""
    mapping = {}
    by_uid = {topic.syllabus_uid: topic for topic in target.topics.filter(source=TopicSource.SYLLABUS)}
    for topic in source.topics.filter(is_archived=False):
        if topic.source == TopicSource.SYLLABUS and topic.syllabus_uid in by_uid:
            mapping[topic.pk] = by_uid[topic.syllabus_uid]
            continue
        mapping[topic.pk] = FolderTopic.objects.create(
            organization_id=target.organization_id,
            folder=target,
            order=topic.order,
            title=topic.title,
            description=topic.description,
            week_no=topic.week_no,
            source=TopicSource.CUSTOM,
        )
    return mapping


def _clone_materials(source, target, topics, by_user) -> int:
    count = 0
    for material in source.materials.filter(is_archived=False).order_by("order", "created_at"):
        clone = FolderMaterial(
            organization_id=target.organization_id,
            folder=target,
            topic=topics.get(material.topic_id),
            kind=material.kind,
            title=material.title,
            description=material.description,
            original_name=material.original_name,
            size=material.size,
            content_type=material.content_type,
            sha256=material.sha256,
            url=material.url,
            code_text=material.code_text,
            code_language=material.code_language,
            order=material.order,
            is_published=material.is_published,
            created_by=by_user,
        )
        if material.file:
            _copy_file(material.file, clone.file, material.original_name)
        clone.save()
        count += 1
    return count


def _clone_task_attachments(task, clone, by_user) -> None:
    for attachment in task.attachments.all():
        copy = TaskAttachment(
            organization_id=clone.organization_id,
            task=clone,
            original_name=attachment.original_name,
            size=attachment.size,
            content_type=attachment.content_type,
            sha256=attachment.sha256,
            uploaded_by=by_user,
        )
        _copy_file(attachment.file, copy.file, attachment.original_name)
        copy.save()


def _clone_tasks(source, target, topics, by_user) -> dict:
    stats = {"homework": 0, "selfwork": 0}
    slots = {task.slot_index: task for task in target.tasks.filter(kind=TaskKind.SELFWORK, is_archived=False)}
    for task in source.tasks.filter(is_archived=False).order_by("kind", "slot_index", "order"):
        if task.kind == TaskKind.SELFWORK:
            slot = slots.get(task.slot_index)
            if slot is None:
                continue
            # Eyni sillabus slotu: müəllimin başlıq/təlimatı və nəsil açarı keçir.
            slot.title = task.title
            slot.instructions = task.instructions
            slot.lineage_key = task.lineage_key
            slot.topic = topics.get(task.topic_id)
            slot.allowed_extensions = list(task.allowed_extensions or [])
            slot.max_file_mb, slot.max_files = task.max_file_mb, task.max_files
            slot.allow_text_answer, slot.allow_files = task.allow_text_answer, task.allow_files
            slot.save()
            _clone_task_attachments(task, slot, by_user)
            stats["selfwork"] += 1
            continue
        clone = FolderTask.objects.create(
            organization_id=target.organization_id,
            folder=target,
            topic=topics.get(task.topic_id),
            kind=TaskKind.HOMEWORK,
            title=task.title,
            instructions=task.instructions,
            allowed_extensions=list(task.allowed_extensions or []),
            max_file_mb=task.max_file_mb,
            max_files=task.max_files,
            allow_text_answer=task.allow_text_answer,
            allow_files=task.allow_files,
            order=task.order,
            is_published=False,
            lineage_key=task.lineage_key,
            created_by=by_user,
        )
        _clone_task_attachments(task, clone, by_user)
        stats["homework"] += 1
    return stats


def clone_folder(source, *, by_user, period, request=None) -> tuple[SubjectFolder, dict]:
    """Qovluğu (məs. keçən semestrdən) YENİ semestrə köçürür → ``(yeni qovluq, xülasə)``.

    Köçürülür: müəllimin öz mövzuları, materiallar (fayllar yeni adla kopyalanır),
    ev tapşırıqları (dərc olunmamış), sərbəst iş slotlarının başlıq/təlimatı
    (yeni sillabusun strukturuna uyğun slotlara). Köçürülmür: təyinatlar, son
    tarixlər, göndərişlər. Hədəf semestrdə qovluq artıq varsa xəta deyil — mövcud
    qovluq qaytarılır, məzmun İKİ DƏFƏ köçürülmür.
    """
    if not access.can_manage_folder(by_user, source):
        raise FolderError.of("permission.not_owner")
    same_org(source.organization, period)
    target, created, _summary = create_folder(
        organization=source.organization,
        subject=source.subject,
        owner=source.owner,
        by_user=by_user,
        period=period,
        title=source.title,
        description=source.description,
        request=request,
        require_teaching=False,
    )
    if not created:
        return target, {"created": False}
    if not _summary.get("has_syllabus") and source.syllabus_ref:
        # Yeni semestrin sillabusu hələ təsdiqlənməyib: mənbə qovluğun versiyası ŞABLON kimi
        # götürülür; yeni sillabus təsdiqlənəndə ``resync`` strukturu uzlaşdırır.
        template = django_apps.get_model("syllabus", "SyllabusVersion").objects.filter(pk=source.syllabus_ref).first()
        if template is not None:
            sync_from_syllabus(target, by_user=by_user, version=template)
    with transaction.atomic():
        target.source_folder = source
        target.save(update_fields=["source_folder", "updated_at"])
        topics = _clone_topics(source, target)
        materials = _clone_materials(source, target, topics, by_user)
        tasks = _clone_tasks(source, target, topics, by_user)
    audit_change(target, actor=by_user, changes={"cloned_from": str(source.pk)}, request=request)
    return target, {"created": True, "topics": len(topics), "materials": materials, **tasks}


def next_order(queryset) -> int:
    current = queryset.aggregate(value=Max("order"))["value"]
    return (current or 0) + 10


__all__ = [
    "clean_text",
    "clean_title",
    "clone_folder",
    "create_folder",
    "next_order",
    "resync",
    "same_org",
    "set_folder_status",
    "update_folder",
]
