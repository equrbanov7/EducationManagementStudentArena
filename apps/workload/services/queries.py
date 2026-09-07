"""Oxu sorğuları: bölgü cədvəli, müəllim yük paneli, «Dərs yüküm» sətirləri."""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db.models import Q, Sum

from ..constants import (
    DEFAULT_ANNUAL_NORM_HOURS,
    Activity,
    Season,
    TaskStatus,
)
from ..models import TeacherAssignment, TeacherWorkloadProfile, TeachingTask, TeachingTaskRow
from .assignments import balance_for_rows

_ACTIVITY_LABELS = {str(value): str(label) for value, label in Activity.choices}
_SEASON_LABELS = {str(value): str(label) for value, label in Season.choices}


def task_rows(task, *, season: str = "", search: str = ""):
    queryset = (
        TeachingTaskRow.objects.filter(task=task)
        .select_related("subject", "specialty", "period")
        .prefetch_related("groups", "assignments__teacher")
        .order_by("season", "order", "created_at")
    )
    if season:
        queryset = queryset.filter(season=season)
    if search:
        queryset = queryset.filter(
            Q(subject__name__icontains=search)
            | Q(subject__code__icontains=search)
            | Q(subject_text__icontains=search)
            | Q(groups_text__icontains=search)
        )
    return queryset


def serialize_rows(task, *, season: str = "", search: str = "") -> list[dict]:
    rows = list(task_rows(task, season=season, search=search))
    balance = balance_for_rows(rows)
    payload = []
    for row in rows:
        info = balance.get(str(row.pk), {})
        payload.append(
            {
                "id": str(row.pk),
                "season": row.season,
                "season_label": _SEASON_LABELS.get(row.season, row.season),
                "subject": row.subject_label,
                "subject_id": str(row.subject_id) if row.subject_id else "",
                "period_id": str(row.period_id) if row.period_id else "",
                # ⚠️ `str(period)` `organization.name`-ə toxunur (əlavə sorğu) —
                # etiket sahələrdən birbaşa yığılır.
                "period_label": (f"{row.period.name} · {row.period.academic_year}" if row.period_id else ""),
                "specialty": row.specialty.name if row.specialty_id else row.specialty_text,
                "groups": [{"id": str(g.pk), "name": g.name} for g in row.groups.all()],
                "groups_text": row.groups_text,
                "education_form": row.education_form,
                "degree_level": row.degree_level,
                "student_count": row.student_count,
                "student_count_text": row.student_count_text,
                "union_count": row.union_count,
                "subgroup_count": row.subgroup_count,
                "credits": row.credits or (str(row.credits_value) if row.credits_value else ""),
                "total_hours": row.total_hours,
                "row_kind": row.row_kind,
                "activities": info.get("activities", {}),
                "teaching_complete": info.get("teaching_complete", True),
                "assignments": [
                    {
                        "id": str(assignment.pk),
                        "activity": assignment.activity,
                        "activity_label": _ACTIVITY_LABELS.get(assignment.activity, assignment.activity),
                        "hours": assignment.hours,
                        "teacher_id": str(assignment.teacher_id) if assignment.teacher_id else "",
                        "teacher_name": (
                            (assignment.teacher.get_full_name() or assignment.teacher.username)
                            if assignment.teacher_id
                            else "Vakant"
                        ),
                        "is_vacant": assignment.teacher_id is None,
                        "is_hourly_paid": assignment.is_hourly_paid,
                        "groups_note": assignment.groups_note,
                    }
                    for assignment in row.assignments.all()
                ],
            }
        )
    return payload


def _norm_for(organization, teacher_id, academic_year, profiles) -> int:
    profile = profiles.get(teacher_id)
    return int(profile.annual_norm_hours if profile else DEFAULT_ANNUAL_NORM_HOURS)


