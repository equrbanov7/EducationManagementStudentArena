"""«Fənn qovluqları» (müəllim) — siyahı və qovluq redaktoru konteksti.

Vəziyyətlər (``state``): ``no_org`` · ``list`` · ``folder`` · ``missing`` (qovluq
tapılmadı / görmə hüququ yoxdur). Qovluq görünüşünün tab-ı ``sf_tab``:
``content`` (mövzular → materiallar + tapşırıqlar) və ya ``groups`` (təyinat, son
tarix, irəliləyiş). Sorğu sayı sətir sayından asılı deyil (servislərin annotasiyaları).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db.models import Q
from django.utils.translation import pgettext

from .. import public
from ..constants import SECTION_TEACHER, TaskKind
from ..models import SubjectFolder, TaskDeadline
from ..services import lookups
from . import common

_CTX = "subject_folder.ui"

TABS = ("content", "groups")
_STATUS_FILTERS = ("draft", "active", "archived")


def teacher_panel(context) -> dict:
    request, organization, user, base = common.resolve(context)
    if organization is None or not lookups.is_authenticated(user):
        return {"state": "no_org"}
    urls = {**common.endpoint_urls(), "list": common.section_url(base, SECTION_TEACHER)}
    folder_id = common.param(request, "folder")
    if folder_id:
        return _folder_state(request, organization, user, base, urls, folder_id)
    return _list_state(request, organization, user, base, urls)


# ── Siyahı ──────────────────────────────────────────────────────────────────


def _period_label(period) -> str:
    return getattr(period, "name", "") or pgettext(_CTX, "Semestrsiz")


def teachable_pairs(organization, user) -> list[dict]:
    """Aktorun tədris etdiyi (fənn, semestr) cütləri — «Yeni qovluq» dialoqu (2 sorğu)."""
    if not lookups.has_instructor_authority(user, organization):
        return []
    offerings = (
        lookups.offering_model()
        .objects.filter(organization=organization, is_active=True)
        .filter(lookups.taught_offerings_q(user))
        .select_related("subject", "period")
        .order_by("-period__start_date", "subject__name")
        .distinct()
    )
    existing = set(
        SubjectFolder.objects.filter(organization=organization, owner=user).values_list("subject_id", "period_id")
    )
    pairs, seen = [], set()
    for offering in offerings:
        key = (offering.subject_id, offering.period_id)
        if key in seen:
            continue
        seen.add(key)
        pairs.append(
            {
                "value": f"{offering.subject_id}|{offering.period_id or ''}",
                "label": f"{offering.subject.name} · {_period_label(offering.period)}",
                "has_folder": key in existing,
            }
        )
    return pairs


def _list_state(request, organization, user, base, urls) -> dict:
    status = common.param(request, "status")
    search = common.param(request, "q", limit=120)
    period_id = common.uuid_param(request, "period")
    all_folders = list(public.list_folders(organization=organization, actor=user))
    periods = {}
    for folder in all_folders:
        if folder.period_id:
            periods[folder.period_id] = folder.period
    folders = public.list_folders(
        organization=organization,
        actor=user,
        period=periods.get(period_id),
        statuses=[status] if status in _STATUS_FILTERS else None,
        search=search,
    )
    rows = [_folder_card(folder, base) for folder in folders]
    everything = [{"value": "", "label": pgettext(_CTX, "Hamısı")}]
    filter_fields = [
        {
            "name": "sf_period",
            "label": pgettext(_CTX, "Semestr"),
            "kind": "select",
            "options": everything
            + [{"value": str(pk), "label": _period_label(period)} for pk, period in periods.items()],
            "value": str(period_id or ""),
        },
        {
            "name": "sf_status",
            "label": pgettext(_CTX, "Status"),
            "kind": "select",
            "options": everything
            + [{"value": key, "label": str(public.FolderStatus(key).label)} for key in _STATUS_FILTERS],
            "value": status if status in _STATUS_FILTERS else "",
        },
        {
            "name": "sf_q",
            "label": pgettext(_CTX, "Axtarış"),
            "kind": "search",
            "value": search,
            "placeholder": pgettext(_CTX, "Fənn və ya qovluq adı…"),
            "wide": True,
        },
    ]
    pending = sum(folder.pending_review for folder in all_folders)
    return {
        "state": "list",
        "urls": urls,
        "folders": rows,
        "filter_fields": filter_fields,
        "filter_count_label": pgettext(_CTX, "Nəticə: %(count)d qovluq") % {"count": len(rows)},
        "is_filtered": bool(status or search or period_id),
        "create_options": teachable_pairs(organization, user),
        "forms": {"folder_create": common.form("folder_create")},
        "kpi_tiles": [
            {"label": pgettext(_CTX, "QOVLUQLAR"), "value": len(all_folders)},
            {
                "label": pgettext(_CTX, "AKTİV"),
                "value": sum(1 for folder in all_folders if folder.status == public.FolderStatus.ACTIVE),
            },
            {
                "label": pgettext(_CTX, "YOXLAMA GÖZLƏYİR"),
                "value": pending,
                "tone": "warning" if pending else None,
                "note": pgettext(_CTX, "göndərilmiş, baxılmamış iş"),
            },
            {
                "label": pgettext(_CTX, "QARALAMA"),
                "value": sum(1 for folder in all_folders if folder.status == public.FolderStatus.DRAFT),
            },
        ],
    }


def _folder_card(folder, base) -> dict:
    return {
        "folder": folder,
        "chip": common.folder_chip(folder.status),
        "url": common.section_url(base, SECTION_TEACHER, folder=folder.pk),
        "period_label": _period_label(folder.period),
        "counts": {
            "topics": folder.topic_count,
            "materials": folder.material_count,
            "selfwork": folder.selfwork_count,
            "homework": folder.homework_count,
            "pending": folder.pending_review,
        },
    }


# ── Qovluq ──────────────────────────────────────────────────────────────────


def _folder_state(request, organization, user, base, urls, raw_id) -> dict:
    folder_pk = common.uuid_or_none(raw_id)
    folder = (
        SubjectFolder.objects.filter(organization=organization, pk=folder_pk)
        .select_related("organization", "subject", "period", "owner")
        .first()
        if folder_pk
        else None
    )
    if folder is None or not public.can_view_folder(user, folder):
        return {"state": "missing", "urls": urls}
    tab = common.param(request, "tab")
    tab = tab if tab in TABS else "content"
    can_manage = public.can_manage_folder(user, folder)
    data = {
        "state": "folder",
        "urls": urls,
        "folder": folder,
        "chip": common.folder_chip(folder.status),
        "period_label": _period_label(folder.period),
        "owner_name": common.user_name(folder.owner),
        "can_manage": can_manage,
        "is_archived": folder.status == public.FolderStatus.ARCHIVED,
        "tab": tab,
        "tabs": [
            {
                "key": key,
                "label": label,
                "current": key == tab,
                "url": common.section_url(base, SECTION_TEACHER, folder=folder.pk, tab=key),
            }
            for key, label in (
                ("content", pgettext(_CTX, "Məzmun")),
                ("groups", pgettext(_CTX, "Qruplar və son tarixlər")),
            )
        ],
        "review_url": common.section_url(base, public.SECTION_REVIEW, folder=folder.pk),
    }
    data["forms"] = {
        "folder_update": common.form("folder_update", folder=folder.pk),
        "topic": common.form("topic_save", folder=folder.pk, topic=""),
        "material": common.form("material_save", folder=folder.pk, material=""),
        "homework": common.form("homework_create", folder=folder.pk),
        "task": common.form("task_update", task=""),
        "clone": common.form("folder_clone", folder=folder.pk),
        "assign": common.form("assign", folder=folder.pk),
        "deadline": common.form("deadline_set", assignment=""),
    }
    if tab == "groups":
        data.update(_groups_context(folder, user))
    else:
        data.update(_content_context(folder, user))
    if can_manage:
        data["clone_periods"] = _clone_periods(organization, folder)
    return data


def _content_context(folder, user) -> dict:
    contents = public.folder_contents(folder, actor=user)
    topics = []
    for row in contents["topics"]:
        topics.append(
            {
                "topic": row["topic"],
                "materials": [_material_row(material) for material in row["materials"] if not material.is_archived],
                "tasks": [_task_row(task) for task in row["tasks"]],
            }
        )
    general = {
        "materials": [
            _material_row(material) for material in contents["general"]["materials"] if not material.is_archived
        ],
        "tasks": [_task_row(task) for task in contents["general"]["tasks"]],
    }
    selfwork = [row for row in _all_tasks(topics, general) if row["task"].kind == TaskKind.SELFWORK]
    return {
        "topics": topics,
        "general": general,
        "topic_options": [
            {"value": str(row["topic"].pk), "label": row["topic"].title}
            for row in topics
            if not row["topic"].is_archived
        ],
        "material_kinds": [{"value": value, "label": str(label)} for value, label in public.MaterialKind.choices],
        "code_languages": [{"value": value, "label": str(label)} for value, label in public.CodeLanguage.choices],
        "selfwork_total": sum(row["task"].max_points or 0 for row in selfwork if not row["task"].is_archived),
        "selfwork_option": folder.selfwork_option,
    }


def _all_tasks(topics, general):
    for row in topics:
        yield from row["tasks"]
    yield from general["tasks"]


def _material_row(material) -> dict:
    return {
        "material": material,
        "download_url": common.material_download_url(material) if material.file else "",
        "size": common.human_size(material.size) if material.file else "",
        "kind_label": str(public.MaterialKind(material.kind).label),
    }


def _task_row(task) -> dict:
    return {
        "task": task,
        "kind_label": str(public.TaskKind(task.kind).label),
        "max_points": common.points_text(task.max_points),
        "extensions": ", ".join(task.allowed_extensions or []),
        "attachments": [
            {
                "attachment": attachment,
                "url": common.attachment_download_url(attachment),
                "size": common.human_size(attachment.size),
            }
            for attachment in task.attachments.all()
        ],
    }


def _groups_context(folder, user) -> dict:
    offerings = public.assignable_offerings(folder, user)
    assignments = [row["assignment"] for row in offerings if row["assignment"] is not None and row["is_active"]]
    tasks = list(folder.tasks.filter(is_archived=False).order_by("kind", "slot_index", "order", "created_at"))
    deadlines = {
        (row.assignment_id, row.task_id): row for row in TaskDeadline.objects.filter(assignment__in=assignments)
    }
    groups = []
    for assignment in assignments:
        progress = {row["task"].pk: row for row in public.task_progress(assignment)}
        groups.append(
            {
                "assignment": assignment,
                "offering": assignment.offering,
                "rows": [
                    {
                        "task": task,
                        "deadline": deadlines.get((assignment.pk, task.pk)),
                        "window": common.window_chip(public.window_state(deadlines.get((assignment.pk, task.pk)))),
                        "stats": _stats(progress.get(task.pk)),
                    }
                    for task in tasks
                ],
            }
        )
    return {
        "offerings": [
            {**row, "label": _offering_label(row["offering"]), "value": str(row["offering"].pk)} for row in offerings
        ],
        "groups": groups,
        "deadline_tasks": [{"value": str(task.pk), "label": task.title} for task in tasks],
        "late_policies": [{"value": value, "label": str(label)} for value, label in public.LatePolicy.choices],
    }


def _stats(progress) -> dict:
    """``task_progress`` sətri → cədvəl xanaları (auditoriya, göndərən, gözləyən, yekun)."""
    progress = progress or {}
    sent = sum(progress.get(key, 0) for key in ("submitted", "returned", "accepted", "checked", "rejected"))
    return {
        "audience": progress.get("audience", 0),
        "sent": sent,
        "waiting": progress.get("submitted", 0),
        "done": progress.get("accepted", 0) + progress.get("checked", 0),
        "flagged": progress.get("flagged", 0),
    }


def _offering_label(offering) -> str:
    group = getattr(offering, "group", None)
    return getattr(group, "name", "") or str(offering)


def _clone_periods(organization, folder) -> list[dict]:
    Period = django_apps.get_model("organizations", "AcademicPeriod")
    rows = Period.objects.filter(organization=organization).order_by("-start_date")
    if folder.period_id:
        rows = rows.filter(~Q(pk=folder.period_id))
    return [{"value": str(period.pk), "label": _period_label(period)} for period in rows[:12]]


__all__ = ["TABS", "teachable_pairs", "teacher_panel"]
