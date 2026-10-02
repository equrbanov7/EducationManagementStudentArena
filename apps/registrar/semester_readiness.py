"""«Semestr hazırlığı» — kafedra üzrə nə çatışmır və kimə xatırlatmaq lazımdır (sahib 2026-10-03).

«Semestr açılışı» bölməsi açılış prosesini (plan → kafedra → müəllim → kilid) izləyirdi; semestr
BAŞLAYANDAN sonra isə sual başqadır: hansı fənnin müəllimi, təsdiqlənmiş sillabusu, dərs cədvəli yoxdur
və hansı jurnalda dərs yazılmır. Bu modul hər aktiv açılış üçün dörd problemi hesablayır (heç nə
SAXLANILMIR — §8/13), kafedra üzrə yığır və «Xatırlat» bildirişlərini qurur.

PROBLEMLƏR (``ISSUES``):

* ``no_teacher``  — açılışa müəllim təyin olunmayıb (kafedra «Dərs yükü»ndən təyin edir);
* ``no_syllabus`` — açılışın sillabusu yoxdur və ya təsdiqlənməyib. Qayda jurnaldakı ilə EYNİDİR
  (``journal_policy.offering_has_approved_syllabus``): üç pilləli axtarışda ilk tapılan dosye
  (açılışın öz → fənn+dövr → fənn+müəllif) və onun ``approved_version``-u;
* ``no_schedule`` — cədvəldə (park edilməmiş) slotu yoxdur;
* ``no_journal``  — semestr başlayandan ``JOURNAL_GRACE_DAYS`` gün keçib, amma jurnalda dərs yoxdur və ya
  son dərs ``JOURNAL_STALE_DAYS`` gündən köhnədir. Semestr bitibsə və ya başlamayıbsa sayılmır.
"""

from __future__ import annotations

from datetime import timedelta

from django.apps import apps as django_apps
from django.db.models import Max
from django.utils import timezone

from .models import CourseOffering, Lesson, ScheduleSlot

ISSUES = ("no_teacher", "no_syllabus", "no_schedule", "no_journal")

#: Semestrin ilk həftəsi — jurnalın hələ boş olması normaldır.
JOURNAL_GRACE_DAYS = 7
#: Bu qədər gün dərs yazılmırsa jurnal «dayanıb» sayılır.
JOURNAL_STALE_DAYS = 14


def approved_syllabus_offering_ids(organization, period, offerings) -> set:
    """Təsdiqlənmiş sillabusu olan açılışların id-ləri — jurnal qaydası ilə eyni, sabit sorğu sayı."""
    if not offerings:
        return set()
    Syllabus = django_apps.get_model("syllabus", "Syllabus")
    subject_ids = {row["subject_id"] for row in offerings}
    candidates = (
        Syllabus.objects.filter(organization=organization, is_active=True, subject_id__in=subject_ids)
        .order_by("subject__code", "pk")
        .values_list("offering_id", "subject_id", "period_id", "author_id", "approved_version_id")
    )
    by_offering, by_period, by_author = {}, {}, {}
    for offering_id, subject_id, period_id, author_id, approved_id in candidates:
        approved = approved_id is not None
        if offering_id is not None:
            by_offering.setdefault(offering_id, approved)
        elif period_id is not None:
            if period_id == period.pk:
                by_period.setdefault(subject_id, approved)
        else:
            by_author.setdefault((subject_id, author_id), approved)

    approved_ids = set()
    for row in offerings:
        if row["id"] in by_offering:
            ok = by_offering[row["id"]]
        elif row["subject_id"] in by_period:
            ok = by_period[row["subject_id"]]
        elif row["instructor_id"] is not None:
            ok = by_author.get((row["subject_id"], row["instructor_id"]), False)
        else:
            ok = False
        if ok:
            approved_ids.add(row["id"])
    return approved_ids


