"""Mümkünlüyün (feasibility) təminatı, yenidən yerləşdirmə və səbəb analizi.

Sərt qaydalar YERLƏŞDİRİLMİŞ hər hadisə üçün MÜTLƏQ ödənməlidir. Axtarış onları
onsuz da qəbul etmir, amma kilidlənmiş dərslərin toqquşması və ya kənar
məşğulluq kimi hallarda son təhlükəsizlik qatı lazımdır:

1. ``make_feasible`` — pozuntu qalana qədər onu yaradan sabit olmayan hadisələri
   çıxarır (toqquşmada aşağı prioritetli; qrup boşluğunda «zəif» blok);
2. ``reinsert`` — çıxarılanları pozuntusuz ən ucuz yerə qaytarmağa çalışır;
3. ``unplaced_reasons`` — yenə də yerləşməyən hər hadisə üçün domendəki hər
   xananın NİYƏ olmadığını sayır (müəllim məşğul / qrup məşğul / boşluq /
   otaq yoxdur) — istifadəçiyə «niyə» cavabı.
"""

from __future__ import annotations

from .construct import best_value
from .types import WEEKS_OF

CAUSE_ORDER = ("teacher_external", "teacher_busy", "group_busy", "group_gap", "rooms_full", "other")


def find_violations(state) -> list:
    """Cari vəziyyətdəki bütün sərt pozuntular (sabit sıra ilə)."""
    out = []
    S, P, D, T = state.S, state.P, state.D, state.T
    for r in range(T + state.C):
        occ = state.occ[r]
        for wk in (0, 1):
            for d in range(D):
                base = wk * S + d * P
                occupied = [p for p in range(P) if occ[base + p]]
                if not occupied:
                    continue
                for p in occupied:
                    if occ[base + p] > 1:
                        out.append(("clash", r, wk, d * P + p))
                if r >= T and occupied[-1] - occupied[0] + 1 != len(occupied):
                    out.append(("gap", r, wk, d))
    for b, cap in enumerate(state.bcap):
        if not cap:
            continue
        for idx, x in enumerate(state.bocc[b]):
            if x > cap:
                out.append(("building", b, idx // S, idx % S))
    return out


def _rank(state, j):
    """Saxlanma üstünlüyü: sabit > yüksək prioritet > kiçik indeks."""
    return (1 if state.fixed[j] else 0, int(state.inst.events[j].priority or 1), -j)


def _ejections(state, violation) -> list:
    kind, r, wk, where = violation
    if kind == "clash":
        occupants = state.occupants(r, wk, where)
        if len(occupants) < state.occ[r][wk * state.S + where]:
            return occupants  # kənar (dərc olunmuş) dərslə toqquşma → hamısı çıxır
        keep = max(occupants, key=lambda j: _rank(state, j)) if occupants else None
        return [j for j in occupants if j != keep]
    if kind == "gap":
        d = where
        base = wk * state.S + d * state.P
        occ = state.occ[r]
        blocks, current = [], []
        for p in range(state.P):
            if occ[base + p]:
                current.append(p)
            elif current:
                blocks.append(current)
                current = []
        if current:
            blocks.append(current)

        def members(block):
            out = []
            for p in block:
                out.extend(state.occupants(r, wk, d * state.P + p))
            return out

        scored = []
        for block in blocks:
            events = members(block)
            scored.append(
                (
                    (
                        any(state.fixed[j] for j in events),
                        sum(int(state.inst.events[j].priority or 1) for j in events),
                        len(block),
                        -block[0],
                    ),
                    events,
                )
            )
        scored.sort(key=lambda item: item[0], reverse=True)
        out = []
        for _score, events in scored[1:]:
            out.extend(events)
        return out
    if kind == "building":
        t = where
        cap = state.bcap[r]
        events = [
            j
            for j in range(state.N)
            if state.ev_b[j] == r
            and state.val[j] is not None
            and state.val[j][0] == t
            and wk in WEEKS_OF[state.val[j][1]]
        ]
        events.sort(key=lambda j: _rank(state, j), reverse=True)
        over = state.bocc[r][wk * state.S + t] - cap
        return events[len(events) - over :] if over > 0 else []
    return []


def make_feasible(state, *, max_rounds=10_000) -> dict:
    """Sərt pozuntu qalmayana qədər hadisə çıxar; qaytarır ``{"ejected", "stuck"}``."""
    ejected = []
    stuck = []
    for _round in range(max_rounds):
        violations = find_violations(state)
        if not violations:
            break
        progressed = False
        for violation in violations:
            for j in _ejections(state, violation):
                if state.fixed[j] or state.val[j] is None:
                    continue
                state.set_value(j, None)
                ejected.append(j)
                progressed = True
            if progressed:
                break
        if not progressed:
            stuck = violations
            break
    return {"ejected": ejected, "stuck": stuck}


def reinsert(state, rng, *, clock=None, deadline=None) -> int:
    """Yerləşdirilməmişləri pozuntusuz ən ucuz yerə qaytar (bir neçə keçid)."""
    placed_total = 0
    events = state.inst.events
    while True:
        pending = [i for i in range(state.N) if state.val[i] is None and not state.fixed[i] and state.values[i]]
        pending.sort(key=lambda i: (-int(events[i].priority or 1), len(state.values[i]), i))
        placed = 0
        for i in pending:
            if deadline is not None and clock is not None and clock() > deadline:
                return placed_total + placed
            best, _delta = best_value(state, i, rng)
            if best is not None:
                state.set_value(i, best)
                placed += 1
        placed_total += placed
        if not placed:
            return placed_total


def chain_insert(state, rng, *, clock=None, deadline=None) -> int:
    """Dərinlik-2 zəncir: yerləşməyəni qoy, toqquşanları çıxar, onları başqa yerə köçür.

    Yalnız ÜMUMİ xərc azalırsa saxlanır (əks halda bütün addımlar geri qaytarılır).
    SA-nın soyuq sonunda qalan «tək-tük» yerləşməyənlər üçündür."""
    placed = 0
    events = state.inst.events
    pending = [i for i in range(state.N) if state.val[i] is None and not state.fixed[i] and state.values[i]]
    pending.sort(key=lambda i: (-int(events[i].priority or 1), len(state.values[i]), i))
    for i in pending:
        if state.val[i] is not None:
            continue
        values = list(state.values[i])
        rng.shuffle(values)
        for v in values:
            if deadline is not None and clock is not None and clock() > deadline:
                return placed
            conflicts = state.conflicting(i, v)
            if not conflicts or any(state.fixed[j] for j in conflicts):
                continue
            before = state.cost
            trail = [(i, None)] + [(j, state.val[j]) for j in conflicts]
            state.commit(state.try_changes([(i, v)] + [(j, None) for j in conflicts]))
            for j in conflicts:
                best, _delta = best_value(state, j, rng)
                if best is not None:
                    trail.append((j, None))
                    state.set_value(j, best)
            if state.cost < before:
                placed += 1
                break
            for j, old in reversed(trail):
                state.set_value(j, old)
    return placed


def _cause(state, i, v) -> str:
    t, week = v
    wks = WEEKS_OF[week]
    event = state.inst.events[i]
    S, P = state.S, state.P
    if event.teacher is not None:
        r = event.teacher
        for wk in wks:
            if state.occ[r][wk * S + t]:
                return "teacher_busy" if state.occupants(r, wk, t) else "teacher_external"
    for c in event.cohorts:
        r = state.T + c
        for wk in wks:
            if state.occ[r][wk * S + t]:
                return "group_busy"
    d, p = divmod(t, P)
    for c in event.cohorts:
        occ = state.occ[state.T + c]
        for wk in wks:
            base = wk * S + d * P
            occupied = [q for q in range(P) if occ[base + q] or q == p]
            if occupied[-1] - occupied[0] + 1 != len(occupied):
                return "group_gap"
    b = state.ev_b[i]
    if b >= 0 and state.bcap[b]:
        for wk in wks:
            if state.bocc[b][wk * S + t] >= state.bcap[b]:
                return "rooms_full"
    return "other"


def unplaced_reasons(state) -> list:
    """Hər yerləşdirilməmiş hadisə: əsas səbəb kodu + səbəblər üzrə xana sayı."""
    out = []
    for i in range(state.N):
        if state.val[i] is not None:
            continue
        event = state.inst.events[i]
        values = state.values[i]
        if not values:
            out.append({"event": i, "code": event.domain_reason or "empty_domain", "counts": {}, "options": 0})
            continue
        counts: dict = {}
        for v in values:
            cause = _cause(state, i, v)
            counts[cause] = counts.get(cause, 0) + 1
        code = max(CAUSE_ORDER, key=lambda name: (counts.get(name, 0), -CAUSE_ORDER.index(name)))
        out.append({"event": i, "code": code, "counts": counts, "options": len(values)})
    return out


__all__ = ["CAUSE_ORDER", "chain_insert", "find_violations", "make_feasible", "reinsert", "unplaced_reasons"]
