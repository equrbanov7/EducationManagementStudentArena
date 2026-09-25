"""«Məlumatı yoxla» — işləmədən ƏVVƏL tələb ↔ tutum analizi (heç nə yazmır).

Nəyi yoxlayır (hər biri üçün say + ilk sətirlər):

* hadisə domeni boşdur (qrup növbəsi ∩ müəllimin «gələ bilir» xanaları) — XƏTA;
* müəllim: həftəlik cüt tələbi > uyğun boş xanalar (kənar dərslər çıxılmaqla) — XƏTA,
  80%-dən çox — XƏBƏRDARLIQ;
* qrup (kohort): tələb > icazəli xanalar və ya gündəlik limit × gün — XƏTA;
* magistr: axşam xanaları tələbə çatmır — XƏTA (siyasətdə günortanı açmaq təklifi);
* korpus: bir növbədə eyni anda lazım olan otaq sayı > korpusdakı otaq sayı — XƏTA;
* məlumat boşluqları: saatı olmayan açılış, müəllimsiz (vakant) dərs, qiyabi/istisna
  qruplar, axınlar, kilidli dərsin domendən kənar qalması.
"""

from __future__ import annotations

import math

from django.utils.translation import pgettext

_CTX = "timetable.precheck"

ERROR, WARNING, INFO = "error", "warning", "info"


def _units(event) -> float:
    return 0.5 if event.biweekly else 1.0


def _item(level, code, title, detail="", count=0, rows=None):
    return {
        "level": level,
        "code": code,
        "title": title,
        "detail": detail,
        "count": count,
        "rows": list(rows or [])[:12],
    }


def _fmt(value) -> str:
    return ("%.1f" % value).rstrip("0").rstrip(".")


def _teacher_checks(problem, out):
    inst = problem.instance
    S = inst.slots
    busy: dict = {}
    for teacher, wk, t in inst.teacher_busy:
        busy.setdefault(teacher, {}).setdefault(t, set()).add(wk)
    demand: dict = {}
    cells: dict = {}
    for event in inst.events:
        if event.teacher is None:
            continue
        demand[event.teacher] = demand.get(event.teacher, 0.0) + _units(event)
        cells.setdefault(event.teacher, set()).update(event.domain)
    over, tight = [], []
    for teacher, need in sorted(demand.items()):
        free = 0.0
        for t in cells.get(teacher, ()):
            if t >= S:
                continue
            taken = len(busy.get(teacher, {}).get(t, ()))
            free += (2 - taken) / 2
        name = problem.teacher_names.get(problem.teacher_ids[teacher], str(problem.teacher_ids[teacher]))
        limit = inst.teachers[teacher].max_per_day
        if limit:
            free = min(free, float(limit * inst.days))
        row = f"{name}: {_fmt(need)} / {_fmt(free)}"
        if need > free:
            over.append(row)
        elif free and need > 0.8 * free:
            tight.append(row)
    if over:
        out.append(
            _item(
                ERROR,
                "teacher_over",
                pgettext(_CTX, "Müəllimin həftəlik dərsi uyğun boş xanalardan çoxdur"),
                pgettext(_CTX, "Tələb / tutum (cüt/həftə). Əlçatanlığı genişləndirin və ya dərsi başqasına verin."),
                len(over),
                over,
            )
        )
    if tight:
        out.append(
            _item(
                WARNING,
                "teacher_tight",
                pgettext(_CTX, "Müəllimin vaxtı çox sıxdır (80%-dən çox dolu)"),
                pgettext(_CTX, "Tələb / tutum (cüt/həftə) — boşluqsuz cədvəl çətinləşə bilər."),
                len(tight),
                tight,
            )
        )


