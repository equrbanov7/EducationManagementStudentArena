"""Baza → mühərrik nümunəsi (``engine.Instance``) + geri xəritə (``Problem``).

Addımlar: dərs saatları (``schedule_grid.lesson_periods``) × tədris günləri
şəbəkəsi → qruplar/ailələr/kohortlar və növbə siyasəti → kurs vahidləri (saat +
müəllim) → mühazirə axınları → hadisələr (həftəlik / iki həftədən bir) →
domenlər (qrup növbəsi ∩ müəllimin «gələ bilir» xanaları ∩ kənar blok) →
kənar məşğulluq (başqa fakültənin dərc olunmuş dərsləri), otaqlar, hint/kilid.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model

from apps.registrar.public import schedule_grid

from ..constants import DEFAULT_WEEKDAYS, KIND_LAB, KIND_LECTURE, KIND_SEMINAR, KINDS, StreamPolicy
from ..engine import (
    WEEK_BOTH,
    WEEK_EVEN,
    WEEK_ODD,
    Building,
    Cohort,
    Event,
    Instance,
    Room,
    Teacher,
    weekly_pattern,
)
from . import context
from .groups import assign_cohorts, load_groups, prune_groups
from .offerings import load_units
from .streams import lecture_streams

_PREFIX = {KIND_LECTURE: "L", KIND_SEMINAR: "S", KIND_LAB: "B"}


@dataclass
class Problem:
    instance: Instance
    periods: list
    weekdays: list
    groups: dict
    cohort_groups: list
    teacher_ids: list
    teacher_names: dict
    events: list
    rooms: list
    units: list
    issues: list = field(default_factory=list)

    def t_to_cell(self, t) -> tuple[int, int]:
        """Şəbəkə indeksi → (ISO həftə günü, dərs saatı nömrəsi 1..)."""
        d, p = divmod(int(t), len(self.periods))
        return self.weekdays[d], p + 1

    def cell_to_t(self, weekday, pair) -> int | None:
        if weekday not in self.weekdays or not 1 <= int(pair) <= len(self.periods):
            return None
        return self.weekdays.index(weekday) * len(self.periods) + int(pair) - 1


def normalize_weekdays(raw) -> list:
    days = []
    for value in raw or []:
        try:
            day = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= day <= 7:
            days.append(day)
    return sorted(set(days)) or list(DEFAULT_WEEKDAYS)


def _allowed(info, periods, weekdays, blocked) -> frozenset:
    bands = set(info.policy.get("bands") or [])
    policy_days = set(info.policy.get("weekdays") or [])
    pairs = len(periods)
    out = set()
    for d, weekday in enumerate(weekdays):
        if policy_days and weekday not in policy_days:
            continue
        for p, row in enumerate(periods):
            if row["shift"] in bands:
                out.add(d * pairs + p)
    return frozenset(out - set(blocked))


def _teacher_names(ids) -> dict:
    names = {}
    for row in get_user_model().objects.filter(pk__in=list(ids)).values("pk", "first_name", "last_name", "username"):
        full = f"{row['first_name'] or ''} {row['last_name'] or ''}".strip()
        names[row["pk"]] = full or row["username"]
    return names


def _events_for_units(units, infos, stream_policy, weeks):
    """(növ, vahidlər, kohortlar, saat) dəsti — hadisələrin xam siyahısı (deterministik)."""
    index = {(unit.group_id, unit.subject_id): unit for unit in units}
    specs = []
    for stream in lecture_streams(units, infos, stream_policy):
        cohorts = []
        for unit in stream:
            cohorts.extend(infos[unit.group_id].cohorts)
        hours = max(unit.hours.get(KIND_LECTURE, 0) for unit in stream)
        specs.append((KIND_LECTURE, stream, tuple(sorted(set(cohorts))), hours))
    for unit in units:
        info = infos[unit.group_id]
        for kind in (KIND_SEMINAR, KIND_LAB):
            hours = unit.hours.get(kind, 0)
            if not hours:
                continue
            covered = set(info.cohorts)
            for child in info.children:
                twin = index.get((child, unit.subject_id))
                if twin is not None and twin.hours.get(kind):
                    covered -= set(infos[child].cohorts)
            if covered:
                specs.append((kind, [unit], tuple(sorted(covered)), hours))
    out = []
    for kind, stream, cohorts, hours in specs:
        weekly, biweekly = weekly_pattern(hours, weeks=weeks)
        root = min(unit.offering_id for unit in stream)
        for n in range(weekly + biweekly):
            out.append(
                {
                    "key": f"{_PREFIX[kind]}:{root}:{n}",
                    "kind": kind,
                    "units": stream,
                    "cohorts": cohorts,
                    "biweekly": n >= weekly,
                    "hours": hours,
                }
            )
    return out


def _family_teachers(units, infos):
    """Alt qrupun müəllimi boşdursa birləşik qrupun eyni fənninin müəllimini götür."""
    index = {(unit.group_id, unit.subject_id): unit for unit in units}
    for unit in units:
        parent = infos[unit.group_id].parent
        twin = index.get((parent, unit.subject_id)) if parent else None
        if twin is None:
            continue
        for kind in KINDS:
            if not unit.teachers.get(kind):
                unit.teachers[kind] = twin.teachers.get(kind)


def build_problem(*, organization, period, groups, params, locked=None, priorities=None) -> Problem:
    """Əhatənin tam mühərrik nümunəsi (bax modul şərhi). Bazaya heç nə yazmır."""
    periods = schedule_grid.lesson_periods(organization)
    weekdays = normalize_weekdays(params.get("weekdays"))
    P = len(periods)
    issues = []
    infos = load_groups(organization, groups)
    Offering = django_apps.get_model("registrar", "CourseOffering")
    with_offerings = {
        str(gid)
        for gid in Offering.objects.filter(
            organization=organization, period=period, group_id__in=list(infos), is_active=True
        ).values_list("group_id", flat=True)
    }
    infos = prune_groups(infos, with_offerings)
    excluded = sorted(info.name for info in infos.values() if info.policy.get("is_excluded"))
    if excluded:
        issues.append({"code": "excluded_groups", "count": len(excluded), "items": excluded[:40]})
    cohort_groups = assign_cohorts(infos)
    active = {gid: info for gid, info in infos.items() if not info.policy.get("is_excluded")}
    units = load_units(organization, period, active)
    _family_teachers(units, active)
    run_offerings = {unit.offering_id for unit in units}
    slots = context.split_slots(
        context.live_slots(organization, period),
        run_offerings,
        set(active),
        periods=periods,
        weekdays=weekdays,
    )
    cohorts = []
    for gid in cohort_groups:
        info = infos[gid]
        cohorts.append(
            Cohort(
                key=gid,
                label=info.name,
                max_per_day=int(info.policy.get("max_pairs_per_day") or 0),
                is_master=info.is_master,
                allowed=_allowed(info, periods, weekdays, slots["group_blocked"].get(gid, ())),
            )
        )
    no_hours = [f"{infos[u.group_id].name} · {u.subject_name}" for u in units if not u.hours]
    if no_hours:
        issues.append({"code": "no_hours", "count": len(no_hours), "items": no_hours[:40]})
    specs = _events_for_units(
        [unit for unit in units if unit.hours],
        active,
        params.get("stream_policy") or StreamPolicy.TASK_ROWS,
        int(params.get("weeks") or 15),
    )
    include_vacant = params.get("include_vacant", True)
    teacher_order = []
    for spec in specs:
        teacher = spec["units"][0].teachers.get(spec["kind"])
        for unit in spec["units"]:
            teacher = teacher or unit.teachers.get(spec["kind"])
        spec["teacher_id"] = teacher
        if teacher and teacher not in teacher_order:
            teacher_order.append(teacher)
    vacant = sorted({s["key"].rsplit(":", 1)[0] for s in specs if not s["teacher_id"]})
    if vacant:
        issues.append({"code": "vacant_teacher", "count": len(vacant)})
    if not include_vacant:
        specs = [spec for spec in specs if spec["teacher_id"]]
    availability = context.load_availability(organization, period, teacher_order)
    overrides = {
        str(k): int(v) for k, v in ((priorities or {}).get("teacher_weights") or {}).items() if str(v).isdigit()
    }
    teachers = []
    for teacher_id in teacher_order:
        row = availability.get(teacher_id)
        priority = overrides.get(str(teacher_id)) or (row.priority if row else 1)
        teachers.append(
            Teacher(
                key=str(teacher_id),
                priority=max(1, min(5, int(priority or 1))),
                max_per_day=int(getattr(row, "max_pairs_per_day", 0) or 0),
                max_days=int(getattr(row, "max_days_per_week", 0) or 0),
                levels=context.levels_string(row, weekdays=weekdays, pairs=P),
            )
        )
    teacher_index = {teacher_id: i for i, teacher_id in enumerate(teacher_order)}
    rooms_raw = context.load_rooms(organization)
    building_names = sorted({room["building"] for room in rooms_raw if room["building"]})
    building_index = {name: i for i, name in enumerate(building_names)}
    buildings = [
        Building(key=name, label=name, capacity=sum(1 for room in rooms_raw if room["building"] == name))
        for name in building_names
    ]
    rooms = [
        Room(
            key=room["id"],
            label=room["label"],
            building=building_index.get(room["building"]),
            capacity=room["capacity"],
        )
        for room in rooms_raw
    ]
    room_lookup = {}
    for k, room in enumerate(rooms_raw):
        for key in room["keys"]:
            room_lookup.setdefault(key, k)
    room_busy, building_busy = [], Counter()
    for key, wk, t in slots["room_busy"]:
        k = room_lookup.get(key)
        if k is None:
            continue
        room_busy.append((k, wk, t))
        if rooms[k].building is not None:
            building_busy[(rooms[k].building, wk, t)] += 1
    subjects = sorted({unit.subject_id for unit in units})
    course_index = {subject: i for i, subject in enumerate(subjects)}
    cohort_students = [infos[gid].students for gid in cohort_groups]
    locked = locked or {}
    events, metas = [], []
    for spec in specs:
        unit0 = spec["units"][0]
        teacher_id = spec["teacher_id"]
        t_idx = teacher_index.get(teacher_id)
        allowed = None
        for c in spec["cohorts"]:
            allowed = set(cohorts[c].allowed) if allowed is None else allowed & cohorts[c].allowed
        allowed = allowed or set()
        reason = ""
        if not allowed:
            reason = "no_common_band" if len(spec["cohorts"]) > 1 else "group_no_slots"
        levels = teachers[t_idx].levels if t_idx is not None else ""
        domain = sorted(t for t in allowed if not levels or levels[t] != "u")
        if allowed and not domain:
            reason = "teacher_unavailable"
        row = availability.get(teacher_id)
        subject_prio = int(((row.subject_priorities or {}) if row else {}).get(unit0.subject_id) or 0)
        building_votes = Counter(active[u.group_id].building for u in spec["units"] if active[u.group_id].building)
        building = building_index.get(building_votes.most_common(1)[0][0]) if building_votes else None
        fixed = locked.get(spec["key"])
        if fixed is not None:
            fixed = (int(fixed[0]), int(fixed[1]))
            if fixed[0] not in domain:
                domain = sorted(set(domain) | {fixed[0]})
                issues.append({"code": "locked_outside_domain", "count": 1, "items": [spec["key"]]})
        events.append(
            Event(
                key=spec["key"],
                kind=spec["kind"],
                teacher=t_idx,
                cohorts=spec["cohorts"],
                course=course_index[unit0.subject_id],
                biweekly=spec["biweekly"],
                domain=tuple(domain),
                priority=max(teachers[t_idx].priority if t_idx is not None else 1, subject_prio, 1),
                fixed=fixed,
                building=building,
                size=sum(cohort_students[c] for c in spec["cohorts"]),
                domain_reason=reason,
            )
        )
        metas.append(
            {
                "key": spec["key"],
                "kind": spec["kind"],
                "offerings": [u.offering_id for u in spec["units"]],
                "groups": [u.group_id for u in spec["units"]],
                "subject": unit0.subject_name,
                "subject_code": unit0.subject_code,
                "teacher_id": teacher_id,
                "hours": spec["hours"],
                "stream": len(spec["units"]) > 1,
            }
        )
    if params.get("keep_published"):
        _apply_hints(events, metas, slots["hints"])
    teacher_busy = [
        (teacher_index[tid], wk, t)
        for tid, cells in slots["teacher_busy"].items()
        if tid in teacher_index
        for wk, t in cells
    ]
    instance = Instance(
        days=len(weekdays),
        pairs=P,
        teachers=teachers,
        cohorts=cohorts,
        events=events,
        buildings=buildings,
        rooms=rooms,
        teacher_busy=sorted(teacher_busy),
        building_busy=sorted((b, wk, t, n) for (b, wk, t), n in building_busy.items()),
        room_busy=sorted(room_busy),
        late_after=max(1, sum(1 for row in periods if row["shift"] != "evening") - 1),
    )
    streams = sum(1 for meta in metas if meta["stream"])
    if streams:
        issues.append({"code": "streams", "count": streams})
    return Problem(
        instance=instance,
        periods=periods,
        weekdays=weekdays,
        groups=infos,
        cohort_groups=cohort_groups,
        teacher_ids=teacher_order,
        teacher_names=_teacher_names(teacher_order),
        events=metas,
        rooms=rooms_raw,
        units=units,
        issues=issues,
    )


def _apply_hints(events, metas, hints) -> None:
    """Dərc olunmuş slotları eyni açılış + növün hadisələrinə sıra ilə hint kimi bağla."""
    pools: dict = {}
    for offering, rows in hints.items():
        for kind, t, week in rows:
            pools.setdefault((offering, kind), []).append((t, week))
    for event, meta in zip(events, metas):
        pool = pools.get((meta["offerings"][0], meta["kind"])) or []
        for k, (t, week) in enumerate(pool):
            if (week == WEEK_BOTH) != (not event.biweekly) or t not in event.domain:
                continue
            if event.biweekly and week not in (WEEK_ODD, WEEK_EVEN):
                continue
            event.hint = (t, week)
            pool.pop(k)
            break


__all__ = ["Problem", "build_problem", "normalize_weekdays"]
