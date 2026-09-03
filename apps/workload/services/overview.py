"""Universitet üzrə aqreqasiya — ekran 17 «Rektor — Ümumi baxış».

⚠️ HANDOFF §8 QAYDA 13 — **AQREQASİYA YALNIZ AŞAĞIDAN YUXARI**:
``kafedra → fakültə → universitet``. Yekun rəqəmlər HEÇ BİR CƏDVƏLDƏ
SAXLANILMIR; hər sorğuda yenidən hesablanır. Denormalizasiya qadağandır —
əks halda üç səviyyə bir-birindən ayrılır.

SORĞU BÜDCƏSİ
-------------
Bütün ekran ~8 aqreqat sorğu ilə qurulur (kafedra sayı nə olursa olsun):

  1 kafedra siyahısı · 1 fakültə siyahısı · 1 tapşırıq statusu ·
  1 sətir saatı · 1 bölgü saatı (+vakant) · 1 müəllim sayı ·
  1 müəllim-saat cəmi · 1 norma profili

Testdə ölçülür (``test_stage4_sections.py``) — sətir-sətir dövr YOXDUR.

YÜK BANTLARI (``core.ui.status_catalog.LOAD_BAND``)
--------------------------------------------------
    < 90%  normadan az · 90–105% normada · 105–125% norma üstü · >125% kritik
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db.models import Count, Q, Sum

from core.constants import OrgUnitType

from ..constants import DEFAULT_ANNUAL_NORM_HOURS, PERM_REPORT, TaskStatus
from ..models import TeacherAssignment, TeacherWorkloadProfile, TeachingTask, TeachingTaskRow

#: Bölgüyə açıq sayılan (yəni «tapşırıq verilmiş») statuslar.
LIVE_STATUSES = (
    TaskStatus.SUBMITTED,
    TaskStatus.RETURNED,
    TaskStatus.PENDING_FINAL_APPROVAL,
    TaskStatus.APPROVED,
    TaskStatus.DISTRIBUTING,
    TaskStatus.DISTRIBUTED,
    TaskStatus.AMENDED,
)


def load_band(percent: int) -> str:
    if percent < 90:
        return "under"
    if percent <= 105:
        return "normal"
    if percent <= 125:
        return "over"
    return "critical"


def _visible_chairs(actor):
    """Rektorluq/RİM ORG-wide görür; fakültə-scope aktor öz alt-ağacını."""
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    if not actor.has(PERM_REPORT):
        return OrgUnit.objects.none()
    base = OrgUnit.objects.filter(
        organization=actor.organization,
        is_active=True,
        unit_type__in=(OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT),
    )
    scope = actor.scope_for(PERM_REPORT)
    if scope.is_org_wide:
        return base
    if not scope.has_structure_access:
        return OrgUnit.objects.none()
    return base.filter(scope.unit_subtree_q())


def _faculty_of(unit, faculty_paths) -> object:
    """Kafedranın fakültəsi — materialized ``path`` prefiksi ilə (sorğusuz)."""
    path = unit.path or ""
    for faculty_path, faculty in faculty_paths:
        if path.startswith(f"{faculty_path}/"):
            return faculty
    return None


def build_overview(*, actor, academic_year: str) -> dict:
    """Kafedra → fakültə → universitet aqreqasiyası (heç nə saxlanılmır)."""
    organization = actor.organization
    chairs = list(_visible_chairs(actor).only("id", "name", "path", "head_id").select_related("head"))
    if not chairs:
        return {
            "chairs": [],
            "faculties": [],
            "totals": _empty_totals(),
            "risky": [],
            "status_map": _status_map([]),
            "academic_year": academic_year,
        }

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    faculties = list(
        OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.FACULTY, is_active=True).only(
            "id", "name", "path"
        )
    )
    faculty_paths = sorted(
        ((faculty.path or "", faculty) for faculty in faculties), key=lambda item: len(item[0]), reverse=True
    )

    chair_ids = [chair.pk for chair in chairs]
    tasks = {
        task.chair_id: task
        for task in TeachingTask.objects.filter(
            organization=organization, academic_year=academic_year, chair_id__in=chair_ids
        ).only("id", "chair_id", "status", "revision")
    }
    task_ids = [task.pk for task in tasks.values()]

    planned = {
        item["task_id"]: int(item["planned_sum"] or 0)
        for item in TeachingTaskRow.objects.filter(task_id__in=task_ids)
        .values("task_id")
        .annotate(planned_sum=Sum("total_hours"))
    }
    # ⚠️ Alias adları sahə adları ilə TOQQUŞMAMALIDIR (`hours=Sum("hours")`
    # Django-da «'hours' is an aggregate» xətası verir).
    assigned_rows = (
        TeacherAssignment.objects.filter(row__task_id__in=task_ids)
        .values("row__task_id")
        .annotate(
            assigned_sum=Sum("hours"),
            vacant_sum=Sum("hours", filter=Q(teacher__isnull=True)),
            teacher_count=Count("teacher_id", distinct=True),
        )
    )
    assigned = {item["row__task_id"]: item for item in assigned_rows}

    teacher_totals = {
        (item["row__task__chair_id"], item["teacher_id"]): int(item["teacher_sum"] or 0)
        for item in TeacherAssignment.objects.filter(row__task_id__in=task_ids, teacher__isnull=False)
        .values("row__task__chair_id", "teacher_id")
        .annotate(teacher_sum=Sum("hours"))
    }
    norms = {
        profile.teacher_id: int(profile.annual_norm_hours or DEFAULT_ANNUAL_NORM_HOURS)
        for profile in TeacherWorkloadProfile.objects.filter(
            organization=organization, academic_year=academic_year
        ).only("teacher_id", "annual_norm_hours")
    }

    over_norm: dict = {}
    for (chair_id, teacher_id), hours in teacher_totals.items():
        norm = norms.get(teacher_id, DEFAULT_ANNUAL_NORM_HOURS)
        if norm and hours > norm:
            over_norm[chair_id] = over_norm.get(chair_id, 0) + 1

    chair_rows = []
    for chair in chairs:
        task = tasks.get(chair.pk)
        stats = assigned.get(getattr(task, "pk", None), {})
        planned_hours = planned.get(getattr(task, "pk", None), 0)
        assigned_hours = int(stats.get("assigned_sum") or 0)
        vacant_hours = int(stats.get("vacant_sum") or 0)
        teachers = int(stats.get("teacher_count") or 0)
        percent = int(round(assigned_hours * 100 / planned_hours)) if planned_hours else 0
        faculty = _faculty_of(chair, faculty_paths)
        chair_rows.append(
            {
                "id": str(chair.pk),
                "name": chair.name,
                "head": (chair.head.get_full_name() or chair.head.username) if chair.head_id else "",
                "faculty_id": str(faculty.pk) if faculty else "",
                "faculty_name": faculty.name if faculty else "",
                "status": task.status if task else "",
                "planned_hours": planned_hours,
                "assigned_hours": assigned_hours,
                "remaining_hours": max(planned_hours - assigned_hours, 0),
                "vacant_hours": vacant_hours,
                "teachers": teachers,
                "over_norm": over_norm.get(chair.pk, 0),
                "percent": percent,
                "band": load_band(percent),
            }
        )
    chair_rows.sort(key=lambda item: (item["faculty_name"], item["name"]))

    faculty_rows = _rollup(chair_rows)
    totals = _rollup_all(chair_rows)
    risky = [
        row
        for row in chair_rows
        if row["planned_hours"] and (row["percent"] < 90 or row["vacant_hours"] or row["over_norm"])
    ]
    risky.sort(key=lambda item: (-item["vacant_hours"], item["percent"]))

    return {
        "chairs": chair_rows,
        "faculties": faculty_rows,
        "totals": totals,
        "risky": risky[:10],
        "status_map": _status_map(chair_rows),
        "academic_year": academic_year,
    }


def _empty_totals() -> dict:
    return {
        "planned_hours": 0,
        "assigned_hours": 0,
        "vacant_hours": 0,
        "teachers": 0,
        "chairs": 0,
        "faculties": 0,
        "percent": 0,
        "band": "under",
        "over_norm": 0,
    }


def _rollup(chair_rows) -> list[dict]:
    """Fakültə səviyyəsi — KAFEDRA sətirlərinin cəmi (saxlanılmır)."""
    buckets: dict = {}
    for row in chair_rows:
        key = row["faculty_id"]
        bucket = buckets.setdefault(
            key,
            {
                "id": key,
                "name": row["faculty_name"] or "—",
                "chairs": 0,
                "planned_hours": 0,
                "assigned_hours": 0,
                "vacant_hours": 0,
                "teachers": 0,
                "over_norm": 0,
            },
        )
        bucket["chairs"] += 1
        for field in ("planned_hours", "assigned_hours", "vacant_hours", "teachers", "over_norm"):
            bucket[field] += row[field]
    result = []
    for bucket in buckets.values():
        percent = int(round(bucket["assigned_hours"] * 100 / bucket["planned_hours"])) if bucket["planned_hours"] else 0
        bucket["percent"] = percent
        bucket["band"] = load_band(percent)
        bucket["remaining_hours"] = max(bucket["planned_hours"] - bucket["assigned_hours"], 0)
        result.append(bucket)
    result.sort(key=lambda item: item["name"])
    return result


def _rollup_all(chair_rows) -> dict:
    """Universitet səviyyəsi — yenə AŞAĞIDAN YUXARI."""
    totals = _empty_totals()
    for row in chair_rows:
        for field in ("planned_hours", "assigned_hours", "vacant_hours", "teachers", "over_norm"):
            totals[field] += row[field]
        totals["chairs"] += 1
    totals["faculties"] = len({row["faculty_id"] for row in chair_rows if row["faculty_id"]})
    totals["percent"] = (
        int(round(totals["assigned_hours"] * 100 / totals["planned_hours"])) if totals["planned_hours"] else 0
    )
    totals["band"] = load_band(totals["percent"])
    totals["remaining_hours"] = max(totals["planned_hours"] - totals["assigned_hours"], 0)
    return totals


def _status_map(chair_rows) -> list[dict]:
    """Təsdiq axını vizualizasiyası — status → kafedra sayı."""
    order = [
        TaskStatus.DRAFT,
        TaskStatus.SUBMITTED,
        TaskStatus.RETURNED,
        TaskStatus.APPROVED,
        TaskStatus.DISTRIBUTING,
        TaskStatus.DISTRIBUTED,
    ]
    counts = {str(status): 0 for status in order}
    missing = 0
    for row in chair_rows:
        if not row["status"]:
            missing += 1
        elif row["status"] in counts:
            counts[row["status"]] += 1
    result = [{"key": key, "count": value} for key, value in counts.items()]
    result.append({"key": "none", "count": missing})
    return result


__all__ = ["LIVE_STATUSES", "build_overview", "load_band"]
