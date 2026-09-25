"""Cədvəl vəziyyəti + DELTA-qiymətləndirmə (lokal axtarışın ürəyi).

Hər resurs (müəllim / kohort) üçün ``2 * days * pairs`` ölçülü məşğulluq sayğacı
saxlanılır. Bir hərəkət (move/swap/eject) yalnız TOXUNDUĞU «gün sətirlərinin»
(resurs × həftə × gün) xərcini əvvəl və sonra hesablayır — tam yenidən hesablama
yoxdur. Bu, ``uctp_bench.py``-dakı yanaşmanın istehsal versiyasıdır.

Xərc komponentləri (``Weights``):

* gün sətri, KOHORT: toqquşma + BOŞLUQ (sərt), gündəlik limit aşımı, tək cütlük
  gün, yük balansı (``n²``);
* gün sətri, MÜƏLLİM: toqquşma (sərt), boş «pəncərə» cütləri (ən güclü yumşaq),
  iş günü, gündəlik limit aşımı;
* həftə, MÜƏLLİM: həftəlik iş günü limiti aşımı;
* korpus xanası: eyni anda dərs sayı > otaq sayı (sərt);
* fənn-gün: eyni fənn eyni gün (qrup üzrə) — mühazirə+məşğələ yüngül, eyni NÖV
  (iki məşğələ) güclü cərimə;
* hadisənin öz xərci: müəllimin xana səviyyəsi, bakalavr üçün gec saat,
  dərc olunmuş cədvəldən fərq (sabitlik), yerləşdirilməmə cəriməsi.
"""

from __future__ import annotations

from .types import (
    LEVEL_DISCOURAGED,
    LEVEL_NEUTRAL,
    LEVEL_UNAVAILABLE,
    WEEKS_OF,
    priority_factor,
)


def event_pref_costs(instance, event, weights) -> dict:
    """Hadisənin hər icazəli xanası üçün öz (lokal) xərci — yoxlayıcı ilə ortaq."""
    teacher = instance.teachers[event.teacher] if event.teacher is not None else None
    factor = priority_factor(teacher.priority) if teacher is not None else 1.0
    levels = teacher.levels if teacher is not None else ""
    is_master = any(instance.cohorts[c].is_master for c in event.cohorts)
    pairs = instance.pairs
    out = {}
    for t in event.domain:
        cost = int(event.pref.get(t, 0))
        level = levels[t] if t < len(levels) else LEVEL_NEUTRAL
        if level == LEVEL_DISCOURAGED:
            cost += int(round(weights.discouraged * factor))
        elif level == LEVEL_NEUTRAL:
            cost += weights.neutral
        pair_no = t % pairs + 1
        if not is_master and pair_no > instance.late_after:
            cost += weights.late_pair * (pair_no - instance.late_after)
        if cost:
            out[t] = cost
    return out


def unplaced_cost(event, weights) -> int:
    """Yerləşdirilməmə cəriməsi: prioritet və axın (bir neçə qrup) ilə artır, ``hard``-dan kiçik qalır."""
    prio = max(1, min(5, int(event.priority or 1)))
    streams = max(1, min(3, len(event.cohorts)))
    return int(weights.unplaced * (1 + 0.25 * (prio - 1)) * (1 + 0.5 * (streams - 1)))


