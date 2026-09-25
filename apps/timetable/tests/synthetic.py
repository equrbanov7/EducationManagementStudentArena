"""Sintetik (Django-sız) cədvəl nümunələri — mühərrik testləri və benchmark üçün.

``uctp_bench.py``-dakı generatorun deterministik (seed-li) versiyası: bakalavr
«ailələri» (1–3 qrup, ortaq mühazirə axını), qrup başına məşğələlər, üst/alt
həftə laboratoriyaları, yalnız AXŞAM oxuyan magistr qrupları, bəzi müəllimlərin
bütöv «gələ bilmədiyi» günü və «dəyişdirilə bilən» (arzuolunmaz) saatları.
"""

from __future__ import annotations

import random

from apps.timetable.engine import Building, Cohort, Event, Instance, Teacher

MORNING = (0, 1, 2)
AFTERNOON = (3, 4, 5)
EVENING = (6, 7)


def _levels(rng, days, pairs, *, p_off, days_off, discouraged):
    levels = ["n"] * (days * pairs)
    if rng.random() < p_off:
        for d in rng.sample(range(days), days_off):
            for p in range(pairs):
                levels[d * pairs + p] = "u"
    for _ in range(rng.randint(0, discouraged)):
        t = rng.randrange(days * pairs)
        if levels[t] == "n":
            levels[t] = "d"
    return "".join(levels)


def make_instance(
    *,
    seed=1,
    teachers=40,
    families=12,
    masters=4,
    subjects=6,
    days=6,
    pairs=8,
    p_off=0.25,
    days_off=1,
    discouraged=4,
    shifts=True,
    building_capacity=0,
):
    """Deterministik sintetik nümunə (bax modul şərhi)."""
    rng = random.Random(seed)
    teacher_list = [
        Teacher(
            key=f"t{k}",
            label=f"Müəllim {k}",
            priority=rng.choice((1, 1, 1, 2, 3)),
            levels=_levels(rng, days, pairs, p_off=p_off, days_off=days_off, discouraged=discouraged),
        )
        for k in range(teachers)
    ]
    cohorts = []
    events = []
    bands = []

    def add_cohort(label, band, *, master=False):
        allowed = frozenset(d * pairs + p for d in range(days) for p in band)
        cohorts.append(Cohort(key=label, label=label, max_per_day=4, is_master=master, allowed=allowed))
        bands.append(band)
        return len(cohorts) - 1

    def add_event(key, kind, cohort_ids, course, *, biweekly=False):
        teacher = rng.randrange(teachers)
        allowed = set.intersection(*(set(cohorts[c].allowed) for c in cohort_ids))
        levels = teacher_list[teacher].levels
        domain = tuple(sorted(t for t in allowed if levels[t] != "u"))
        events.append(
            Event(
                key=key,
                kind=kind,
                teacher=teacher,
                cohorts=tuple(cohort_ids),
                course=course,
                biweekly=biweekly,
                domain=domain,
                priority=teacher_list[teacher].priority,
                building=0 if building_capacity else None,
                size=25 * len(cohort_ids),
                domain_reason="" if domain else "teacher_unavailable",
            )
        )

    course = 0
    for f in range(families):
        band = (MORNING if f % 2 == 0 else AFTERNOON) if shifts else MORNING + AFTERNOON
        members = [add_cohort(f"B{f}-{g}", band) for g in range(rng.randint(1, 3))]
        for s in range(subjects):
            course += 1
            add_event(f"lec:{f}:{s}", "lecture", members, course)
            for g in members:
                if s < subjects - 1:
                    add_event(f"sem:{f}:{s}:{g}", "seminar", [g], course, biweekly=(s % 3 == 2))
                else:
                    add_event(f"lab:{f}:{s}:{g}:o", "lab", [g], course, biweekly=True)
                    add_event(f"lab:{f}:{s}:{g}:e", "lab", [g], course, biweekly=True)
    for m in range(masters):
        cohort = add_cohort(f"M{m}", EVENING, master=True)
        for s in range(4):
            course += 1
            add_event(f"mlec:{m}:{s}", "lecture", [cohort], course)
            add_event(f"msem:{m}:{s}", "seminar", [cohort], course, biweekly=True)
    buildings = [Building(key="A", label="Korpus A", capacity=building_capacity)] if building_capacity else []
    return Instance(
        days=days,
        pairs=pairs,
        teachers=teacher_list,
        cohorts=cohorts,
        events=events,
        buildings=buildings,
    )


__all__ = ["AFTERNOON", "EVENING", "MORNING", "make_instance"]
