"""Mühərrik vahid testləri — kiçik sintetik nümunələr (baza YOXDUR, Django lazım deyil).

Qorunan müqavilə (sahibin sərt qaydaları):
* yerləşdirilmiş heç bir dərs üçün müəllim/qrup toqquşması yoxdur;
* qrupun günündə HEÇ VAXT boşluq (1-ci və 3-cü var, 2-ci boş) olmur;
* magistr qrupu səhər (və günorta) saatına düşmür — yalnız axşam;
* müəllimin «gələ bilmədiyi» xana heç vaxt istifadə olunmur;
* üst/alt həftə pariteti düzgündür (iki həftədən bir dərslər eyni xananı bölüşə bilir);
* eyni seed + iterasiya büdcəsi → eyni nəticə (determinizm);
* yerləşməyən dərs üçün SƏBƏB qaytarılır.
"""

from __future__ import annotations

import random

from apps.timetable.engine import (
    WEEK_BOTH,
    WEEK_EVEN,
    WEEK_ODD,
    Building,
    Cohort,
    Event,
    Instance,
    Params,
    Room,
    Teacher,
    check,
    solve,
    weekly_pattern,
)
from apps.timetable.engine.state import State
from apps.timetable.tests.synthetic import EVENING, make_instance

P = 8
DAYS = 6


def _params(seed=7, iterations=15000):
    return Params(seed=seed, time_limit=60, max_iterations=iterations)


def _cohort(key, pairs=(0, 1, 2, 3, 4, 5), *, master=False, days=DAYS):
    allowed = frozenset(d * P + p for d in range(days) for p in pairs)
    return Cohort(key=key, label=key, is_master=master, allowed=allowed)


def _event(key, teacher, cohorts, course, domain, *, biweekly=False, **extra):
    return Event(
        key=key,
        kind=extra.pop("kind", "seminar"),
        teacher=teacher,
        cohorts=tuple(cohorts),
        course=course,
        biweekly=biweekly,
        domain=tuple(sorted(domain)),
        **extra,
    )


# ── Saat → həftəlik nümunə ────────────────────────────────────────────────


def test_weekly_pattern_follows_two_hour_pairs():
    assert weekly_pattern(0) == (0, 0)
    assert weekly_pattern(15) == (0, 1)  # iki həftədən bir
    assert weekly_pattern(30) == (1, 0)  # hər həftə
    assert weekly_pattern(45) == (1, 1)
    assert weekly_pattern(60) == (2, 0)
    assert weekly_pattern(10) == (0, 1)  # qiyabi — minimum bir yarım-cüt
    assert weekly_pattern(30, weeks=30) == (0, 1)
    assert weekly_pattern("xyz") == (0, 0)


# ── Sərt qaydalar (sintetik orta nümunə) ─────────────────────────────────


def _assert_hard_clean(instance, result):
    kpis = check(instance, result.values, result.rooms)
    assert kpis["hard_total"] == 0, kpis["hard"]
    return kpis


def test_synthetic_instance_places_everything_without_hard_violations():
    instance = make_instance(seed=3, teachers=24, families=8, masters=3, subjects=5)
    result = solve(instance, _params(seed=3, iterations=40000))
    kpis = _assert_hard_clean(instance, result)
    assert kpis["placed"] == kpis["events"]
    assert result.kpis["hard_total"] == 0


def test_group_day_never_has_a_gap_even_when_something_must_stay_unplaced():
    # Bir qrup, üç dərs; B-nin müəllimi yalnız 1-ci və 3-cü cütdə gələ bilir,
    # A və C isə istənilən saatda. Boşluqsuz yeganə düzülüş: B kənarda.
    days = 1
    teachers = [Teacher("ta"), Teacher("tb", levels="nun" + "u" * 5), Teacher("tc")]
    cohort = _cohort("G", pairs=(0, 1, 2), days=days)
    events = [
        _event("A", 0, [0], 1, {0, 1, 2}),
        _event("B", 1, [0], 2, {0, 2}),
        _event("C", 2, [0], 3, {0, 1, 2}),
    ]
    instance = Instance(days=days, pairs=P, teachers=teachers, cohorts=[cohort], events=events)
    result = solve(instance, _params())
    kpis = _assert_hard_clean(instance, result)
    assert kpis["placed"] == 3
    b_pair = result.values[1][0] % P
    assert b_pair in (0, 2)