def _journal_window(period, today):
    """``(yoxlanılırmı, son dərsin ən köhnə qəbul tarixi)`` — semestr aktiv deyilsə yoxlanmır."""
    if period.start_date is None or today < period.start_date + timedelta(days=JOURNAL_GRACE_DAYS):
        return False, None
    if period.end_date is not None and today > period.end_date:
        return False, None
    return True, today - timedelta(days=JOURNAL_STALE_DAYS)


def offering_issues(organization, period, *, offering_ids=None, today=None) -> dict:
    """``{offering_id: {"issues": [...], "subject": …, "group": …, "chair_id": …, "instructor_id": …}}``."""
    today = today or timezone.localdate()
    qs = CourseOffering.objects.filter(organization=organization, period=period, is_active=True)
    if offering_ids is not None:
        qs = qs.filter(pk__in=list(offering_ids))
    offerings = list(
        qs.values(
            "id",
            "subject_id",
            "instructor_id",
            "subject__name",
            "group__name",
            "subject__chair_unit_id",
            "subject__chair_unit__name",
        )
    )
    if not offerings:
        return {}
    ids = [row["id"] for row in offerings]
    approved = approved_syllabus_offering_ids(organization, period, offerings)
    scheduled = set(
        ScheduleSlot.objects.filter(offering_id__in=ids, is_parked=False).values_list("offering_id", flat=True)
    )
    check_journal, stale_before = _journal_window(period, today)
    last_lesson = (
        dict(Lesson.objects.filter(offering_id__in=ids).values_list("offering_id").annotate(last=Max("date")))
        if check_journal
        else {}
    )

    result = {}
    for row in offerings:
        issues = []
        if row["instructor_id"] is None:
            issues.append("no_teacher")
        if row["id"] not in approved:
            issues.append("no_syllabus")
        if row["id"] not in scheduled:
            issues.append("no_schedule")
        if check_journal:
            last = last_lesson.get(row["id"])
            if last is None or last < stale_before:
                issues.append("no_journal")
        result[row["id"]] = {
            "issues": issues,
            "subject": row["subject__name"] or "",
            "group": row["group__name"] or "",
            "chair_id": row["subject__chair_unit_id"],
            "chair_name": row["subject__chair_unit__name"] or "",
            "instructor_id": row["instructor_id"],
        }
    return result


def readiness_by_chair(organization, period, *, issues_map=None) -> dict:
    """Kafedra sətirləri (ən az hazır birinci) + ümumi cəm. ``pct`` = problemsiz açılışların payı."""
    issues_map = offering_issues(organization, period) if issues_map is None else issues_map
    chairs: dict = {}
    for item in issues_map.values():
        key = str(item["chair_id"]) if item["chair_id"] else ""
        bucket = chairs.setdefault(
            key, {"chair_id": key, "name": item["chair_name"], "total": 0, "ready": 0, **{k: 0 for k in ISSUES}}
        )
        bucket["total"] += 1
        bucket["ready"] += 0 if item["issues"] else 1
        for issue in item["issues"]:
            bucket[issue] += 1
    rows = [{**row, "pct": round(100 * row["ready"] / row["total"]) if row["total"] else 0} for row in chairs.values()]
    rows.sort(key=lambda row: (row["pct"], -row["total"], row["name"]))
    totals = {key: sum(row[key] for row in rows) for key in ("total", "ready", *ISSUES)}
    totals["pct"] = round(100 * totals["ready"] / totals["total"]) if totals["total"] else 0
    return {"rows": rows, "totals": totals}


def offering_ids_with_issue(organization, period, issue: str, *, chair_id: str = "") -> list:
    """«Problem» süzgəci üçün: bu problemi olan açılışların id-ləri (kafedra ilə daralda bilər)."""
    if issue not in ISSUES:
        return []
    return [
        offering_id
        for offering_id, item in offering_issues(organization, period).items()
        if issue in item["issues"] and (not chair_id or str(item["chair_id"]) == chair_id)
    ]


__all__ = [
    "ISSUES",
    "JOURNAL_GRACE_DAYS",
    "JOURNAL_STALE_DAYS",
    "approved_syllabus_offering_ids",
    "offering_ids_with_issue",
    "offering_issues",
    "readiness_by_chair",
]
