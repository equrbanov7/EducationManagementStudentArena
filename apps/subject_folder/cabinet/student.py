"""«Fənn qovluqlarım» (tələbə) — qovluq siyahısı, qovluq içi və tapşırıq səhifəsi konteksti.

Vəziyyətlər: ``no_org`` · ``list`` · ``folder`` (``sf_folder``) · ``task`` (``sf_folder`` +
``sf_task``) · ``missing``. Bildiriş keçidləri eyni parametrləri daşıyır
(``services.notify.profile_link``). Tələbə YALNIZ aktiv təyinatlı, aktiv qovluğun
dərc edilmiş məzmununu görür (``student_folders`` / ``folder_contents`` servis qaydası);
oxşarlıq bayrağı və müəllimin daxili qeydləri burada yoxdur.
"""

from __future__ import annotations

from django.utils.translation import pgettext

from .. import public
from ..constants import FINAL_STATUSES, SECTION_STUDENT, SubmissionStatus, TaskKind
from ..errors import FolderError
from ..services import lookups
from . import common

_CTX = "subject_folder.ui"


def student_panel(context) -> dict:
    request, organization, user, base = common.resolve(context)
    if organization is None or not lookups.is_authenticated(user):
        return {"state": "no_org"}
    entries = public.student_folders(organization=organization, student=user)
    urls = {**common.endpoint_urls(), "list": common.section_url(base, SECTION_STUDENT)}
    folder_id = common.uuid_param(request, "folder")
    if folder_id is None:
        return _list_state(entries, base, urls)
    entry = next((row for row in entries if row["folder"].pk == folder_id), None)
    if entry is None:
        return {"state": "missing", "urls": urls}
    task_id = common.uuid_param(request, "task")
    if task_id is not None:
        state = next((row for row in entry["tasks"] if row["task"].pk == task_id), None)
        if state is not None:
            return _task_state(entry, state["task"], user, base, urls)
        return {"state": "missing", "urls": urls, "folder_url": _folder_url(base, entry)}
    return _folder_state(entry, user, base, urls)


def _folder_url(base, entry, **params) -> str:
    return common.section_url(base, SECTION_STUDENT, folder=entry["folder"].pk, **params)


def _teacher_name(entry) -> str:
    """Qovluğun sahibi (müəllim) — ``student_folders`` onu artıq birləşdirib (əlavə sorğu yoxdur)."""
    return common.user_name(entry["folder"].owner)


def _list_state(entries, base, urls) -> dict:
    cards = []
    for entry in entries:
        offering = entry["offering"]
        cards.append(
            {
                "entry": entry,
                "url": _folder_url(base, entry),
                "subject": entry["folder"].subject.name,
                "title": entry["folder"].title,
                "teacher": _teacher_name(entry),
                "group": getattr(getattr(offering, "group", None), "name", ""),
                "period": getattr(getattr(offering, "period", None), "name", ""),
                "counts": entry["counts"],
            }
        )
    open_total = sum(entry["counts"]["open"] for entry in entries)
    returned_total = sum(entry["counts"]["returned"] for entry in entries)
    return {
        "state": "list",
        "urls": urls,
        "cards": cards,
        "kpi_tiles": [
            {"label": pgettext(_CTX, "QOVLUQLAR"), "value": len(entries)},
            {
                "label": pgettext(_CTX, "AÇIQ TAPŞIRIQ"),
                "value": open_total,
                "tone": "warning" if open_total else None,
                "note": pgettext(_CTX, "göndərilməyi gözləyir"),
            },
            {
                "label": pgettext(_CTX, "QAYTARILIB"),
                "value": returned_total,
                "tone": "warning" if returned_total else None,
                "note": pgettext(_CTX, "rəyə görə yenidən işləyin"),
            },
            {"label": pgettext(_CTX, "YEKUNLAŞIB"), "value": sum(entry["counts"]["done"] for entry in entries)},
        ],
    }


