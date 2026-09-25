"""Lokal axtarış — simulyasiya olunmuş tavlanma (SA) + IFS üslubunda «ejection».

Hərəkətlər (ehtimallar ``MOVE_MIX``-dədir):

* **place/eject** — yerləşdirilməmiş hadisəni təsadüfi dəyərə qoy, toqquşan
  (sabit olmayan) hadisələri çıxar (Iterative Forward Search-in konflikt-yönlü
  addımı). Prioritetli dərs aşağı prioritetlini sıxışdıra bilir;
* **move** — hadisəni domenindəki təsadüfi dəyərə köçür;
* **swap** — ortaq resursu (qrup/müəllim) olan iki hadisə yerlərini dəyişir;
* **shift** — eyni gündə qonşu cütə sürüşdür (günü sıxlaşdırır);
* **flip** — iki həftədən bir dərsin üst/alt həftəsini dəyiş.

Qəbul qaydası klassik Metropolis-dir: ``delta <= 0`` həmişə, əks halda
``exp(-delta/T)`` ehtimalı ilə. Temperatur ``t_start → t_end`` həndəsi azalır;
irəliləyiş payı iterasiya büdcəsi verilibsə İTERASİYAYA (deterministik), yoxdursa
VAXTA görə hesablanır. Sərt çəki (10^6) heç vaxt qəbul olunmur — axtarış daim
mümkün (feasible) bölgədə qalır, yalnız yerləşdirilməmişlər azalır.
"""

from __future__ import annotations

import math

from .types import WEEK_EVEN, WEEK_ODD

MOVE_MIX = (
    ("place", 0.18),
    ("move", 0.40),
    ("swap", 0.25),
    ("shift", 0.10),
    ("flip", 0.07),
)


class _Unplaced:
    """O(1) əlavə/silmə ilə yerləşdirilməmişlər çoxluğu (təsadüfi seçim üçün)."""

    def __init__(self, items):
        self.items = list(items)
        self.pos = {i: k for k, i in enumerate(self.items)}

    def add(self, i):
        if i not in self.pos:
            self.pos[i] = len(self.items)
            self.items.append(i)

    def discard(self, i):
        k = self.pos.pop(i, None)
        if k is None:
            return
        last = self.items.pop()
        if k < len(self.items):
            self.items[k] = last
            self.pos[last] = k

    def __len__(self):
        return len(self.items)


def _thresholds(has_unplaced):
    mix = [(name, weight) for name, weight in MOVE_MIX if has_unplaced or name != "place"]
    total = sum(weight for _name, weight in mix)
    acc = 0.0
    out = []
    for name, weight in mix:
        acc += weight / total
        out.append((acc, name))
    return out


def _propose(state, rng, kind, movable, unplaced, value_sets):
    """Bir hərəkət təklif et → ``[(event, new_value)]`` və ya ``None``."""
    val = state.val
    if kind == "place" and not len(unplaced):
        kind = "move"  # həddlər 256 iterasiyada bir yenilənir — arada siyahı boşala bilər
    if kind == "place":
        i = unplaced.items[int(rng.random() * len(unplaced))]
        values = state.values[i]
        v = values[int(rng.random() * len(values))]
        conflicts = state.conflicting(i, v)
        if any(state.fixed[j] for j in conflicts):
            return None
        return [(i, v)] + [(j, None) for j in conflicts]
    i = movable[int(rng.random() * len(movable))]
    current = val[i]
    if kind == "move":
        values = state.values[i]
        v = values[int(rng.random() * len(values))]
        return None if v == current else [(i, v)]
    if current is None:
        return None
    if kind == "swap":
        res = state.ev_res[i]
        r = res[int(rng.random() * len(res))]
        mates = state.res_events[r]
        j = mates[int(rng.random() * len(mates))]
        other = val[j]
        if j == i or other is None or state.fixed[j] or other == current:
            return None
        events = state.inst.events
        if events[i].biweekly == events[j].biweekly:
            new_i, new_j = other, current
        else:
            new_i, new_j = (other[0], current[1]), (current[0], other[1])
        if new_i not in value_sets[i] or new_j not in value_sets[j]:
            return None
        return [(i, new_i), (j, new_j)]
    t, week = current
    if kind == "shift":
        d, p = divmod(t, state.P)
        p2 = p + (1 if rng.random() < 0.5 else -1)
        if p2 < 0 or p2 >= state.P:
            return None
        v = (d * state.P + p2, week)
        return [(i, v)] if v in value_sets[i] else None
    if kind == "flip":
        if week not in (WEEK_ODD, WEEK_EVEN):
            return None
        v = (t, WEEK_EVEN if week == WEEK_ODD else WEEK_ODD)
        return [(i, v)] if v in value_sets[i] else None
    return None


def anneal(state, rng, *, clock, budget_seconds, max_iterations=0, t_start=30.0, t_end=0.4, progress=None) -> dict:
    """SA dövrü; ən yaxşı (ən ucuz) vəziyyətə qayıdır. Statistika qaytarır."""
    movable = [i for i in range(state.N) if not state.fixed[i] and state.values[i]]
    stats = {"iterations": 0, "accepted": 0, "improved": 0, "elapsed": 0.0}
    if not movable:
        return stats
    value_sets = [set(values) for values in state.values]
    unplaced = _Unplaced(i for i in movable if state.val[i] is None)
    start = clock()
    budget = max(0.0, float(budget_seconds or 0))
    limit = int(max_iterations or 0)
    snap_cost = state.cost
    snap_vals = list(state.val)
    snap_it = 0
    temperature = t_start
    thresholds = _thresholds(len(unplaced) > 0)
    last_progress = start
    it = accepted = 0
    ratio = t_end / t_start if t_start > 0 else 1.0
    while True:
        if it & 255 == 0:
            now = clock()
            frac_time = (now - start) / budget if budget else 0.0
            frac = it / limit if limit else frac_time
            if (limit and it >= limit) or (budget and frac_time >= 1.0) or (not limit and not budget):
                break
            frac = min(1.0, frac)
            temperature = t_start * (ratio**frac)
            thresholds = _thresholds(len(unplaced) > 0)
            if progress is not None and now - last_progress >= 1.0:
                last_progress = now
                progress(
                    {
                        "phase": "search",
                        "frac": round(frac, 3),
                        "iterations": it,
                        "cost": state.cost,
                        "best": snap_cost,
                        "unplaced": len(unplaced),
                    }
                )
        it += 1
        u = rng.random()
        kind = thresholds[-1][1]
        for edge, name in thresholds:
            if u < edge:
                kind = name
                break
        changes = _propose(state, rng, kind, movable, unplaced, value_sets)
        if not changes:
            continue
        delta = state.try_changes(changes)
        if delta <= 0 or (temperature > 0 and rng.random() < math.exp(-delta / temperature)):
            state.commit(delta)
            accepted += 1
            for j, new in changes:
                if new is None:
                    unplaced.add(j)
                else:
                    unplaced.discard(j)
            if state.cost < snap_cost and (it - snap_it >= 400 or snap_cost - state.cost >= 1000):
                snap_cost = state.cost
                snap_vals = list(state.val)
                snap_it = it
                stats["improved"] += 1
        else:
            state.undo()
    if state.cost > snap_cost:
        state.load(snap_vals)
    stats.update({"iterations": it, "accepted": accepted, "elapsed": round(clock() - start, 3)})
    return stats


__all__ = ["MOVE_MIX", "anneal"]
