"""Dərs yükü (TAPŞIRIQ) sətrindən BİR QRUPUN saat bölgüsü — sillabusun plan saatı.

Sahib 2026-10-25: «Fənn 75 saatdır. Patok dərsidir — mühazirədə birdir, amma seminarda bölünür. Müəllimin dərs
yükü 105 saat olsa da, sillabus olaraq 75 saat yazmalıdır.»  Sillabus FƏNNİN bir qrup üçün saatıdır, müəllimin
ümumi yükü deyil (235 K + 235 İT: mühazirə 45 birlikdə + seminar 30 + 30 → yük 105, sillabus 45 + 30 = 75).

Qayda (rəsmi tapşırıq şablonunun sütunları üzrə)
------------------------------------------------
* ``*_plan`` («plan üzrə») BİR QRUPUN saatıdır — birləşmə (``union_count``) və yarımqrup (``subgroup_count``)
  sayından asılı deyil, olduğu kimi götürülür.  Birləşmə sətrində ``plan == cəm`` normaldır (bütün axın bir
  yerdə oxuyur — məs. xarici dil 105, 5 qrup birlikdə → hər qrupun sillabusu 105).
* ``*_plan`` boşdursa (kitabçadan YALNIZ cəm idxal olunub):

  - mühazirə — cəm (axın mühazirəni bir dəfə dinləyir);
  - seminar/lab — cəm ÷ bölmə sayı.  Yarımqrup sayı > 1 → o (şablonun tərifi, dəqiq); birləşmə > 1 → bölünmür
    (birgə); əks halda qrup sayı — tələbə sayı yazılışındakı ədədlərdən («25  40» → 2), yoxdursa bağlı
    qruplardan.  Qrup sayından bölmə yalnız TAM bölünəndə və pay mühazirənin yarısından ÇOX olanda qəbul
    olunur (45 + 60, 2 qrup → 30; 30 + 30, 2 qrup → birgə 30) — əks halda seminar birgə sayılır (cəm).  Qeyri-müəyyən hal kafedranın «plan saatını düzəlt»
    imkanı ilə həll olunur (``Syllabus.plan_hours_override``).
* Eyni fənn + dövr + qrup üçün BİR NEÇƏ sətir (axın sətri + qrupun öz sətri, iki kitabça) → növ üzrə ƏN BÖYÜYÜ.
  Cəm DEYİL: real yükdə eyni saat həm birləşmə, həm qrup sətrində təkrarlanır (cəm kreditdən iki dəfə çox çıxır).

Model ``get_model`` ilə həll olunur: registrar → workload Python import kənarı yaranmır (modul-sərhəd qapısı).
"""

from __future__ import annotations

import re

KINDS = ("lecture", "seminar", "lab")
_NUMBER = re.compile(r"\d+")


def _int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def section_count(row, group_count: int | None = None) -> tuple[int, bool]:
    """Seminar/lab bölmələrinin sayı → ``(say, dəqiqdir)``.

    ``dəqiqdir`` — yarımqrup sütunundan gəlir (şablonun tərifi); qrup sayından çıxarılan təxmindir.
    """
    subgroups = _int(getattr(row, "subgroup_count", 1))
    if subgroups > 1:
        return subgroups, True
    if _int(getattr(row, "union_count", 1)) > 1:
        return 1, True
    parts = _NUMBER.findall(getattr(row, "student_count_text", "") or "")
    if parts:
        return len(parts), False
    return max(_int(group_count), 1), False


def _split_total(total: int, sections: int, exact: bool, lecture: int) -> int:
    if not total or sections <= 1:
        return total
    if exact:
        return max(round(total / sections), 1)
    share, rest = divmod(total, sections)
    if rest or (lecture and share * 2 <= lecture):
        return total
    return share


def row_group_hours(row, *, group_count: int | None = None) -> dict:
    """BİR tapşırıq sətrindən bir qrupa düşən ``{növ: saat}`` (boş növlər atılır)."""
    lecture = _int(row.lecture_plan) or _int(row.lecture_total)
    hours = {"lecture": lecture} if lecture else {}
    sections = None
    for kind in ("seminar", "lab"):
        plan = _int(getattr(row, f"{kind}_plan"))
        total = _int(getattr(row, f"{kind}_total"))
        if not plan and total and sections is None:
            sections = section_count(row, group_count() if callable(group_count) else group_count)
        value = plan or (_split_total(total, sections[0], sections[1], lecture) if total else 0)
        if value:
            hours[kind] = value
    return hours


def merge_group_hours(shares) -> dict:
    """Bir neçə sətrin payı → növ üzrə ən böyük dəyər (sıra ``KINDS``)."""
    merged: dict = {}
    for share in shares:
        for kind, value in (share or {}).items():
            if value and value > merged.get(kind, 0):
                merged[kind] = value
    return {kind: merged[kind] for kind in KINDS if merged.get(kind)}


def _task_row_model():
    from django.apps import apps as django_apps

    try:
        return django_apps.get_model("workload", "TeachingTaskRow")
    except LookupError:
        return None


def workload_hours_for_offering(offering) -> dict:
    """Açılışın (fənn + dövr + qrup) yük sətirlərindən BİR QRUPUN bölgüsü (``{}`` — sətir yoxdur)."""
    if offering is None or not (getattr(offering, "subject_id", None) and getattr(offering, "period_id", None)):
        return {}
    TaskRow = _task_row_model()
    if TaskRow is None:
        return {}
    rows = TaskRow.objects.filter(
        organization_id=offering.organization_id, subject_id=offering.subject_id, period_id=offering.period_id
    ).exclude(task__status="cancelled")
    if offering.group_id:
        rows = rows.filter(groups=offering.group_id)
    shares = [row_group_hours(row, group_count=row.groups.count) for row in rows.order_by("-updated_at")]
    return merge_group_hours(shares)


def workload_hours_by_offering(offerings) -> dict:
    """``workload_hours_for_offering``-in TOPLU qarşılığı — iki sorğu (sətirlər + qrupları)."""
    offerings = [offering for offering in offerings if offering is not None and offering.subject_id]
    TaskRow = _task_row_model()
    if not offerings or TaskRow is None:
        return {}
    queryset = (
        TaskRow.objects.filter(
            organization_id=offerings[0].organization_id,
            subject_id__in={offering.subject_id for offering in offerings},
            period_id__in={offering.period_id for offering in offerings},
        )
        .exclude(task__status="cancelled")
        .prefetch_related("groups")
    )
    rows = []
    for row in queryset:
        group_ids = {group.pk for group in row.groups.all()}
        rows.append((row, group_ids, row_group_hours(row, group_count=len(group_ids))))
    result = {}
    for offering in offerings:
        result[offering.pk] = merge_group_hours(
            share
            for row, group_ids, share in rows
            if row.subject_id == offering.subject_id
            and row.period_id == offering.period_id
            and (not offering.group_id or offering.group_id in group_ids)
        )
    return result


__all__ = [
    "merge_group_hours",
    "row_group_hours",
    "section_count",
    "workload_hours_by_offering",
    "workload_hours_for_offering",
]
