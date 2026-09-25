"""Qovluq mövzuları: müəllimin öz mövzusu, redaktə, gizlətmə, sıralama.

Sillabus mövzusu SİLİNMİR (növbəti sinxron onu yenidən yaradardı) — adı
dəyişdirilə və gizlədilə (arxiv) bilər. Müəllimin öz mövzusu yalnız boş olanda
silinir; bağlı material/tapşırıq varsa əvvəlcə başqa mövzuya köçürülməlidir.
"""

from __future__ import annotations

from django.db import transaction

from ..constants import TopicSource
from ..errors import FolderError
from ..models import FolderTopic
from . import access
from .events import audit_change
from .folders import clean_text, clean_title, next_order


def _week(value):
    if value in (None, ""):
        return None
    try:
        week = int(value)
    except (TypeError, ValueError):
        return None
    return week if 0 < week < 100 else None


def create_topic(folder, *, by_user, title, description: str = "", week_no=None, request=None) -> FolderTopic:
    access.ensure_can_manage(by_user, folder)
    topic = FolderTopic.objects.create(
        organization_id=folder.organization_id,
        folder=folder,
        order=next_order(folder.topics.all()),
        title=clean_title(title),
        description=clean_text(description),
        week_no=_week(week_no),
        source=TopicSource.CUSTOM,
    )
    audit_change(topic, actor=by_user, changes={"created": topic.title}, request=request)
    return topic


def update_topic(topic, *, by_user, title=None, description=None, week_no=None, request=None) -> FolderTopic:
    access.ensure_can_manage(by_user, topic.folder)
    fields = []
    if title is not None:
        topic.title = clean_title(title)
        fields.append("title")
    if description is not None:
        topic.description = clean_text(description)
        fields.append("description")
    if week_no is not None:
        topic.week_no = _week(week_no)
        fields.append("week_no")
    if fields:
        topic.save(update_fields=[*fields, "updated_at"])
        audit_change(topic, actor=by_user, changes={"fields": fields}, request=request)
    return topic


def set_topic_hidden(topic, *, by_user, hidden: bool = True, request=None) -> FolderTopic:
    """Mövzunu gizlədir/açır (``is_archived``) — tələbə gizli mövzunun materiallarını görmür."""
    access.ensure_can_manage(by_user, topic.folder)
    if topic.is_archived != bool(hidden):
        topic.is_archived = bool(hidden)
        topic.save(update_fields=["is_archived", "updated_at"])
        audit_change(topic, actor=by_user, changes={"hidden": topic.is_archived}, request=request)
    return topic


def delete_topic(topic, *, by_user, request=None) -> None:
    access.ensure_can_manage(by_user, topic.folder)
    if topic.source == TopicSource.SYLLABUS:
        raise FolderError.of("topic.syllabus_topic")
    if topic.materials.exists() or topic.tasks.exists():
        raise FolderError.of("topic.not_empty")
    audit_change(topic, actor=by_user, changes={"deleted": topic.title}, request=request)
    topic.delete()


@transaction.atomic
def reorder_topics(folder, *, by_user, ordered_ids, request=None) -> int:
    """Verilən id ardıcıllığına görə ``order`` = 10, 20, … (qovluğa aid olmayan id → xəta)."""
    access.ensure_can_manage(by_user, folder)
    topics = {str(topic.pk): topic for topic in folder.topics.all()}
    ordered = []
    for raw in ordered_ids or []:
        topic = topics.get(str(raw))
        if topic is None:
            raise FolderError.of("topic.not_in_folder")
        ordered.append(topic)
    for index, topic in enumerate(ordered, start=1):
        topic.order = index * 10
    FolderTopic.objects.bulk_update(ordered, ["order"])
    audit_change(folder, actor=by_user, changes={"reorder_topics": len(ordered)}, request=request)
    return len(ordered)


def topic_in_folder(folder, topic):
    """``topic`` (obyekt/id/None) qovluğa aiddirmi — aid deyilsə xəta; ``None`` → ``None``."""
    if topic in (None, ""):
        return None
    topic_id = getattr(topic, "pk", topic)
    found = folder.topics.filter(pk=topic_id).first()
    if found is None:
        raise FolderError.of("topic.not_in_folder")
    return found


__all__ = [
    "create_topic",
    "delete_topic",
    "reorder_topics",
    "set_topic_hidden",
    "topic_in_folder",
    "update_topic",
]
