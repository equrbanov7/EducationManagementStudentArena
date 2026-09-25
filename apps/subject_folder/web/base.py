"""JSON cavabları, obyekt yükləyiciləri və forma sahəsi parserləri (əməl handler-ləri üçün ortaq).

Cavab forması layihənin digər əməl endpoint-ləri ilə eynidir (``workload.actions``,
``registrar.semester_actions``): uğur ``{"ok": true, …}``; imtina
``{"ok": false, "error": <kod>, "message": <mətn>, "params"?: {…}}`` — icazə 403,
tapılmayan obyekt 404, qalan domen xətaları 400. Kliyent (``cabinet.js``) mətni
``payload.message``-dən göstərir.
"""

from __future__ import annotations

import datetime
import uuid

from django.http import JsonResponse
from django.utils import timezone
from django.utils.translation import pgettext

from core.tenancy import get_request_organization, request_has_active_organization_context

from ..errors import FolderError
from ..models import (
    FolderAssignment,
    FolderMaterial,
    FolderTask,
    FolderTopic,
    SimilarityMatch,
    SubjectFolder,
    Submission,
    SubmissionFile,
    TaskAttachment,
)

CTX = "subject_folder.ui"


class ActionError(Exception):
    """Handler-in giriş/axtarış imtinası (domen xətası deyil): kod + mətn + HTTP status."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(code, message, status)
        self.code = code
        self.message = message
        self.status = status


def json_ok(**payload) -> JsonResponse:
    return JsonResponse({"ok": True, **payload})


def json_error(code: str, message: str, *, status: int = 400, params: dict | None = None) -> JsonResponse:
    body = {"ok": False, "error": code, "message": str(message)}
    if params:
        body["params"] = {key: str(value) for key, value in params.items()}
    return JsonResponse(body, status=status)


def folder_error_response(exc: FolderError) -> JsonResponse:
    return json_error(exc.code, str(exc), status=403 if exc.is_permission else 400, params=exc.params)


def request_organization(request):
    """Aktiv təşkilat konteksti (view-as/üzvlük middleware-dən) və ya ``None``."""
    organization = get_request_organization(request)
    if organization is None or not request_has_active_organization_context(request):
        return None
    return organization


def not_found() -> ActionError:
    return ActionError("not_found", pgettext(CTX, "Obyekt tapılmadı və ya artıq mövcud deyil."), status=404)


def uuid_or_none(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return uuid.UUID(text)
    except (TypeError, ValueError, AttributeError):
        return None


def _get(queryset, raw_id):
    pk = uuid_or_none(raw_id)
    if pk is None:
        raise not_found()
    row = queryset.filter(pk=pk).first()
    if row is None:
        raise not_found()
    return row


def get_folder(organization, raw_id) -> SubjectFolder:
    return _get(
        SubjectFolder.objects.filter(organization=organization).select_related(
            "organization", "subject", "period", "owner"
        ),
        raw_id,
    )


def get_topic(folder, raw_id) -> FolderTopic:
    return _get(FolderTopic.objects.filter(folder=folder), raw_id)


def optional_topic(folder, raw_id):
    """Boş dəyər — «ümumi» (mövzusuz); dolu amma yad dəyər — 404."""
    if not str(raw_id or "").strip():
        return None
    return get_topic(folder, raw_id)


def get_material(organization, raw_id) -> FolderMaterial:
    return _get(
        FolderMaterial.objects.filter(organization=organization).select_related("folder", "folder__organization"),
        raw_id,
    )


def get_task(organization, raw_id) -> FolderTask:
    return _get(
        FolderTask.objects.filter(organization=organization).select_related(
            "folder", "folder__organization", "folder__subject", "topic"
        ),
        raw_id,
    )


def get_attachment(organization, raw_id) -> TaskAttachment:
    return _get(
        TaskAttachment.objects.filter(organization=organization).select_related(
            "task", "task__folder", "task__folder__organization"
        ),
        raw_id,
    )


def get_assignment(organization, raw_id) -> FolderAssignment:
    return _get(
        FolderAssignment.objects.filter(organization=organization).select_related(
            "folder", "folder__organization", "offering", "offering__organization", "offering__group"
        ),
        raw_id,
    )


def get_submission(organization, raw_id) -> Submission:
    return _get(
        Submission.objects.filter(organization=organization).select_related(
            "task",
            "task__folder",
            "task__folder__subject",
            "assignment",
            "assignment__folder",
            "assignment__offering",
            "assignment__offering__organization",
            "assignment__offering__group",
            "enrollment",
            "student",
            "reviewed_by",
        ),
        raw_id,
    )


def get_submission_file(organization, raw_id) -> SubmissionFile:
    return _get(SubmissionFile.objects.filter(organization=organization).select_related("submission"), raw_id)


def get_match(organization, raw_id) -> SimilarityMatch:
    return _get(
        SimilarityMatch.objects.filter(organization=organization).select_related(
            "submission_a__assignment__offering", "submission_b__assignment__offering"
        ),
        raw_id,
    )


# ── Forma sahələri ───────────────────────────────────────────────────────────


def field(request, name: str, *, limit: int = 20_000) -> str:
    """POST mətni — ``None`` əvəzinə boş sətir; uzunluq servisdə də yoxlanılır."""
    return str(request.POST.get(name) or "")[: limit + 1]


def optional_field(request, name: str, *, limit: int = 20_000):
    """Sahə formada YOXDURSA ``None`` (dəyişmə), varsa mətn."""
    if name not in request.POST:
        return None
    return field(request, name, limit=limit)


def flag(request, name: str) -> bool:
    return str(request.POST.get(name) or "").strip().lower() in {"1", "true", "on", "yes"}


def optional_flag(request, name: str):
    """Checkbox dəyişikliyi: ``<name>__present`` işarəsi varsa bool, yoxsa ``None``."""
    if f"{name}__present" not in request.POST and name not in request.POST:
        return None
    return flag(request, name)


def int_or_none(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        raise ActionError("invalid_number", pgettext(CTX, "Rəqəm düzgün yazılmayıb.")) from None


def local_datetime(value):
    """``<input type="datetime-local">`` dəyəri (cari saat qurşağında) → aware datetime; boş → ``None``."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        raise ActionError("invalid_datetime", pgettext(CTX, "Tarix və saat düzgün seçilməyib.")) from None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def extensions(value):
    """«pdf, .docx  zip» → [".pdf", ".docx", ".zip"]; boş → ``None`` (servis defoltu)."""
    parts = [part.strip() for part in str(value or "").replace(";", ",").replace(" ", ",").split(",")]
    cleaned = [part if part.startswith(".") else f".{part}" for part in parts if part]
    return cleaned or None


__all__ = [
    "ActionError",
    "CTX",
    "extensions",
    "field",
    "flag",
    "folder_error_response",
    "get_assignment",
    "get_attachment",
    "get_folder",
    "get_match",
    "get_material",
    "get_submission",
    "get_submission_file",
    "get_task",
    "get_topic",
    "int_or_none",
    "json_error",
    "json_ok",
    "local_datetime",
    "not_found",
    "optional_field",
    "optional_flag",
    "optional_topic",
    "request_organization",
    "uuid_or_none",
]
