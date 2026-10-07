"""Elanlar view-ları: istifadəçi JSON səthi (``user``) + idarə səhifələri (``manage``) + idarə JSON-u (``manage_api``)."""

from .manage import manage_action, manage_create, manage_edit, manage_list, manage_preview, manage_rows
from .manage_api import manage_audience_count, manage_recipients
from .user import ack, apply, attachment_download, detail_redirect, list_fragment, mark_read, popup_seen

__all__ = [
    "ack",
    "apply",
    "attachment_download",
    "detail_redirect",
    "list_fragment",
    "manage_action",
    "manage_audience_count",
    "manage_create",
    "manage_edit",
    "manage_list",
    "manage_preview",
    "manage_recipients",
    "manage_rows",
    "mark_read",
    "popup_seen",
]
