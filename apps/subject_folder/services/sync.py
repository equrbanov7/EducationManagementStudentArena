"""Qovluğun sillabusla İDEMPOTENT sinxronu — mövzular + sərbəst iş slotları.

Qaydalar:
  * yalnız TƏSDİQLƏNMİŞ versiya oxunur; versiya yoxdursa MÖVCUD struktur
    TOXUNULMUR (dağıdıcı sürpriz yoxdur) — nəticə ``has_syllabus=False``;
  * mövzu açarı ``syllabus_uid``-dir; başlıq bir az dəyişibsə (yazı səhvi)
    oxşarlıqla (≥ 0.75) köhnə mövzuya bağlanır, materiallar itmir;
  * sillabusdan çıxan mövzu: bağlı material/tapşırıq varsa ARXİVLƏNİR, yoxdursa silinir;
  * sərbəst iş: ``count`` slot × ``per_score`` bal. Göndərişi olan tapşırıq HEÇ
    VAXT silinmir və balı dəyişdirilmir — arxivlənir, slot üçün yeni tapşırıq
    açılır (``lineage_key`` saxlanılır, plagiat müqayisəsi davam edir);
  * müəllim başlığı dəyişməyibsə (``title == syllabus_title``) sillabusun yeni
    başlığı götürülür, dəyişibsə müəllimin mətni qalır.
"""

from __future__ import annotations

import difflib
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from ..constants import TaskKind, TopicSource
from ..models import FolderTask, FolderTopic
from . import syllabus_bridge

_CTX = "subject_folder.sync"
_FUZZY_THRESHOLD = 0.75


def default_slot_title(slot: int) -> str:
    return pgettext(_CTX, "Sərbəst iş %(n)s") % {"n": slot}


def _similar(left: str, right: str) -> float:
    return difflib.SequenceMatcher(None, (left or "").casefold(), (right or "").casefold()).ratio()


def _best_fuzzy(row, candidates, matched) -> FolderTopic | None:
    best, best_score = None, _FUZZY_THRESHOLD
    for topic in candidates:
        if topic.pk in matched:
            continue
        score = _similar(row["title"], topic.syllabus_title or topic.title)
        if topic.week_no == row["week_no"]:
            score += 0.05
        if score >= best_score:
            best, best_score = topic, score
    return best


def _topic_has_content(topic) -> bool:
    return topic.materials.exists() or topic.tasks.exists()


def _apply_row(topic, row, position, stats) -> None:
    if topic.title == topic.syllabus_title:
        topic.title = row["title"]
    stats["restored" if topic.is_archived else "updated"] += 1
    topic.syllabus_uid = row["uid"]
    topic.syllabus_title = row["title"]
    topic.week_no = row["week_no"]
    topic.order = position * 10
    topic.is_archived = False
    topic.save(
        update_fields=["syllabus_uid", "title", "syllabus_title", "week_no", "order", "is_archived", "updated_at"]
    )


def _sync_topics(folder, version) -> dict:
    stats = {"created": 0, "updated": 0, "restored": 0, "archived": 0, "deleted": 0}
    desired = syllabus_bridge.week_topics(version)
    existing = list(folder.topics.filter(source=TopicSource.SYLLABUS))
    by_uid = {topic.syllabus_uid: topic for topic in existing}
    matched: set = set()
    # 1-ci keçid: DƏQİQ açar uyğunluğu (oxşarlıq heç vaxt dəqiq uyğunluğu «oğurlamasın»).
    pairs = {}
    for position, row in enumerate(desired):
        topic = by_uid.get(row["uid"])
        if topic is not None:
            pairs[position] = topic
            matched.add(topic.pk)
    # 2-ci keçid: qalan sətirlər üçün başlıq oxşarlığı, sonra yeni mövzu.
    for position, row in enumerate(desired):
        topic = pairs.get(position)
        if topic is None:
            topic = _best_fuzzy(row, existing, matched)
            if topic is not None:
                matched.add(topic.pk)
        if topic is not None:
            _apply_row(topic, row, position, stats)
            continue
        FolderTopic.objects.create(
            organization_id=folder.organization_id,
            folder=folder,
            order=position * 10,
            title=row["title"],
            week_no=row["week_no"],
            source=TopicSource.SYLLABUS,
            syllabus_uid=row["uid"],
            syllabus_title=row["title"],
        )
        stats["created"] += 1
    for topic in existing:
        if topic.pk in matched or topic.is_archived:
            continue
        if _topic_has_content(topic):
            topic.is_archived = True
            topic.save(update_fields=["is_archived", "updated_at"])
            stats["archived"] += 1
        else:
            topic.delete()
            stats["deleted"] += 1
    return stats


