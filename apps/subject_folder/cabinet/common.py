"""Kabinet kontekstinin ortaq köməkçiləri: aktor/təşkilat, ``sf_*`` parametrləri, çiplər, URL-lər."""

from __future__ import annotations

import uuid
from decimal import Decimal
from urllib.parse import urlencode

from django.template.defaultfilters import filesizeformat
from django.urls import NoReverseMatch, reverse
from django.utils.translation import pgettext

from core.tenancy import get_request_organization, request_has_active_organization_context

from ..constants import FolderStatus, JournalSyncStatus, SubmissionStatus
from ..errors import display_number
from ..services.assignments import WINDOW_CLOSED, WINDOW_LATE, WINDOW_NOT_OPEN

CTX = "subject_folder.ui"
PREFIX = "sf_"
#: URL şablonlarındakı yer tutucu id (JS onu real id ilə əvəzləyir).
PLACEHOLDER = "00000000-0000-0000-0000-000000000000"
PAGE_SIZE = 25


def resolve(context):
    """Şablon kontekstindən ``(request, organization|None, user, profile_base_url)``."""
    request = context.get("request")
    user = getattr(request, "user", None)
    organization = get_request_organization(request) if request is not None else None
    if organization is not None and not request_has_active_organization_context(request):
        organization = None
    base_url = context.get("profile_base_url") or _profile_url()
    return request, organization, user, base_url


def _profile_url() -> str:
    try:
        return reverse("accounts:profile")
    except NoReverseMatch:  # pragma: no cover — accounts URL-ləri yüklənməyib
        return "/accounts/profile/"


def param(request, name: str, *, limit: int = 64) -> str:
    if request is None:
        return ""
    return str(request.GET.get(PREFIX + name) or "").strip()[:limit]


def uuid_or_none(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return uuid.UUID(text)
    except (TypeError, ValueError, AttributeError):
        return None


def uuid_param(request, name: str):
    return uuid_or_none(param(request, name))


def section_url(base_url: str, section: str, **params) -> str:
    query = {"section": section}
    query.update({PREFIX + key: value for key, value in params.items() if value not in (None, "")})
    return f"{base_url}?{urlencode(query)}"


def endpoint_urls() -> dict:
    """JS-ə ``data-*`` ilə ötürülən endpoint-lər (id yerinə ``PLACEHOLDER``)."""
    return {
        "action": reverse("subject_folder:action"),
        "review_detail": reverse("subject_folder:review_detail", args=[PLACEHOLDER]),
        "review_preview": reverse("subject_folder:review_preview", args=[PLACEHOLDER]),
    }


def form(action: str, **hidden) -> dict:
    """``_form_dialog.html`` / ``_reason_dialog.html`` üçün forma atributları + gizli sahələr.

    Atribut ADLARI yalnız serverdən gəlir (şablon müqaviləsi); ``cabinet.js`` formu
    ``form[data-sf-form]`` ilə tapır və ``FormData`` kimi ``subject_folder:action``-a göndərir.
    """
    fields = [{"name": "action", "value": action, "keep": True}]
    fields += [{"name": name, "value": str(value), "keep": True} for name, value in hidden.items() if value is not None]
    return {"data": {"data-sf-form": "1"}, "hidden": fields}


def material_download_url(material) -> str:
    return reverse("subject_folder:material_download", args=[material.pk])


def attachment_download_url(attachment) -> str:
    return reverse("subject_folder:task_attachment_download", args=[attachment.pk])


def submission_file_url(row) -> str:
    return reverse("subject_folder:submission_file_download", args=[row.pk])


def human_size(size) -> str:
    """Fayl ölçüsü — Django-nun lokallaşdırılmış ``filesizeformat``-ı (vahidlər dörd dildə tərcümədədir)."""
    try:
        return filesizeformat(int(size or 0))
    except (TypeError, ValueError):
        return ""


def points_text(value) -> str:
    if value is None:
        return ""
    return str(display_number(value if isinstance(value, Decimal) else Decimal(str(value))))


# ── Çiplər (``ems-badge`` tonları; rəng yalnız CSS token-dir) ────────────────

_STATUS_TONES = {
    SubmissionStatus.DRAFT.value: "neutral",
    SubmissionStatus.SUBMITTED.value: "primary",
    SubmissionStatus.RETURNED.value: "warning",
    SubmissionStatus.ACCEPTED.value: "success",
    SubmissionStatus.CHECKED.value: "success",
    SubmissionStatus.REJECTED.value: "danger",
}


def status_chip(status) -> dict:
    if not status:
        return {"label": pgettext(CTX, "Başlanmayıb"), "tone": "muted", "key": "none"}
    return {"label": str(SubmissionStatus(status).label), "tone": _STATUS_TONES.get(status, "neutral"), "key": status}


def window_chip(window: dict | None) -> dict:
    window = window or {}
    state = window.get("state")
    if state == WINDOW_NOT_OPEN:
        return {"label": pgettext(CTX, "Hələ açılmayıb"), "tone": "muted", "key": state}
    if state == WINDOW_LATE:
        return {"label": pgettext(CTX, "Gecikmə ilə açıqdır"), "tone": "warning", "key": state}
    if state == WINDOW_CLOSED:
        return {"label": pgettext(CTX, "Bağlanıb"), "tone": "danger", "key": state}
    if window.get("due_at"):
        return {"label": pgettext(CTX, "Açıqdır"), "tone": "success", "key": "open"}
    return {"label": pgettext(CTX, "Son tarix yoxdur"), "tone": "neutral", "key": "open"}


_SYNC_TONES = {
    JournalSyncStatus.PENDING.value: "warning",
    JournalSyncStatus.SYNCED.value: "success",
    JournalSyncStatus.BLOCKED.value: "danger",
}


def sync_chip(status) -> dict | None:
    if not status or status == JournalSyncStatus.NONE:
        return None
    return {"label": str(JournalSyncStatus(status).label), "tone": _SYNC_TONES.get(status, "neutral"), "key": status}


_FOLDER_TONES = {
    FolderStatus.DRAFT.value: "neutral",
    FolderStatus.ACTIVE.value: "success",
    FolderStatus.ARCHIVED.value: "muted",
}


def folder_chip(status) -> dict:
    return {"label": str(FolderStatus(status).label), "tone": _FOLDER_TONES.get(status, "neutral"), "key": status}


def blocked_text(reason) -> str:
    """``task_state.blocked_reason`` → tələbəyə izah (FolderError kataloqu ilə eyni mətnlər)."""
    from ..errors import FolderError

    return str(FolderError.of(reason)) if reason else ""


def user_name(user) -> str:
    if user is None:
        return ""
    full = (user.get_full_name() or "").strip() if hasattr(user, "get_full_name") else ""
    return full or getattr(user, "username", "") or ""


__all__ = [
    "CTX",
    "PAGE_SIZE",
    "PLACEHOLDER",
    "PREFIX",
    "attachment_download_url",
    "blocked_text",
    "endpoint_urls",
    "folder_chip",
    "form",
    "human_size",
    "material_download_url",
    "param",
    "points_text",
    "resolve",
    "section_url",
    "status_chip",
    "submission_file_url",
    "sync_chip",
    "user_name",
    "uuid_or_none",
    "uuid_param",
    "window_chip",
]
