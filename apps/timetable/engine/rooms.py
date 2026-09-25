"""Otaq təyini — «əvvəl vaxt, sonra otaq» (UniTime/ITC təcrübəsi).

Vaxt mərhələsi korpusda eyni anda keçirilən dərs sayını otaq sayı ilə
məhdudlaşdırır; bu mərhələ isə hər yerləşdirilmiş dərsə KONKRET otaq təklif edir:

* yalnız qrupun korpusundakı otaqlar (korpus bilinmirsə — istənilən);
* həftəlik dərs üçün otaq HƏR İKİ həftədə boş olmalıdır;
* tutum məlumdursa ``tutum >= tələbə sayı``, ən kiçik uyğun otaq seçilir
  (böyük auditoriyalar axınlar üçün qalsın); tutumu naməlum (0) otaqlar sonda;
* eyni qrup əvvəlki cütdə hansı otaqdadırsa, mümkünsə eyni otaqda qalır
  (qrup binada gəzişməsin);
* kənar (dərc olunmuş) dərslərin tutduğu otaqlar məşğul sayılır.

Nəticə yalnız TƏKLİFDİR — dərcdən əvvəl redaktə edilə bilər.
"""

from __future__ import annotations

from .types import WEEK_BOTH, WEEKS_OF


def assign_rooms(instance, values) -> tuple[list, dict]:
    """Hər hadisə üçün otaq indeksi (və ya ``None``) + statistika."""
    rooms = instance.rooms
    events = instance.events
    P = instance.pairs
    result = [None] * len(events)
    stats = {"assigned": 0, "missing": 0, "no_rooms": 0}
    if not rooms:
        stats["no_rooms"] = sum(1 for v in values if v is not None)
        return result, stats
    by_building: dict = {}
    for k, room in enumerate(rooms):
        by_building.setdefault(room.building, []).append(k)
    every = list(range(len(rooms)))
    for bucket in list(by_building.values()) + [every]:
        bucket.sort(key=lambda k: (rooms[k].capacity == 0, rooms[k].capacity, rooms[k].label, k))
    used = {(room, week, t) for room, week, t in instance.room_busy}
    order = sorted(
        (i for i, v in enumerate(values) if v is not None),
        key=lambda i: (
            values[i][0],
            0 if values[i][1] == WEEK_BOTH else 1,
            -int(events[i].size or 0),
            -int(events[i].priority or 1),
            events[i].key,
        ),
    )
    last_room: dict = {}

    def free(k, t, wks):
        return all((k, wk, t) not in used for wk in wks)

    def fits(k, size):
        cap = rooms[k].capacity
        return cap == 0 or cap >= size

    for i in order:
        t, week = values[i]
        wks = WEEKS_OF[week]
        d, p = divmod(t, P)
        event = events[i]
        if event.building is None:
            candidates = every
        else:
            candidates = by_building.get(event.building, [])

        size = int(event.size or 0)
        choice = None
        for c in event.cohorts:
            prev = last_room.get((c, d))
            if prev and prev[0] == p - 1 and prev[1] in candidates and free(prev[1], t, wks) and fits(prev[1], size):
                choice = prev[1]
                break
        if choice is None:
            for k in candidates:
                if free(k, t, wks) and fits(k, size):
                    choice = k
                    break
        if choice is None:
            stats["missing"] += 1
            continue
        result[i] = choice
        stats["assigned"] += 1
        for wk in wks:
            used.add((choice, wk, t))
        for c in event.cohorts:
            last_room[(c, d)] = (p, choice)
    return result, stats


__all__ = ["assign_rooms"]
