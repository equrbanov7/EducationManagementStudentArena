"""RİM detal kartının 2026-11-04 blokları — «Vəzifə və bölmə», «Məzun et», «Arxivə göndər / Arxivdən çıxar».

``detail.serialize_detail`` sətri qurur; bu modul ona əlavə açarlar yazır (``detail.py`` 600 sətir büdcəsində
qalsın deyə ayrıdır). Düymələrin görünməsi UI rahatlığıdır — FAKTİKİ qapı hər əməliyyatın öz servisindədir.
"""

from __future__ import annotations

from . import graduation, placement, staff_archive
from .policy import PERM_EDIT
from .positions import position_options


def attach_cards(row: dict, user, actor, *, manageable: bool) -> None:
    status = row["status"]
    alive = status != "deleted"
    row["position_options"] = position_options()
    row["can_edit_position"] = bool(manageable and actor.has(PERM_EDIT) and alive)
    # Arxivdəki əməkdaşın rolları deaktivdir — bölmə yalnız «Arxivdən çıxar»dan sonra dəyişir.
    row["placement"] = placement.card(actor, user) if manageable and alive and status != "archived" else None
    row["graduation"] = graduation.card(actor, user, manageable=manageable) if alive else None
    row["staff_archive"] = staff_archive.card(actor, user, manageable=manageable) if alive else None

    actions = row["actions"]
    graduation_card = row["graduation"] or {}
    archive_card = row["staff_archive"] or {}
    actions["graduate"] = bool(graduation_card.get("can_graduate"))
    actions["archive_staff"] = bool(archive_card.get("can_archive"))
    actions["unarchive_staff"] = bool(archive_card.get("can_unarchive"))


__all__ = ["attach_cards"]
