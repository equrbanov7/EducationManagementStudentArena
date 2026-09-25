"""Açılışın müəllimləri və saatları — cədvəl generatoru üçün OXU API-si (2026-09-25).

``apps.workload.public.teachers_for_offering(s)`` bunu açır. Mənbə — açılışı
ƏHATƏ EDƏN tapşırıq sətirləri: eyni fənn + eyni semestr + sətrin qrupları
arasında açılışın qrupu var (ləğv edilmiş sənədlər xaric). Bölgü (split
teaching) ``TeacherAssignment``-dadır: mühazirə bir müəllimdə, seminar/lab
yarımqruplar üzrə bir neçə müəllimdə ola bilər.

Qaytarılan lüğət (açılış başına)::

    {
        "lecture": User | None,       # jurnal sahibi (offering.instructor), yoxdursa yükün mühazirəçisi
        "seminar": [User, ...],       # vakant-olmayan seminar müəllimləri (təkrarsız, bölgü sırası ilə)
        "lab": [User, ...],           # vakant-olmayan laboratoriya müəllimləri
        "workload_lecture": User | None,  # yalnız yükdən (bölgü) — jurnal sahibindən fərqli ola bilər
        "hours": {"lecture": int, "seminar": int, "lab": int},  # QRUP başına semestr saatı
        "vacant": ["seminar", ...],   # vakant və ya hələ bölünməmiş (müəllimsiz) auditoriya fəaliyyətləri
        "row_ids": ["<uuid>", ...],   # əhatə edən tapşırıq sətirləri
    }

NİYƏ ``lecture`` = jurnal sahibi: spec §11.3 — jurnal sahibi mühazirəçidir;
sinxron ikisini eyni saxlayır, fərq yalnız «Fənn təhvili» (və ya cədvəl
redaktoru) müəllimi dəyişəndə yaranır — o halda dərsi FAKTİKİ aparan jurnal
sahibidir. Çoxqruplu sətirdə seminar/lab siyahısı SƏTİR səviyyəsindədir
(yarımqrup bölgüsü ``groups_note`` mətnindədir, strukturlaşdırılmayıb).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

from ..constants import Activity, TaskStatus
from ..models import TeachingTaskRow
from .offering_rules import merge_hours
from .offering_sync import assignments_prefetch

_TEACHING = {Activity.LECTURE: "lecture", Activity.SEMINAR: "seminar", Activity.LAB: "lab"}


def _empty() -> dict:
    return {
        "lecture": None,
        "seminar": [],
        "lab": [],
        "workload_lecture": None,
        "hours": {"lecture": 0, "seminar": 0, "lab": 0},
        "vacant": [],
        "row_ids": [],
    }


def _covering_rows(offerings) -> dict:
    """``(fənn, semestr, qrup)`` → əhatə edən sətirlər (bir sorğu + iki prefetch)."""
    by_key: dict = {}
    rows = (
        TeachingTaskRow.objects.filter(
            organization_id__in={o.organization_id for o in offerings},
            subject_id__in={o.subject_id for o in offerings},
            period_id__in={o.period_id for o in offerings},
        )
        .exclude(task__status=TaskStatus.CANCELLED)
        .prefetch_related("groups", assignments_prefetch())
        .order_by("created_at")
    )
    for row in rows:
        for group in row.groups.all():
            by_key.setdefault((row.subject_id, row.period_id, group.pk), []).append(row)
    return by_key


def _describe(offering, rows, instructors) -> dict:
    result = _empty()
    result["row_ids"] = [str(row.pk) for row in rows]
    result["hours"] = merge_hours(rows)
    seen = {"seminar": set(), "lab": set()}
    vacant = set()
    for row in rows:
        for assignment in row.assignments.all():
            kind = _TEACHING.get(assignment.activity)
            if kind is None:
                continue
            if not assignment.teacher_id:
                vacant.add(kind)
            elif kind == "lecture":
                result["workload_lecture"] = result["workload_lecture"] or assignment.teacher
            elif assignment.teacher_id not in seen[kind]:
                seen[kind].add(assignment.teacher_id)
                result[kind].append(assignment.teacher)
    result["lecture"] = instructors.get(offering.instructor_id) or result["workload_lecture"]
    for kind in ("lecture", "seminar", "lab"):
        if result["hours"][kind] and not result[kind]:
            vacant.add(kind)
    result["vacant"] = sorted(vacant)
    return result


def teachers_for_offerings(offerings) -> dict:
    """``{offering.pk: {...}}`` — toplu forma: açılış sayından asılı olmayan sorğu sayı."""
    offerings = [o for o in offerings if o is not None]
    result = {offering.pk: _empty() for offering in offerings}
    usable = [o for o in offerings if o.subject_id and o.period_id and o.group_id]
    if not usable:
        return result
    by_key = _covering_rows(usable)
    instructor_ids = {o.instructor_id for o in usable if o.instructor_id}
    instructors = {user.pk: user for user in get_user_model().objects.filter(pk__in=instructor_ids)}
    for offering in usable:
        rows = by_key.get((offering.subject_id, offering.period_id, offering.group_id), [])
        result[offering.pk] = _describe(offering, rows, instructors)
    return result


def teachers_for_offering(offering) -> dict:
    """Bir açılışın müəllimləri — bax modul başlığı (``lecture``/``seminar``/``lab`` + saat)."""
    if offering is None:
        return _empty()
    return teachers_for_offerings([offering])[offering.pk]


__all__ = ["teachers_for_offering", "teachers_for_offerings"]