def _archive_task(task) -> None:
    task.is_archived = True
    task.is_published = False
    task.save(update_fields=["is_archived", "is_published", "updated_at"])


def _new_slot(folder, slot, *, title, per_score, lineage_key=None, by_user=None) -> FolderTask:
    kwargs = {"lineage_key": lineage_key} if lineage_key else {}
    return FolderTask.objects.create(
        organization_id=folder.organization_id,
        folder=folder,
        kind=TaskKind.SELFWORK,
        title=title,
        syllabus_title=title,
        slot_index=slot,
        max_points=per_score,
        order=slot,
        is_published=False,
        created_by=by_user if getattr(by_user, "pk", None) else None,
        **kwargs,
    )


def _sync_selfwork(folder, version, *, by_user=None) -> dict:
    stats = {"option": None, "created": [], "updated": [], "archived": [], "deleted": []}
    structure = syllabus_bridge.selfwork_structure(version)
    active = {task.slot_index: task for task in folder.tasks.filter(kind=TaskKind.SELFWORK, is_archived=False)}
    count = structure["count"] if structure else 0
    if structure:
        stats["option"] = structure["option"]
        per_score = Decimal(structure["per_score"])
        titles = structure["titles"]
        for slot in range(1, count + 1):
            wanted = (titles[slot - 1] if slot - 1 < len(titles) else "") or default_slot_title(slot)
            task = active.get(slot)
            if task is None:
                _new_slot(folder, slot, title=wanted, per_score=per_score, by_user=by_user)
                stats["created"].append(slot)
                continue
            if task.max_points != per_score:
                if task.submissions.exists():
                    _archive_task(task)
                    stats["archived"].append(slot)
                    _new_slot(
                        folder,
                        slot,
                        title=wanted,
                        per_score=per_score,
                        lineage_key=task.lineage_key,
                        by_user=by_user,
                    )
                    stats["created"].append(slot)
                    continue
                task.max_points = per_score
            if task.title == task.syllabus_title:
                task.title = wanted
            task.syllabus_title = wanted
            task.save(update_fields=["max_points", "title", "syllabus_title", "updated_at"])
            stats["updated"].append(slot)
    for slot, task in sorted(active.items()):
        if slot <= count:
            continue
        if task.submissions.exists():
            _archive_task(task)
            stats["archived"].append(slot)
        else:
            task.delete()
            stats["deleted"].append(slot)
    folder.selfwork_option = structure["option"] if structure else ""
    return stats


@transaction.atomic
def sync_from_syllabus(folder, *, by_user=None, offering=None, version=None) -> dict:
    """Qovluğu təsdiqlənmiş sillabusla uzlaşdırır (idempotent). Nəticə — dəyişiklik xülasəsi.

    ``{"has_syllabus": bool, "version_id": str|None,
       "topics": {"created","updated","restored","archived","deleted"},
       "selfwork": {"option", "created": [slot…], "updated": […], "archived": […], "deleted": […]}}``
    """
    if version is None:
        version = syllabus_bridge.approved_version_for_folder(folder, offering=offering)
    if version is None:
        return {
            "has_syllabus": False,
            "version_id": None,
            "topics": {"created": 0, "updated": 0, "restored": 0, "archived": 0, "deleted": 0},
            "selfwork": {
                "option": folder.selfwork_option or None,
                "created": [],
                "updated": [],
                "archived": [],
                "deleted": [],
            },
        }
    # Paralel sinxronlar eyni slotu iki dəfə yaratmasın — qovluq sətri kilidlənir.
    type(folder).objects.select_for_update().filter(pk=folder.pk).first()
    topics = _sync_topics(folder, version)
    selfwork = _sync_selfwork(folder, version, by_user=by_user)
    folder.syllabus_ref = version.pk
    folder.synced_at = timezone.now()
    folder.save(update_fields=["selfwork_option", "syllabus_ref", "synced_at", "updated_at"])
    return {"has_syllabus": True, "version_id": str(version.pk), "topics": topics, "selfwork": selfwork}


__all__ = ["default_slot_title", "sync_from_syllabus"]
