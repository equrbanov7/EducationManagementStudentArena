"""Qaralamanın əl ilə düzəlişi — kilid və köçürmə (SƏRT qaydalar server tərəfdə yoxlanır).

Köçürmə mühərrikin EYNİ vəziyyət modelindən keçir: nümunə yenidən qurulur, cari
qaralama yüklənir, yeni dəyər sınanır və ``find_violations`` fərqi baxılır —
toqquşma, qrupda boşluq, korpus dolu, növbədən/əlçatanlıqdan kənar hallarda HEÇ NƏ
yazılmır və səbəb qaytarılır. Uğurlu köçürmədən sonra otaq təklifləri və KPI-lar
yenilənir.
"""

from __future__ import annotations

from django.db import transaction
from django.utils.translation import pgettext

from ..engine import WEEK_BOTH, WEEK_EVEN, WEEK_FROM_CODE, WEEK_ODD, Weights, check
from ..engine.repair import find_violations
from ..engine.rooms import assign_rooms
from ..engine.state import State
from .runs import build_for_run

_CTX = "timetable.edit"


class EditError(Exception):
    def __init__(self, code, message, conflicts=None, status=400):
        conflicts = list(conflicts or [])
        super().__init__(code, message, conflicts, status)
        self.code = code
        self.message = message
        self.conflicts = conflicts
        self.status = status


def set_lock(run, key, locked) -> int:
    count = run.slots.filter(event_key=key).update(locked=bool(locked))
    if not count:
        raise EditError("not_found", pgettext(_CTX, "Dərs qaralamada tapılmadı."), status=404)
    return count


def _load(run):
    problem = build_for_run(run)
    index = {meta["key"]: i for i, meta in enumerate(problem.events)}
    state = State(problem.instance, Weights.from_dict((run.params or {}).get("weights")))
    rows = {}
    for row in run.slots.all().only("event_key", "weekday", "pair", "week_type"):
        rows.setdefault(row.event_key, row)
    values = [None] * len(problem.events)
    for key, row in rows.items():
        i = index.get(key)
        if i is None or row.weekday is None:
            continue
        t = problem.cell_to_t(row.weekday, row.pair)
        if t is not None:
            values[i] = (t, WEEK_FROM_CODE.get(row.week_type, WEEK_BOTH))
    state.load(values)
    return problem, state, index


def _describe(problem, state, violation) -> str:
    kind, r, wk, where = violation
    week = pgettext(_CTX, "üst həftə") if wk == 0 else pgettext(_CTX, "alt həftə")
    if kind == "building":
        return pgettext(_CTX, "%(building)s korpusunda həmin vaxt boş otaq qalmır (%(week)s).") % {
            "building": problem.instance.buildings[r].label,
            "week": week,
        }
    if kind == "gap":
        label = problem.instance.cohorts[r - state.T].label
        return pgettext(_CTX, "%(group)s qrupunun günündə boş cüt yaranır (%(week)s) — qrupda boşluq qadağandır.") % {
            "group": label,
            "week": week,
        }
    others = state.occupants(r, wk, where)
    subjects = ", ".join(sorted({problem.events[j]["subject"] for j in others})) or pgettext(
        _CTX, "başqa fakültənin dərc olunmuş dərsi"
    )
    if r < state.T:
        name = problem.teacher_names.get(problem.teacher_ids[r], "")
        return pgettext(_CTX, "Müəllim %(teacher)s həmin vaxt məşğuldur: %(subjects)s (%(week)s).") % {
            "teacher": name,
            "subjects": subjects,
            "week": week,
        }
    return pgettext(_CTX, "%(group)s qrupunun həmin vaxt dərsi var: %(subjects)s (%(week)s).") % {
        "group": problem.instance.cohorts[r - state.T].label,
        "subjects": subjects,
        "week": week,
    }


def _domain_reason(problem, event, t) -> str:
    for c in event.cohorts:
        if t not in problem.instance.cohorts[c].allowed:
            return pgettext(_CTX, "Bu saat %(group)s qrupunun növbəsinə daxil deyil.") % {
                "group": problem.instance.cohorts[c].label
            }
    return pgettext(_CTX, "Müəllim bu saatda gələ bilmir (əlçatanlıq).")


def move(run, key, *, weekday, pair, week_type) -> dict:
    """Hadisəni yeni xanaya köçür; pozuntu varsa ``EditError`` (409, səbəblərlə)."""
    problem, state, index = _load(run)
    i = index.get(key)
    if i is None:
        raise EditError(
            "stale",
            pgettext(_CTX, "Qaralama köhnəlib (açılışlar dəyişib) — yenidən işlədin."),
            status=409,
        )
    event = problem.instance.events[i]
    try:
        t = problem.cell_to_t(int(weekday), int(pair))
    except (TypeError, ValueError):
        t = None
    if t is None:
        raise EditError("invalid", pgettext(_CTX, "Gün və dərs saatı düzgün seçilməlidir."))
    week = WEEK_FROM_CODE.get(str(week_type or ""), None)
    if event.biweekly and week not in (WEEK_ODD, WEEK_EVEN):
        week = WEEK_ODD
    if not event.biweekly:
        week = WEEK_BOTH
    if run.slots.filter(event_key=key, locked=True).exists():
        raise EditError("locked", pgettext(_CTX, "Dərs kilidlidir — əvvəlcə kilidi açın."), status=409)
    if t not in event.domain:
        raise EditError("outside_domain", _domain_reason(problem, event, t), status=409)
    before = set(find_violations(state))
    state.try_changes([(i, (t, week))])
    added = [violation for violation in find_violations(state) if violation not in before]
    if added:
        conflicts = [_describe(problem, state, violation) for violation in added[:6]]
        state.undo()
        raise EditError("conflict", conflicts[0], conflicts=conflicts, status=409)
    state.commit(0)
    rooms, _stats = assign_rooms(problem.instance, state.val)
    by_key = {meta["key"]: k for k, meta in enumerate(problem.events)}
    with transaction.atomic():
        rows = list(run.slots.all())
        for row in rows:
            k = by_key.get(row.event_key)
            if k is None:
                continue
            room_index = rooms[k]
            room = problem.rooms[room_index] if room_index is not None else {}
            row.room = (room.get("label") or "")[:64]
            row.room_ref = (room.get("id") or "")[:64]
            if row.event_key == key:
                row.weekday, row.pair = problem.t_to_cell(t)
                row.week_type = row_week(week)
                row.is_manual = True
                row.reason = ""
                row.reason_code = ""
        if rows:
            fields = ["room", "room_ref", "weekday", "pair", "week_type", "is_manual", "reason", "reason_code"]
            type(rows[0]).objects.bulk_update(rows, fields, batch_size=500)
        kpis = dict(run.kpis or {})
        fresh = check(problem.instance, state.val, rooms)
        kpis.update({k: fresh[k] for k in ("placed", "unplaced", "events", "hard", "hard_total", "soft")})
        kpis["manual_edits"] = int(kpis.get("manual_edits") or 0) + 1
        run.kpis = kpis
        run.save(update_fields=["kpis", "updated_at"])
    weekday_value, pair_value = problem.t_to_cell(t)
    return {"key": key, "weekday": weekday_value, "pair": pair_value, "week_type": row_week(week)}


def row_week(week) -> str:
    return {WEEK_BOTH: "all", WEEK_ODD: "odd", WEEK_EVEN: "even"}[week]


__all__ = ["EditError", "move", "set_lock"]