def _cohort_checks(problem, out):
    inst = problem.instance
    demand: dict = {}
    for event in inst.events:
        for c in event.cohorts:
            demand[c] = demand.get(c, 0.0) + _units(event)
    over, masters = [], []
    for c, need in sorted(demand.items()):
        cohort = inst.cohorts[c]
        capacity = float(len(cohort.allowed))
        if cohort.max_per_day:
            days = len({t // inst.pairs for t in cohort.allowed})
            capacity = min(capacity, float(cohort.max_per_day * days))
        row = f"{cohort.label}: {_fmt(need)} / {_fmt(capacity)}"
        if need > capacity:
            (masters if cohort.is_master else over).append(row)
    if over:
        out.append(
            _item(
                ERROR,
                "group_over",
                pgettext(_CTX, "Qrupun həftəlik dərsi icazəli xanalara sığmır"),
                pgettext(_CTX, "Tələb / tutum (cüt/həftə). Növbəni genişləndirin və ya gündəlik limiti artırın."),
                len(over),
                over,
            )
        )
    if masters:
        out.append(
            _item(
                ERROR,
                "master_evening",
                pgettext(_CTX, "Magistr qruplarının dərsi axşam xanalarına sığmır"),
                pgettext(_CTX, "Tələb / axşam tutumu. Növbə siyasətində magistr üçün günortanı açmaq olar."),
                len(masters),
                masters,
            )
        )


def _building_checks(problem, out):
    inst = problem.instance
    if not inst.buildings:
        return
    band_of = {}
    for p, row in enumerate(problem.periods):
        band_of[p] = row["shift"]
    need: dict = {}
    slots: dict = {}
    for event in inst.events:
        if event.building is None or not event.domain:
            continue
        bands = {band_of[t % inst.pairs] for t in event.domain}
        key = (event.building, "+".join(sorted(bands)))
        need[key] = need.get(key, 0.0) + _units(event)
        slots.setdefault(key, set()).update(event.domain)
    over = []
    for (building, bands), demand in sorted(need.items()):
        capacity = inst.buildings[building].capacity
        width = len(slots[(building, bands)]) or 1
        peak = math.ceil(demand / width)
        if capacity and peak > capacity:
            over.append(f"{inst.buildings[building].label} ({bands}): {peak} / {capacity}")
    if over:
        out.append(
            _item(
                ERROR,
                "rooms_peak",
                pgettext(_CTX, "Korpusda eyni anda lazım olan otaq sayı mövcud otaqlardan çoxdur"),
                pgettext(_CTX, "Lazım olan / mövcud otaq."),
                len(over),
                over,
            )
        )


def _domain_checks(problem, out):
    labels = {
        "no_common_band": pgettext(_CTX, "axının qruplarının ortaq növbəsi yoxdur"),
        "group_no_slots": pgettext(_CTX, "qrup üçün icazəli xana yoxdur"),
        "teacher_unavailable": pgettext(_CTX, "müəllim qrupun növbəsində heç gələ bilmir"),
    }
    rows = []
    for event, meta in zip(problem.instance.events, problem.events):
        if event.domain:
            continue
        groups = ", ".join(problem.groups[g].name for g in meta["groups"] if g in problem.groups)
        rows.append(f"{meta['subject']} · {groups} — {labels.get(event.domain_reason, event.domain_reason)}")
    if rows:
        out.append(
            _item(
                ERROR,
                "empty_domain",
                pgettext(_CTX, "Bəzi dərslər üçün heç bir mümkün vaxt yoxdur"),
                pgettext(_CTX, "Bu dərslər yerləşdirilməyəcək — səbəbi sətirdə göstərilib."),
                len(rows),
                rows,
            )
        )


def _data_checks(problem, out):
    texts = {
        "no_hours": (WARNING, pgettext(_CTX, "Saat bölgüsü tapılmayan açılışlar (plan/tapşırıqda saat yoxdur)")),
        "vacant_teacher": (
            WARNING,
            pgettext(_CTX, "Müəllimi təyin edilməmiş dərslər (vakant) — yalnız qrupa görə yerləşir"),
        ),
        "excluded_groups": (INFO, pgettext(_CTX, "Cədvələ daxil edilməyən qruplar (qiyabi və ya siyasətdə istisna)")),
        "streams": (INFO, pgettext(_CTX, "Mühazirə axınları (bir neçə qrup birlikdə)")),
        "locked_outside_domain": (WARNING, pgettext(_CTX, "Kilidli dərs indiki növbə/əlçatanlıqdan kənardadır")),
    }
    for issue in problem.issues:
        level, title = texts.get(issue["code"], (INFO, issue["code"]))
        out.append(_item(level, issue["code"], title, "", issue.get("count", 0), issue.get("items")))


def summary(problem) -> dict:
    inst = problem.instance
    weekly = sum(_units(event) for event in inst.events)
    return {
        "groups": len(problem.groups),
        "cohorts": len(inst.cohorts),
        "events": len(inst.events),
        "weekly_pairs": _fmt(weekly),
        "teachers": len(inst.teachers),
        "rooms": len(inst.rooms),
        "streams": sum(1 for meta in problem.events if meta["stream"]),
        "external_busy": len({(t, wk) for _r, wk, t in inst.teacher_busy}),
    }


def run_precheck(problem) -> dict:
    items: list = []
    _domain_checks(problem, items)
    _teacher_checks(problem, items)
    _cohort_checks(problem, items)
    _building_checks(problem, items)
    _data_checks(problem, items)
    order = {ERROR: 0, WARNING: 1, INFO: 2}
    items.sort(key=lambda item: order[item["level"]])
    return {
        "ok": not any(item["level"] == ERROR for item in items),
        "errors": sum(1 for item in items if item["level"] == ERROR),
        "warnings": sum(1 for item in items if item["level"] == WARNING),
        "summary": summary(problem),
        "items": items,
    }


__all__ = ["run_precheck", "summary"]
