"""Tələbə cədvəlində eyni dərsin təkrarı birləşdirilir (sahib 2026-10-25: «seminar … eyni xanada təkrarlanma olub»).

Tələbə həm öz bölgü qrupunun («234 K-1»), həm də ana qrupun («234 K az») jurnalında ola bilir — hər jurnalın öz
slotu var, amma bu EYNİ dərsdir (eyni fənn, müəllim, növ, gün, saat, üst/alt). Tələbə üçün bir kart göstərilir;
otağı olan slot üstün tutulur. Qrup / müəllim cədvəli və bazadakı slotlar dəyişmir.
"""

from __future__ import annotations


def _key(slot) -> tuple:
    from .schedule import effective_instructor_id

    return (
        slot.weekday,
        slot.start_time,
        slot.end_time,
        slot.week_type,
        slot.kind,
        slot.offering.subject_id,
        effective_instructor_id(slot),
    )


def merge_duplicate_slots(slots) -> list:
    """Sıranı saxlayaraq təkrar dərsləri birləşdir (otaqlı slot qalır)."""
    kept: dict = {}
    order: list = []
    for slot in slots:
        key = _key(slot)
        current = kept.get(key)
        if current is None:
            kept[key] = slot
            order.append(key)
        elif not (current.room or "").strip() and (slot.room or "").strip():
            kept[key] = slot
    return [kept[key] for key in order]


__all__ = ["merge_duplicate_slots"]
