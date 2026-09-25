"""MÜSTƏQİL yoxlayıcı + KPI-lar — axtarışın inkremental vəziyyətinə ETİBAR ETMİR.

Yekun dəyərlərdən məşğulluğu SIFIRDAN qurur və hər qaydanı ayrıca sayır. Testlər
və ``solver`` sərt pozuntuların sıfır olduğunu MƏHZ buradan təsdiqləyir (delta
qiymətləndirmədəki səhv bu yolla görünür).
"""

from __future__ import annotations

from .types import LEVEL_DISCOURAGED, LEVEL_PREFERRED, LEVEL_UNAVAILABLE, WEEK_BOTH, WEEKS_OF


def _grid(size):
    return [0] * size


def _gaps(row):
    occupied = [p for p, x in enumerate(row) if x]
    if not occupied:
        return 0, 0
    return occupied[-1] - occupied[0] + 1 - len(occupied), len(occupied)


def check(instance, values, rooms=None) -> dict:
    """Sərt/yumşaq göstəricilər (bax modul şərhi)."""
    S, P, D = instance.slots, instance.pairs, instance.days
    events = instance.events
    T, C = len(instance.teachers), len(instance.cohorts)
    t_occ = [_grid(2 * S) for _ in range(T)]
    t_ours = [_grid(2 * S) for _ in range(T)]
    c_occ = [_grid(2 * S) for _ in range(C)]
    b_occ = [_grid(2 * S) for _ in instance.buildings]
    b_ours = [_grid(2 * S) for _ in instance.buildings]
    subject_day: dict = {}
    kind_day: dict = {}
    hard = dict.fromkeys(
        (
            "teacher_clash",
            "cohort_clash",
            "cohort_gap",
            "building_over",
            "outside_domain",
            "band_violation",
            "unavailable_used",
            "fixed_moved",
            "room_clash",
        ),
        0,
    )
    soft = dict.fromkeys(("discouraged_used", "preferred_used", "late_pairs", "moved_vs_published"), 0)
    for teacher, week, t in instance.teacher_busy:
        if 0 <= teacher < T and 0 <= t < S:
            t_occ[teacher][week * S + t] = max(1, t_occ[teacher][week * S + t])
    for building, week, t, count in instance.building_busy:
        if 0 <= building < len(b_occ) and 0 <= t < S:
            b_occ[building][week * S + t] += int(count)
    placed = 0
    weekly_units = 0.0
    for event, v in zip(events, values):
        if v is None:
            continue
        placed += 1
        t, week = v
        weekly_units += 1.0 if week == WEEK_BOTH else 0.5
        if t not in event.domain or (week == WEEK_BOTH) == bool(event.biweekly):
            hard["outside_domain"] += 1
        if event.fixed and tuple(event.fixed) != tuple(v):
            hard["fixed_moved"] += 1
        if event.hint and tuple(event.hint) != tuple(v):
            soft["moved_vs_published"] += 1
        for c in event.cohorts:
            allowed = instance.cohorts[c].allowed
            if allowed and t not in allowed:
                hard["band_violation"] += 1
        if event.teacher is not None:
            levels = instance.teachers[event.teacher].levels
            level = levels[t] if t < len(levels) else "n"
            if level == LEVEL_UNAVAILABLE:
                hard["unavailable_used"] += 1
            elif level == LEVEL_DISCOURAGED:
                soft["discouraged_used"] += 1
            elif level == LEVEL_PREFERRED:
                soft["preferred_used"] += 1
        if not any(instance.cohorts[c].is_master for c in event.cohorts) and t % P + 1 > instance.late_after:
            soft["late_pairs"] += 1
        d = t // P
        for wk in WEEKS_OF[week]:
            idx = wk * S + t
            if event.teacher is not None:
                t_occ[event.teacher][idx] += 1
                t_ours[event.teacher][idx] += 1
            for c in event.cohorts:
                c_occ[c][idx] += 1
                key = (c, event.course, wk, d)
                subject_day[key] = subject_day.get(key, 0) + 1
                kind_key = (c, event.course, event.kind, wk, d)
                kind_day[kind_key] = kind_day.get(kind_key, 0) + 1
            if event.building is not None and event.building < len(b_occ):
                b_occ[event.building][idx] += 1
                b_ours[event.building][idx] += 1
    for r in range(T):
        for idx in range(2 * S):
            if t_ours[r][idx] and t_occ[r][idx] > 1:
                hard["teacher_clash"] += t_occ[r][idx] - 1
    for c in range(C):
        for x in c_occ[c]:
            if x > 1:
                hard["cohort_clash"] += x - 1
    for b, building in enumerate(instance.buildings):
        if not building.capacity:
            continue
        for idx in range(2 * S):
            if b_ours[b][idx] and b_occ[b][idx] > building.capacity:
                hard["building_over"] += b_occ[b][idx] - building.capacity

    idle = teachers_with_idle = teacher_overload = teacher_days_over = 0
    for r, teacher in enumerate(instance.teachers):
        mine = 0
        for wk in (0, 1):
            used_days = 0
            for d in range(D):
                base = wk * S + d * P
                if not any(t_ours[r][base : base + P]):
                    if any(t_occ[r][base : base + P]):
                        used_days += 1
                    continue
                gaps, n = _gaps(t_occ[r][base : base + P])
                mine += gaps
                used_days += 1
                if teacher.max_per_day and n > teacher.max_per_day:
                    teacher_overload += n - teacher.max_per_day
            if teacher.max_days and used_days > teacher.max_days:
                teacher_days_over += used_days - teacher.max_days
        idle += mine
        teachers_with_idle += 1 if mine else 0

    gaps_total = single = overload = max_load = 0
    loads = []
    for c, cohort in enumerate(instance.cohorts):
        for wk in (0, 1):
            for d in range(D):
                base = wk * S + d * P
                gaps, n = _gaps(c_occ[c][base : base + P])
                if not n:
                    continue
                gaps_total += gaps
                loads.append(n)
                max_load = max(max_load, n)
                single += 1 if n == 1 else 0
                if cohort.max_per_day and n > cohort.max_per_day:
                    overload += n - cohort.max_per_day
    hard["cohort_gap"] = gaps_total

    if rooms is not None:
        seen = {(room, week, t) for room, week, t in instance.room_busy}
        for v, room in zip(values, rooms):
            if v is None or room is None:
                continue
            for wk in WEEKS_OF[v[1]]:
                key = (room, wk, v[0])
                if key in seen:
                    hard["room_clash"] += 1
                seen.add(key)

    soft.update(
        {
            "teacher_idle_pairs": idle,
            "teacher_idle_per_week": round(idle / 2, 1),
            "teachers_with_idle": teachers_with_idle,
            "teacher_overload": teacher_overload,
            "teacher_days_over": teacher_days_over,
            "group_overload": overload,
            "single_pair_days": single,
            "same_subject_same_day": sum(x - 1 for x in subject_day.values() if x > 1),
            "same_kind_same_day": sum(x - 1 for x in kind_day.values() if x > 1),
            "max_group_day_load": max_load,
            "avg_group_day_load": round(sum(loads) / len(loads), 2) if loads else 0,
        }
    )
    return {
        "events": len(events),
        "placed": placed,
        "unplaced": len(events) - placed,
        "weekly_pair_units": weekly_units,
        "hard": hard,
        "hard_total": sum(hard.values()),
        "soft": soft,
    }


__all__ = ["check"]
