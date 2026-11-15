"""«Sillabusu redaktə et» — müəllimin redaktəyə HARADAN keçəcəyi (sahib 2026-11-15).

Jurnalın «Sillabusa bax» paneli və redaktorun kilid banneri bu funksiyadan soruşur: «bu aktor bu dosyeni
redaktə edə bilərmi, edə bilərsə hansı yolla?». Yeni icazə qaydası YOXDUR — cavab servislərin özünün yazı
qapılarının güzgüsüdür:

* bölmə yazısı (``drafts.save_section``) — ``syllabus.edit`` açarı + ``is_author`` (dosyenin müəllifi VƏ YA
  bağlı açılışın CARİ müəllimi — təhvildən sonra yeni müəllim də);
* yeni versiya (``drafts.create_next_version``) — eyni açar; bağlı (``reused_from``) dosyedə qadağandır.

Rejimlər:

``open``         açıq versiya (qaralama / düzəliş / baxışda) və ya avtomatik təsdiq rejimində təsdiqlənmiş versiya
                 — redaktor birbaşa HƏMİN versiyada açılır; bağlı dosye də burada (redaktorda «Ayır» var);
``new_version``  qüvvədə olan nüsxə təsdiqlənib / rədd edilib / arxivdədir — əvvəl yeni QARALAMA versiya açılır
                 (``syllabus_action`` → ``new_version``), təsdiqlənmiş versiyanın üstündən YAZILMIR.
"""

from __future__ import annotations

from ..constants import PERM_EDIT
from ..editing import approved_edits_enabled
from .drafts import open_version_for
from .offerings import approved_version_for
from .scoping import is_author

EDIT_MODE_OPEN = "open"
EDIT_MODE_NEW_VERSION = "new_version"


def can_edit_content(actor, syllabus) -> bool:
    """Bölmə yazısının qapısı (``save_section``) — redaktorun «normal» rejimi və düymələr bununla açılır."""
    return bool(syllabus is not None and actor.has(PERM_EDIT) and is_author(actor, syllabus))


def edit_target(actor, syllabus) -> dict | None:
    """``{"mode", "version"}`` və ya ``None`` (redaktə hüququ / versiya yoxdur)."""
    if not can_edit_content(actor, syllabus):
        return None
    open_version = open_version_for(syllabus)
    if open_version is not None:
        return {"mode": EDIT_MODE_OPEN, "version": open_version.pk}
    approved = approved_version_for(syllabus, metadata_only=True)
    if approved is not None and approved_edits_enabled(approved):
        return {"mode": EDIT_MODE_OPEN, "version": approved.pk}
    if syllabus.reused_from_id:
        # Bağlı dosyenin məzmunu mənbədən gəlir — yeni versiya yox, redaktorun «Ayır» banneri.
        target = approved or syllabus.current_version
        return {"mode": EDIT_MODE_OPEN, "version": target.pk} if target is not None else None
    if not syllabus.versions.exists():
        return None
    return {"mode": EDIT_MODE_NEW_VERSION, "version": None}


__all__ = ["EDIT_MODE_NEW_VERSION", "EDIT_MODE_OPEN", "can_edit_content", "edit_target"]