class State:
    """Cari yerləşdirmə + inkremental xərc."""

    def __init__(self, instance, weights):
        self.inst = instance
        self.w = weights
        self.D, self.P = instance.days, instance.pairs
        self.S = self.D * self.P
        teachers, cohorts = instance.teachers, instance.cohorts
        self.T, self.C = len(teachers), len(cohorts)
        resources = self.T + self.C
        size = 2 * self.S
        self.occ = [[0] * size for _ in range(resources)]
        self.H = weights.hard
        self.max_day = [t.max_per_day for t in teachers] + [c.max_per_day for c in cohorts]
        self.max_days = [t.max_days for t in teachers] + [0] * self.C
        factors = [priority_factor(t.priority) for t in teachers]
        self.idle_w = [int(round(weights.teacher_idle * f)) for f in factors] + [0] * self.C
        self.tload_w = [int(round(weights.teacher_overload * f)) for f in factors] + [0] * self.C
        self.tdays_w = [int(round(weights.teacher_days_over * f)) for f in factors] + [0] * self.C
        self.bcap = [b.capacity for b in instance.buildings]
        self.bocc = [[0] * size for _ in instance.buildings]
        self._init_events(instance, weights)
        self._init_background(instance)
        self.cost = self.total_cost()
        self._undo = []

    # ── Qurulma ──────────────────────────────────────────────────────────────
    def _init_events(self, instance, weights):
        events = instance.events
        n = len(events)
        self.N = n
        self.sd_index: dict = {}
        self.sd: list = []
        self.sd_weight: list = []
        self.ev_res, self.ev_sd, self.ev_b = [], [], []
        self.ev_pref, self.ev_unplaced, self.ev_hint = [], [], []
        self.values, self.fixed = [], []
        self.res_events = [[] for _ in range(self.T + self.C)]
        for index, event in enumerate(events):
            res = []
            if event.teacher is not None:
                res.append(event.teacher)
            res.extend(self.T + c for c in event.cohorts)
            res = tuple(dict.fromkeys(res))
            self.ev_res.append(res)
            for r in res:
                self.res_events[r].append(index)
            sds = []
            for c in event.cohorts:
                for key, weight in (
                    ((c, event.course, ""), weights.same_subject_day),
                    ((c, event.course, event.kind), weights.same_kind_day),
                ):
                    if key not in self.sd_index:
                        self.sd_index[key] = len(self.sd)
                        self.sd.append([0] * (2 * self.D))
                        self.sd_weight.append(weight)
                    sds.append(self.sd_index[key])
            self.ev_sd.append(tuple(dict.fromkeys(sds)))
            self.ev_b.append(event.building if event.building is not None else -1)
            self.ev_pref.append(event_pref_costs(instance, event, weights))
            self.ev_unplaced.append(unplaced_cost(event, weights))
            self.ev_hint.append(tuple(event.hint) if event.hint else None)
            if event.fixed:
                self.values.append([tuple(event.fixed)])
                self.fixed.append(True)
            else:
                self.values.append(event.values())
                self.fixed.append(False)
        self.val = [None] * n

    def _init_background(self, instance):
        S = self.S
        for teacher, week, t in instance.teacher_busy:
            if 0 <= teacher < self.T and 0 <= t < S and week in (0, 1):
                self.occ[teacher][week * S + t] = max(1, self.occ[teacher][week * S + t])
        for building, week, t, count in instance.building_busy:
            if 0 <= building < len(self.bcap) and 0 <= t < S and week in (0, 1):
                cap = self.bcap[building]
                idx = week * S + t
                self.bocc[building][idx] = min(cap, self.bocc[building][idx] + int(count)) if cap else 0

    # ── Xərc funksiyaları ────────────────────────────────────────────────────
    def row_cost(self, r, wk, d):
        occ = self.occ[r]
        base = wk * self.S + d * self.P
        first = -1
        last = 0
        n = 0
        clash = 0
        for i in range(base, base + self.P):
            x = occ[i]
            if x:
                if x > 1:
                    clash += x - 1
                if first < 0:
                    first = i
                last = i
                n += 1
        if not n:
            return 0
        gaps = last - first + 1 - n
        w = self.w
        limit = self.max_day[r]
        if r >= self.T:
            cost = self.H * (clash + gaps) + w.group_balance * n * n
            if limit and n > limit:
                cost += w.group_overload * (n - limit)
            if n == 1:
                cost += w.group_single_day
            return cost
        cost = self.H * clash + self.idle_w[r] * gaps + w.teacher_day
        if limit and n > limit:
            cost += self.tload_w[r] * (n - limit)
        return cost

    def week_cost(self, r, wk):
        limit = self.max_days[r]
        if not limit:
            return 0
        occ = self.occ[r]
        used = 0
        base = wk * self.S
        for d in range(self.D):
            start = base + d * self.P
            for i in range(start, start + self.P):
                if occ[i]:
                    used += 1
                    break
        return self.tdays_w[r] * (used - limit) if used > limit else 0

    def event_cost(self, i, v):
        if v is None:
            return self.ev_unplaced[i]
        cost = self.ev_pref[i].get(v[0], 0)
        hint = self.ev_hint[i]
        if hint is not None and hint != v:
            cost += self.w.move
        return cost

    def _collect(self, i, v, rows, weeks, cells, sds):
        t, week = v
        d = t // self.P
        wks = WEEKS_OF[week]
        for r in self.ev_res[i]:
            for wk in wks:
                rows.add((r, wk, d))
                if self.max_days[r]:
                    weeks.add((r, wk))
        b = self.ev_b[i]
        if b >= 0:
            for wk in wks:
                cells.add((b, wk * self.S + t))
        for k in self.ev_sd[i]:
            for wk in wks:
                sds.add((k, wk * self.D + d))

    def _local(self, rows, weeks, cells, sds):
        cost = 0
        for r, wk, d in rows:
            cost += self.row_cost(r, wk, d)
        for r, wk in weeks:
            cost += self.week_cost(r, wk)
        for b, idx in cells:
            over = self.bocc[b][idx] - self.bcap[b]
            if over > 0 and self.bcap[b]:
                cost += self.H * over
        for k, idx in sds:
            x = self.sd[k][idx]
            if x > 1:
                cost += self.sd_weight[k] * (x - 1)
        return cost

    def _apply(self, i, v, sign):
        t, week = v
        d = t // self.P
        b = self.ev_b[i]
        for wk in WEEKS_OF[week]:
            idx = wk * self.S + t
            for r in self.ev_res[i]:
                self.occ[r][idx] += sign
            if b >= 0:
                self.bocc[b][idx] += sign
            day_idx = wk * self.D + d
            for k in self.ev_sd[i]:
                self.sd[k][day_idx] += sign

    # ── Hərəkət API-si ───────────────────────────────────────────────────────
    def try_changes(self, changes):
        """``[(event, yeni_dəyər)]`` tətbiq edir və xərc fərqini qaytarır.

        Çağıran ``commit(delta)`` və ya ``undo()`` etməlidir."""
        rows, weeks, cells, sds = set(), set(), set(), set()
        olds = []
        for i, new in changes:
            old = self.val[i]
            olds.append(old)
            if old is not None:
                self._collect(i, old, rows, weeks, cells, sds)
            if new is not None:
                self._collect(i, new, rows, weeks, cells, sds)
        before = self._local(rows, weeks, cells, sds)
        for (i, new), old in zip(changes, olds):
            before += self.event_cost(i, old)
            if old is not None:
                self._apply(i, old, -1)
            if new is not None:
                self._apply(i, new, +1)
            self.val[i] = new
        after = self._local(rows, weeks, cells, sds)
        for i, new in changes:
            after += self.event_cost(i, new)
        self._undo = list(zip([i for i, _new in changes], olds))
        return after - before

    def undo(self):
        for i, old in reversed(self._undo):
            new = self.val[i]
            if new is not None:
                self._apply(i, new, -1)
            if old is not None:
                self._apply(i, old, +1)
            self.val[i] = old
        self._undo = []

    def commit(self, delta):
        self.cost += delta
        self._undo = []

    def set_value(self, i, v):
        delta = self.try_changes([(i, v)])
        self.commit(delta)
        return delta

    def load(self, vals):
        """Vəziyyəti verilmiş dəyər siyahısına gətir (ən yaxşı həllin bərpası)."""
        for i in range(self.N):
            if self.val[i] is not None:
                self._apply(i, self.val[i], -1)
                self.val[i] = None
        for i, v in enumerate(vals):
            if v is not None:
                self._apply(i, v, +1)
                self.val[i] = v
        self.cost = self.total_cost()
        self._undo = []

    def total_cost(self):
        cost = 0
        for r in range(self.T + self.C):
            for wk in (0, 1):
                for d in range(self.D):
                    cost += self.row_cost(r, wk, d)
                cost += self.week_cost(r, wk)
        for b, cap in enumerate(self.bcap):
            if not cap:
                continue
            for x in self.bocc[b]:
                if x > cap:
                    cost += self.H * (x - cap)
        for k, counts in enumerate(self.sd):
            weight = self.sd_weight[k]
            for x in counts:
                if x > 1:
                    cost += weight * (x - 1)
        for i in range(self.N):
            cost += self.event_cost(i, self.val[i])
        return cost

    # ── Köməkçilər ───────────────────────────────────────────────────────────
    def occupants(self, r, wk, t):
        """``r`` resursunun ``(wk, t)`` xanasını tutan hadisələr."""
        out = []
        for j in self.res_events[r]:
            v = self.val[j]
            if v is not None and v[0] == t and wk in WEEKS_OF[v[1]]:
                out.append(j)
        return out

    def conflicting(self, i, v):
        """``i``-ni ``v``-yə qoysaq resurs üzrə toqquşan hadisələr (sabit sıra)."""
        t, week = v
        wks = WEEKS_OF[week]
        found = []
        seen = {i}
        for r in self.ev_res[i]:
            for j in self.res_events[r]:
                if j in seen:
                    continue
                other = self.val[j]
                if other is None or other[0] != t:
                    continue
                if any(wk in wks for wk in WEEKS_OF[other[1]]):
                    seen.add(j)
                    found.append(j)
        return found

    def level_at(self, i, t):
        event = self.inst.events[i]
        if event.teacher is None:
            return LEVEL_NEUTRAL
        levels = self.inst.teachers[event.teacher].levels
        return levels[t] if t < len(levels) else LEVEL_NEUTRAL

    def is_unavailable(self, i, t):
        return self.level_at(i, t) == LEVEL_UNAVAILABLE


__all__ = ["State", "event_pref_costs", "unplaced_cost"]