def test_gap_rule_leaves_event_unplaced_instead_of_breaking_the_group_day():
    # Qrupun yalnız bir günü var; A 1-ci cütdə KİLİDLİDİR, B yalnız 3-cü cütdə ola
    # bilər → B qoyulsa 2-ci cüt boş qalardı. Nəticə: B yerləşmir, səbəb «group_gap».
    days = 1
    cohort = _cohort("G", pairs=(0, 1, 2), days=days)
    events = [
        _event("A", 0, [0], 1, {0}, fixed=(0, WEEK_BOTH)),
        _event("B", 1, [0], 2, {2}),
    ]
    instance = Instance(days=days, pairs=P, teachers=[Teacher("a"), Teacher("b")], cohorts=[cohort], events=events)
    result = solve(instance, _params())
    _assert_hard_clean(instance, result)
    assert result.values[0] == (0, WEEK_BOTH)
    assert result.values[1] is None
    assert result.unplaced == [{"event": 1, "code": "group_gap", "counts": {"group_gap": 1}, "options": 1}]


def test_master_groups_are_scheduled_in_the_evening_only():
    instance = make_instance(seed=5, teachers=16, families=4, masters=4, subjects=4)
    result = solve(instance, _params(seed=5, iterations=30000))
    _assert_hard_clean(instance, result)
    master_cohorts = {i for i, c in enumerate(instance.cohorts) if c.is_master}
    assert master_cohorts
    checked = 0
    for event, value in zip(instance.events, result.values):
        if value is None or not set(event.cohorts) & master_cohorts:
            continue
        assert value[0] % P in EVENING
        checked += 1
    assert checked > 0


def test_unavailable_slots_are_never_used():
    instance = make_instance(seed=11, teachers=20, families=6, masters=2, subjects=5, p_off=0.9, days_off=2)
    result = solve(instance, _params(seed=11, iterations=30000))
    kpis = _assert_hard_clean(instance, result)
    assert kpis["hard"]["unavailable_used"] == 0
    for event, value in zip(instance.events, result.values):
        if value is not None and event.teacher is not None:
            assert instance.teachers[event.teacher].levels[value[0]] != "u"


def test_biweekly_events_share_a_cell_in_opposite_weeks():
    # Tək xana, iki «iki həftədən bir» dərs → üst + alt eyni xanada; üçüncü sığmır.
    cohort = _cohort("G", pairs=(0,), days=1)
    events = [_event(f"L{k}", k, [0], k, {0}, biweekly=True, kind="lab") for k in range(3)]
    teachers = [Teacher(f"t{k}") for k in range(3)]
    instance = Instance(days=1, pairs=P, teachers=teachers, cohorts=[cohort], events=events)
    result = solve(instance, _params())
    _assert_hard_clean(instance, result)
    weeks = sorted(v[1] for v in result.values if v is not None)
    assert weeks == [WEEK_ODD, WEEK_EVEN]
    assert sum(1 for v in result.values if v is None) == 1


def test_weekly_event_blocks_both_weeks():
    cohort = _cohort("G", pairs=(0,), days=1)
    events = [
        _event("W", 0, [0], 1, {0}),
        _event("B", 1, [0], 2, {0}, biweekly=True),
    ]
    instance = Instance(days=1, pairs=P, teachers=[Teacher("a"), Teacher("b")], cohorts=[cohort], events=events)
    result = solve(instance, _params())
    _assert_hard_clean(instance, result)
    assert sum(1 for v in result.values if v is not None) == 1


def test_stream_lecture_occupies_every_member_group():
    # Axın mühazirəsi A+B qruplarını birlikdə tutur; A-nın məşğələsi eyni xanaya düşə bilməz.
    cohorts = [_cohort("A", pairs=(0,), days=1), _cohort("B", pairs=(0,), days=1)]
    events = [
        _event("LEC", 0, [0, 1], 1, {0}, kind="lecture"),
        _event("SEM", 1, [0], 2, {0}),
    ]
    instance = Instance(days=1, pairs=P, teachers=[Teacher("a"), Teacher("b")], cohorts=cohorts, events=events)
    result = solve(instance, _params())
    _assert_hard_clean(instance, result)
    assert result.values[0] is not None  # axın (2 qrup) daha yüksək cərimədir → o qalır
    assert result.values[1] is None


def test_same_seed_and_iteration_budget_is_deterministic():
    instance = make_instance(seed=9, teachers=18, families=6, masters=2, subjects=5)
    first = solve(instance, _params(seed=42, iterations=12000))
    second = solve(instance, _params(seed=42, iterations=12000))
    assert first.values == second.values
    assert first.rooms == second.rooms
    assert first.kpis["soft"] == second.kpis["soft"]


