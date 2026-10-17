"""Cədvəl redaktoru dialoqu — «Korpus → Otaq» seçiciləri üçün otaq kataloqu (sahib 2026-10-17).

«Korpusa uyğun otaqları düz seç»: otaq adları korpuslar arasında TƏKRARLANIR (məs. «203» həm 1-ci,
həm 2-ci korpusda), ona görə dialoqda əvvəl korpus seçilir, otaq siyahısı yalnız həmin korpusun
otaqlarıdır. Korpus ayrıca model deyil — ``ExamRoom.building`` mətnidir; POST-a yenə yalnız otaq
MƏTNİ gedir (``ScheduleSlot.room``, ``schedule_editor.parse_cell`` — format dəyişmir), korpus isə
yalnız siyahını daraldan süzgəc və ``action=plan``-da otaq sıralamasının açarıdır.

Otaq etiketləri ``schedule_suggest.load_rooms`` ilə EYNİDİR (ad, yoxdursa kod) — beləcə planlayıcının
otaq təklifinə klik dialoqdakı seçimə dəqiq düşür.
"""

from __future__ import annotations

import re

from django.utils.translation import pgettext

from . import campus
from .schedule_suggest import load_rooms

_CTX = "registrar.schedule_rooms"
_DIGITS = re.compile(r"(\d+)")


def _natural(text) -> tuple:
    """«2» < «10» < «101» — otaq nömrələri insan sırası ilə (sətir sırası «101» < «11» < «2» idi)."""
    return tuple(int(part) if part.isdigit() else part for part in _DIGITS.split(str(text or "").lower()))


def room_text(label, capacity) -> str:
    """Seçicidə görünən mətn: «33 · 40 nəfər»; tutum məlum deyilsə yalnız ad."""
    if not capacity:
        return label
    return pgettext(_CTX, "%(room)s · %(count)s nəfər") % {"room": label, "count": capacity}


def dialog_rooms(organization, group=None) -> dict:
    """``{"rooms": [{label, building, capacity, text}], "buildings": [...], "default_building": str}``.

    ``default_building`` — qrupun ixtisas/kafedra korpusu (``campus.default_building_for_group``), reyestrin
    yazılışı ilə; xəritə yoxdursa və ya korpus reyestrdə yoxdursa ``""`` (dialoq «bütün korpuslar» açılır).
    Eyni korpusda eyni adlı iki sətir bir dəfə göstərilir (dəyər onsuz da eyni mətndir)."""
    seen = set()
    rooms = []
    for row in load_rooms(organization):
        key = (row["label"].lower(), row["building"])
        if key in seen:
            continue
        seen.add(key)
        rooms.append(
            {
                "label": row["label"],
                "building": row["building"],
                "capacity": row["capacity"],
                "text": room_text(row["label"], row["capacity"]),
            }
        )
    rooms.sort(key=lambda room: (_natural(room["building"]), _natural(room["label"])))
    buildings = sorted({room["building"] for room in rooms if room["building"]}, key=_natural)
    home = campus.default_building_for_group(organization, group) if group is not None else ""
    return {"rooms": rooms, "buildings": buildings, "default_building": campus.match_building(buildings, home)}


__all__ = ["dialog_rooms", "room_text"]