def teacher_load_panel(task) -> list[dict]:
    """Sağ paneldəki müəllim kartları: cəmi saat / norma / doluluq %."""
    assignments = (
        TeacherAssignment.objects.filter(row__task=task).select_related("teacher", "row").order_by("teacher__last_name")
    )
    profiles = {
        profile.teacher_id: profile
        for profile in TeacherWorkloadProfile.objects.filter(
            organization=task.organization, academic_year=task.academic_year
        )
    }
    buckets: dict = {}
    for assignment in assignments:
        key = assignment.teacher_id
        bucket = buckets.setdefault(
            key,
            {
                "teacher_id": str(key) if key else "",
                "name": ((assignment.teacher.get_full_name() or assignment.teacher.username) if key else "Vakant"),
                "is_vacant": key is None,
                "hours": 0,
                "fall_hours": 0,
                "spring_hours": 0,
                "hourly_paid_hours": 0,
                "rows": 0,
            },
        )
        bucket["hours"] += int(assignment.hours or 0)
        bucket["rows"] += 1
        if assignment.row.season == Season.FALL:
            bucket["fall_hours"] += int(assignment.hours or 0)
        elif assignment.row.season == Season.SPRING:
            bucket["spring_hours"] += int(assignment.hours or 0)
        if assignment.is_hourly_paid:
            bucket["hourly_paid_hours"] += int(assignment.hours or 0)

    cards = []
    for key, bucket in buckets.items():
        norm = _norm_for(task.organization, key, task.academic_year, profiles) if key else 0
        bucket["norm_hours"] = norm
        bucket["fill_percent"] = int(round(bucket["hours"] * 100 / norm)) if norm else 0
        bucket["is_over_norm"] = bool(norm and bucket["hours"] > norm)
        cards.append(bucket)
    cards.sort(key=lambda item: (item["is_vacant"], -item["hours"]))
    return cards


# ── Müəllim səthi («Dərs yüküm») ────────────────────────────────────────────


def teacher_years(*, organization, teacher) -> list[str]:
    years = (
        TeacherAssignment.objects.filter(organization=organization, teacher=teacher)
        .values_list("row__task__academic_year", flat=True)
        .distinct()
    )
    return sorted({year for year in years if year}, reverse=True)


def teacher_workload_rows(*, organization, teacher, academic_year: str = "", season: str = "") -> list[dict]:
    """Müəllimin ÖZ bölgü sətirləri — YALNIZ təsdiqlənmiş tapşırıqlar.

    ⚠️ Müəllim yarımçıq bölgünü GÖRMÜR: sənəd ``distributed``/``amended``
    olmayana qədər sətirlər siyahıya düşmür (kafedra hələ işləyir).
    """
    queryset = (
        TeacherAssignment.objects.filter(
            organization=organization,
            teacher=teacher,
            row__task__status__in=(TaskStatus.DISTRIBUTED, TaskStatus.AMENDED),
        )
        .select_related("row", "row__subject", "row__task", "row__period", "row__specialty")
        .prefetch_related("row__groups")
        .order_by("row__season", "row__subject__name", "activity")
    )
    if academic_year:
        queryset = queryset.filter(row__task__academic_year=academic_year)
    if season:
        queryset = queryset.filter(row__season=season)

    offering_map = _offering_links(organization, queryset)
    rows = []
    for assignment in queryset:
        row = assignment.row
        rows.append(
            {
                "id": str(assignment.pk),
                "academic_year": row.task.academic_year,
                "season": row.season,
                "season_label": _SEASON_LABELS.get(row.season, row.season),
                "subject": row.subject_label,
                "groups": row.groups_text or ", ".join(group.name for group in row.groups.all()),
                "activity": assignment.activity,
                "activity_label": _ACTIVITY_LABELS.get(assignment.activity, assignment.activity),
                "hours": assignment.hours,
                "education_form": row.education_form,
                "degree_level": row.degree_level,
                "is_hourly_paid": assignment.is_hourly_paid,
                "groups_note": assignment.groups_note,
                "offering_id": offering_map.get((row.subject_id, row.period_id)) or "",
            }
        )
    return rows


def _offering_links(organization, assignments) -> dict:
    """(subject_id, period_id) → offering id — jurnal keçidi üçün."""
    pairs = {
        (assignment.row.subject_id, assignment.row.period_id)
        for assignment in assignments
        if assignment.row.subject_id and assignment.row.period_id
    }
    if not pairs:
        return {}
    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    lookup = Q()
    for subject_id, period_id in pairs:
        lookup |= Q(subject_id=subject_id, period_id=period_id)
    rows = (
        CourseOffering.objects.filter(organization=organization).filter(lookup).values("id", "subject_id", "period_id")
    )
    return {(row["subject_id"], row["period_id"]): str(row["id"]) for row in rows}