def _task_summary(state, base, entry) -> dict:
    task = state["task"]
    submission = state["submission"]
    return {
        "task": task,
        "url": _folder_url(base, entry, task=task.pk),
        "kind_label": str(TaskKind(task.kind).label),
        "max_points": common.points_text(task.max_points),
        "chip": common.status_chip(state["status"]),
        "window": common.window_chip(state["window"]),
        "due_at": state["window"].get("due_at"),
        "points": common.points_text(getattr(submission, "points", None)) if submission is not None else "",
        "needs_action": state["can_submit"] and state["status"] != SubmissionStatus.RETURNED,
        "returned": state["status"] == SubmissionStatus.RETURNED,
    }


def _folder_state(entry, user, base, urls) -> dict:
    folder = entry["folder"]
    try:
        contents = public.folder_contents(folder, actor=user)
    except FolderError:
        return {"state": "missing", "urls": urls}
    states = {row["task"].pk: row for row in entry["tasks"]}

    def tasks_of(rows):
        return [_task_summary(states[task.pk], base, entry) for task in rows if task.pk in states]

    def materials_of(rows):
        return [
            {
                "material": material,
                "download_url": common.material_download_url(material) if material.file else "",
                "size": common.human_size(material.size) if material.file else "",
                "kind_label": str(public.MaterialKind(material.kind).label),
            }
            for material in rows
        ]

    topics = [
        {"topic": row["topic"], "materials": materials_of(row["materials"]), "tasks": tasks_of(row["tasks"])}
        for row in contents["topics"]
    ]
    topics = [row for row in topics if row["materials"] or row["tasks"]]
    general = {
        "materials": materials_of(contents["general"]["materials"]),
        "tasks": tasks_of(contents["general"]["tasks"]),
    }
    selfwork = [row for row in entry["tasks"] if row["task"].kind == TaskKind.SELFWORK]
    earned = sum(
        (row["submission"].points or 0)
        for row in selfwork
        if row["submission"] is not None and row["status"] == SubmissionStatus.ACCEPTED
    )
    return {
        "state": "folder",
        "urls": urls,
        "entry": entry,
        "folder": folder,
        "teacher": _teacher_name(entry),
        "group": getattr(getattr(entry["offering"], "group", None), "name", ""),
        "topics": topics,
        "general": general,
        "selfwork_earned": common.points_text(earned),
        "has_selfwork": bool(selfwork),
        "counts": entry["counts"],
    }


def _task_state(entry, task, user, base, urls) -> dict:
    try:
        view = public.student_task_view(task, entry["assignment"], user)
    except FolderError:
        return {"state": "missing", "urls": urls, "folder_url": _folder_url(base, entry)}
    current = view["submission"]
    draft = current if current is not None and current.status == SubmissionStatus.DRAFT else None
    attempts = [
        {
            "attempt": attempt,
            "chip": common.status_chip(attempt.status),
            "points": common.points_text(attempt.points),
            "files": [
                {"file": row, "url": common.submission_file_url(row), "size": common.human_size(row.size)}
                for row in attempt.files.all()
            ],
        }
        for attempt in view["attempts"]
        if attempt.status != SubmissionStatus.DRAFT
    ]
    extensions = task.allowed_extensions or []
    return {
        "state": "task",
        "urls": urls,
        "entry": entry,
        "folder": entry["folder"],
        "folder_url": _folder_url(base, entry),
        "task": task,
        "assignment": entry["assignment"],
        "kind_label": str(TaskKind(task.kind).label),
        "max_points": common.points_text(task.max_points),
        "chip": common.status_chip(view["status"]),
        "window": common.window_chip(view["window"]),
        "due_at": view["window"].get("due_at"),
        "opens_at": view["window"].get("opens_at"),
        "is_late_window": view["window"].get("state") == "late",
        "attachments": [
            {"attachment": row, "url": common.attachment_download_url(row), "size": common.human_size(row.size)}
            for row in view["attachments"]
        ],
        "attempts": list(reversed(attempts)),
        "draft": draft,
        "draft_files": [
            {"file": row, "size": common.human_size(row.size)} for row in (draft.files.all() if draft else [])
        ],
        "can_submit": view["can_submit"],
        "blocked_text": common.blocked_text(view["blocked_reason"]),
        "is_final": view["status"] in FINAL_STATUSES,
        "accept": ",".join(extensions),
        "extensions_label": ", ".join(extensions),
        "remaining_files": max(0, task.max_files - len(draft.files.all())) if draft else task.max_files,
    }


__all__ = ["student_panel"]