def test_unplaced_reason_for_empty_domain_and_external_teacher_lesson():
    cohort = _cohort("G", pairs=(0, 1), days=1)
    events = [
        _event("NODOMAIN", 0, [0], 1, set(), domain_reason="teacher_unavailable"),
        _event("EXT", 1, [0], 2, {0}),
    ]
    instance = Instance(
        days=1,
        pairs=P,
        teachers=[Teacher("a"), Teacher("b")],
        cohorts=[cohort],
        events=events,
        teacher_busy=[(1, 0, 0), (1, 1, 0)],
    )
    result = solve(instance, _params())
    _assert_hard_clean(instance, result)
    codes = {instance.events[item["event"]].key: item["code"] for item in result.unplaced}
    assert codes == {"NODOMAIN": "teacher_unavailable", "EXT": "teacher_external"}


def test_locked_event_keeps_its_place():
    cohort = _cohort("G", days=2)
    events = [
        _event("LOCK", 0, [0], 1, set(cohort.allowed), fixed=(P + 3, WEEK_BOTH)),
        _event("FREE", 1, [0], 2, set(cohort.allowed)),
    ]
    instance = Instance(days=2, pairs=P, teachers=[Teacher("a"), Teacher("b")], cohorts=[cohort], events=events)
    result = solve(instance, _params())
    _assert_hard_clean(instance, result)
    assert result.values[0] == (P + 3, WEEK_BOTH)
    assert result.values[1] is not None


def test_published_hint_is_kept_when_feasible():
    instance = make_instance(seed=13, teachers=16, families=4, masters=1, subjects=4)
    baseline = solve(instance, _params(seed=13, iterations=20000))
    for event, value in zip(instance.events, baseline.values):
        event.hint = value
    again = solve(instance, _params(seed=99, iterations=20000))
    kpis = _assert_hard_clean(instance, again)
    # Sabitlik YUMŞAQDIR: yalnız başqa cərimələri azaldan az sayda köçürmə olur…
    assert kpis["soft"]["moved_vs_published"] <= max(3, len(instance.events) // 10)
    # …çəki böyüdüləndə isə dərc olunmuş cədvəl tam saxlanılır (minimal dəyişiklik).
    from apps.timetable.engine import Weights

    strict = Params(seed=99, time_limit=60, max_iterations=20000, weights=Weights(move=5000))
    kept = solve(instance, strict)
    assert _assert_hard_clean(instance, kept)["soft"]["moved_vs_published"] == 0


def test_incremental_cost_matches_full_recomputation():
    instance = make_instance(seed=17, teachers=12, families=4, masters=2, subjects=4, building_capacity=3)
    from apps.timetable.engine import Weights

    state = State(instance, Weights())
    rng = random.Random(1)
    for _ in range(3000):
        i = rng.randrange(state.N)
        values = state.values[i]
        new = None if (not values or rng.random() < 0.2) else values[rng.randrange(len(values))]
        delta = state.try_changes([(i, new)])
        if rng.random() < 0.6:
            state.commit(delta)
        else:
            state.undo()
    assert state.cost == state.total_cost()


def test_building_capacity_limits_parallel_lessons_and_rooms_are_clash_free():
    cohorts = [_cohort(f"G{k}", pairs=(0, 1), days=1) for k in range(3)]
    events = [_event(f"E{k}", k, [k], k, {0, 1}, building=0, size=20) for k in range(3)]
    rooms = [Room("r1", "101", building=0, capacity=30), Room("r2", "102", building=0, capacity=30)]
    instance = Instance(
        days=1,
        pairs=P,
        teachers=[Teacher(f"t{k}") for k in range(3)],
        cohorts=cohorts,
        events=events,
        buildings=[Building("A", capacity=2)],
        rooms=rooms,
    )
    result = solve(instance, _params())
    kpis = _assert_hard_clean(instance, result)
    assert kpis["placed"] == 3
    per_slot = {}
    for value, room in zip(result.values, result.rooms):
        per_slot.setdefault(value[0], []).append(room)
    assert max(len(v) for v in per_slot.values()) <= 2
    assert all(room is not None for room in result.rooms)


def test_teacher_idle_pairs_are_minimised_on_an_easy_instance():
    # Bir müəllim, üç qrup, hər qrupa bir dərs, bir gün: ideal həll boşluqsuzdur.
    cohorts = [_cohort(f"G{k}", pairs=(0, 1, 2, 3, 4, 5), days=1) for k in range(3)]
    events = [_event(f"E{k}", 0, [k], k, set(cohorts[k].allowed)) for k in range(3)]
    instance = Instance(days=1, pairs=P, teachers=[Teacher("t")], cohorts=cohorts, events=events)
    result = solve(instance, _params())
    kpis = _assert_hard_clean(instance, result)
    assert kpis["soft"]["teacher_idle_pairs"] == 0
