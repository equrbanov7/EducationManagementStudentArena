"""Elanlar view-ları: istifadəçi JSON səthi (``user``) + idarə səhifələri (``manage``)."""

from .manage import manage_action, manage_create, manage_edit, manage_list, manage_preview, manage_rows
from .user import apply, attachment_download, detail_redirect, list_fragment, mark_read, popup_seen

__all__ = [
    "apply",
    "attachment_download",
    "detail_redirect",
    "list_fragment",
    "manage_action",
    "manage_create",
    "manage_edit",
    "manage_list",
    "manage_preview",
    "manage_rows",
    "mark_read",
    "popup_seen",
]