def teacher_workload_summary(*, organization, teacher, academic_year: str = "") -> dict:
    queryset = TeacherAssignment.objects.filter(
        organization=organization,
        teacher=teacher,
        row__task__status__in=(TaskStatus.DISTRIBUTED, TaskStatus.AMENDED),
    )
    if academic_year:
        queryset = queryset.filter(row__task__academic_year=academic_year)
    total = int(queryset.aggregate(total=Sum("hours"))["total"] or 0)
    hourly = int(queryset.filter(is_hourly_paid=True).aggregate(total=Sum("hours"))["total"] or 0)
    fall = int(queryset.filter(row__season=Season.FALL).aggregate(total=Sum("hours"))["total"] or 0)
    spring = int(queryset.filter(row__season=Season.SPRING).aggregate(total=Sum("hours"))["total"] or 0)
    profile = TeacherWorkloadProfile.objects.filter(
        organization=organization, teacher=teacher, academic_year=academic_year
    ).first()
    norm = int(profile.annual_norm_hours if profile else DEFAULT_ANNUAL_NORM_HOURS)
    return {
        "total_hours": total,
        "fall_hours": fall,
        "spring_hours": spring,
        "hourly_paid_hours": hourly,
        "norm_hours": norm,
        "fill_percent": int(round(total * 100 / norm)) if norm else 0,
        "is_over_norm": bool(norm and total > norm),
        "position": profile.position if profile else "",
        "staff_fraction": str(profile.staff_fraction) if profile else "",
    }


def teacher_workload_summaries(*, organization, teacher_ids, academic_year: str = "") -> dict:
    """``teacher_workload_summary``-nin TOPLU variantı — müəllim id → eyni formalı xülasə.

    Kafedra profili 72 müəllim üçün hər birinə 4 SUM + 1 profil sorğusu edirdi
    (288 + 72 sorğu — QA 2026-09-05 P2-3). Burada bütün cəmlər BİR GROUP BY ilə,
    profillər BİR sorğu ilə gəlir; müəllimsiz id-lər sıfır xülasə alır.
    """
    from django.db.models import Q

    ids = [tid for tid in teacher_ids if tid]
    if not ids:
        return {}
    queryset = TeacherAssignment.objects.filter(
        organization=organization,
        teacher_id__in=ids,
        row__task__status__in=(TaskStatus.DISTRIBUTED, TaskStatus.AMENDED),
    )
    if academic_year:
        queryset = queryset.filter(row__task__academic_year=academic_year)
    sums = {
        row["teacher_id"]: row
        for row in queryset.values("teacher_id").annotate(
            total=Sum("hours"),
            hourly=Sum("hours", filter=Q(is_hourly_paid=True)),
            fall=Sum("hours", filter=Q(row__season=Season.FALL)),
            spring=Sum("hours", filter=Q(row__season=Season.SPRING)),
        )
    }
    profiles = {
        profile.teacher_id: profile
        for profile in TeacherWorkloadProfile.objects.filter(
            organization=organization, teacher_id__in=ids, academic_year=academic_year
        )
    }
    out = {}
    for teacher_id in ids:
        row = sums.get(teacher_id, {})
        profile = profiles.get(teacher_id)
        total = int(row.get("total") or 0)
        norm = int(profile.annual_norm_hours if profile else DEFAULT_ANNUAL_NORM_HOURS)
        out[teacher_id] = {
            "total_hours": total,
            "fall_hours": int(row.get("fall") or 0),
            "spring_hours": int(row.get("spring") or 0),
            "hourly_paid_hours": int(row.get("hourly") or 0),
            "norm_hours": norm,
            "fill_percent": int(round(total * 100 / norm)) if norm else 0,
            "is_over_norm": bool(norm and total > norm),
            "position": profile.position if profile else "",
            "staff_fraction": str(profile.staff_fraction) if profile else "",
        }
    return out


def chair_tasks(*, organization, chair_ids, academic_year: str = ""):
    queryset = TeachingTask.objects.filter(organization=organization, chair_id__in=list(chair_ids))
    if academic_year:
        queryset = queryset.filter(academic_year=academic_year)
    return queryset.select_related("chair").order_by("chair__name")


__all__ = [
    "chair_tasks",
    "serialize_rows",
    "task_rows",
    "teacher_load_panel",
    "teacher_workload_rows",
    "teacher_workload_summaries",
    "teacher_workload_summary",
    "teacher_years",
]
