"""Oxu sorğuları: bölgü cədvəli, müəllim yük paneli, «Dərs yüküm» sətirləri."""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum

from core.search_text import tolerant_q

from ..constants import (
    Activity,
    RowKind,
    Season,
    TaskStatus,
)
from ..models import TeacherAssignment, TeacherWorkloadProfile, TeachingTask, TeachingTaskRow
from .assignments import balance_for_rows
from .norms import norm_hours_for, norms_for
from .row_filters import apply_row_filters

# ⚠️ Etiketlər LAZY qalır (import anında `str()` dili dondururdu — QA-1 F3); mətnə çevirmə çağırış anındadır.
_ACTIVITY_LABELS = {str(value): label for value, label in Activity.choices}
_SEASON_LABELS = {str(value): label for value, label in Season.choices}


def _visible_q() -> Q:
    """Müəllimə görünən bölgü: təsdiqlənmiş sənəd VƏ ya intensiv kurs (o, zəncirdən keçmir — 2026-10-25)."""
    return Q(row__task__status__in=(TaskStatus.DISTRIBUTED, TaskStatus.AMENDED)) | Q(row__row_kind=RowKind.INTENSIVE)


def _label(labels: dict, value: str) -> str:
    """Seçim etiketi AKTİV dildə (çağırış anında); naməlum dəyər — olduğu kimi."""
    label = labels.get(value)
    return str(label) if label is not None else value


#: «Vakant» kartı (sağ panel) üçün süzgəc açarı — müəllimi olmayan bölgü sətirləri.
VACANT_FILTER = "vacant"
#: Səhifələmənin üst həddi (``rows`` endpoint-i): bir cavab bundan çox sətir daşımır.
MAX_PAGE_LIMIT = 300


def _teacher_row_ids(task, teacher: str):
    """Sağ paneldə seçilmiş müəllimin (və ya «Vakant»ın) bölgüsü olan sətir id-ləri (alt sorğu, JOIN-suz)."""
    assignments = TeacherAssignment.objects.filter(row__task=task)
    if teacher == VACANT_FILTER:
        return assignments.filter(teacher__isnull=True).values("row_id")
    try:
        teacher_pk = TeacherAssignment._meta.get_field("teacher").related_model._meta.pk.to_python(teacher)
    except (ValidationError, ValueError, TypeError):
        return assignments.none().values("row_id")
    return assignments.filter(teacher_id=teacher_pk).values("row_id")


def task_rows(task, *, season: str = "", search: str = "", teacher: str = "", status: str = "", activity: str = ""):
    queryset = (
        TeachingTaskRow.objects.filter(task=task)
        .select_related("subject", "specialty", "period", "intensive_offering")
        .prefetch_related("groups", "assignments__teacher")
        # `pk` — səhifələmə sabit olsun (eyni `order` dəyəri olan sətirlər yerini dəyişməsin).
        .order_by("season", "order", "created_at", "pk")
    )
    if season:
        queryset = queryset.filter(season=season)
    if teacher:
        queryset = queryset.filter(pk__in=_teacher_row_ids(task, teacher))
    # 2026-10-25: bölgü vəziyyəti (vakantlı / tam / qismən …) və fəaliyyət növü — `row_filters` (server tərəfi).
    queryset = apply_row_filters(queryset, task, status=status, activity=activity)
    # Sahib 2026-10-23: «müəllimə görə də axtarmaq lazımdır» — fənn / qrup / müəllim (ad, soyad, istifadəçi adı).
    search_q = tolerant_q(
        search,
        (
            "subject__name",
            "subject_text",
            "assignments__teacher__first_name",
            "assignments__teacher__last_name",
            "assignments__teacher__username",
        ),
        compact_fields=("subject__code", "groups_text"),
    )
    if search_q is not None:
        queryset = queryset.filter(search_q).distinct()
    return queryset


#: Sətir redaktə modalının saat sahələri (2026-10-15: modal əvvəl bunları DOLDURMURDU — «Redaktə»
#: saatları 0, qrupları/ixtisası boş göndərirdi).
_ROW_HOUR_FIELDS = (
    "lecture_plan",
    "lecture_total",
    "seminar_plan",
    "seminar_total",
    "lab_plan",
    "lab_total",
    "consult_hours",
    "exam_hours",
    "thesis_hours",
    "postgrad_hours",
    "practice_research_hours",
    "practice_production_hours",
    "credits_value",
)


def _intensive_payload(row) -> dict | None:
    """İntensiv kurs sətrinin kartı: tarixlər, səbəb, tələbə sayı, jurnal keçidi."""
    offering = row.intensive_offering if row.row_kind == RowKind.INTENSIVE else None
    if offering is None:
        return None
    from django.urls import reverse

    return {
        "offering_id": str(offering.pk),
        "starts_on": f"{offering.starts_on:%d.%m.%Y}" if offering.starts_on else "",
        "ends_on": f"{offering.ends_on:%d.%m.%Y}" if offering.ends_on else "",
        "note": offering.format_note,
        "students": row.student_count,
        "is_active": offering.is_active,
        "journal_url": reverse("registrar:journal_detail", args=[offering.pk]),
    }


def serialize_rows(task, *, season: str = "", search: str = "") -> list[dict]:
    return serialize_rows_state(task, season=season, search=search)[0]


def serialize_rows_state(task, *, season: str = "", search: str = "") -> tuple[list[dict], list, dict]:
    """``serialize_rows`` + yüklənmiş sətirlər və balans (PERF-1 F-09).

    `rows` endpoint-i hazırlıq xülasəsini (``distribution_readiness``) eyni sorğunun sətirləri ilə qurur —
    süzgəcsiz görünüşdə sətirlər, qruplar və balans ikinci dəfə oxunmur.
    """
    return _serialize(task, list(task_rows(task, season=season, search=search)))


def rows_page(
    task,
    *,
    season: str = "",
    search: str = "",
    teacher: str = "",
    status: str = "",
    activity: str = "",
    offset: int = 0,
    limit: int = 0,
    focus_row=None,
) -> dict:
    """Tənbəl yükləmə (2026-10-25): süzgəcə uyğun sətirlərin ``offset`` / ``limit`` dilimi + cəmi say.

    Sorğu sayı sətir sayından asılı deyil (dilim + qruplar + təyinatlar prefetch, balans BİR GROUP BY).
    ``limit=0`` — sətir oxunmur (yalnız say). ``focus_row`` (ilk dilim) — «Redaktə et» keçidinin sətri dilimdən
    kənardadırsa, dilim ona qədər genişləndirilir ki, JS ona sürüşə bilsin.
    """
    queryset = task_rows(task, season=season, search=search, teacher=teacher, status=status, activity=activity)
    total = queryset.count()
    offset = max(int(offset or 0), 0)
    limit = min(max(int(limit or 0), 0), MAX_PAGE_LIMIT)
    if focus_row and limit and offset == 0:
        position = next((i for i, pk in enumerate(queryset.values_list("pk", flat=True)) if pk == focus_row), None)
        if position is not None:
            limit = min(max(limit, position + 1), MAX_PAGE_LIMIT)
    rows = list(queryset[offset : offset + limit]) if limit else []
    payload, _rows, _balance = _serialize(task, rows)
    next_offset = offset + len(rows)
    return {"rows": payload, "total": total, "next_offset": next_offset, "has_more": next_offset < total}


def _serialize(task, rows: list) -> tuple[list[dict], list, dict]:
    from .tasks import _amendment_target_row_ids

    balance = balance_for_rows(rows)
    amend_targets = _amendment_target_row_ids(task) if task.status == TaskStatus.AMENDED else set()
    payload = []
    for row in rows:
        info = balance.get(str(row.pk), {})
        payload.append(
            {
                "id": str(row.pk),
                "hours": {field: int(getattr(row, field, 0) or 0) for field in _ROW_HOUR_FIELDS},
                "specialty_id": str(row.specialty_id) if row.specialty_id else "",
                "is_amend_target": row.pk in amend_targets,
                "season": row.season,
                "season_label": _label(_SEASON_LABELS, row.season),
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
                "intensive": _intensive_payload(row),
                "activities": info.get("activities", {}),
                "teaching_complete": info.get("teaching_complete", True),
                "assignments": [
                    {
                        "id": str(assignment.pk),
                        "activity": assignment.activity,
                        "activity_label": _label(_ACTIVITY_LABELS, assignment.activity),
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
    return payload, rows, balance


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

    # Norma — «Sistem tənzimləmələri» qaydası (``services.norms``), bütün kartlar üçün bir dəfə.
    norms = norms_for(task.organization, [key for key in buckets if key], profiles)
    cards = []
    for key, bucket in buckets.items():
        norm = norms.get(key, 0) if key else 0
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
        )
        .filter(_visible_q())
        .select_related("row", "row__subject", "row__task", "row__task__chair", "row__period", "row__specialty")
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
        group_ids = [group.pk for group in row.groups.all()] or [None]
        offering_id = str(row.intensive_offering_id or "") or next(
            (
                offering_map[key]
                for key in ((row.subject_id, row.period_id, gid) for gid in group_ids)
                if key in offering_map
            ),
            "",
        )
        rows.append(
            {
                "id": str(assignment.pk),
                # 2026-10-15: «Mənim dərs yüküm» fənn + qrup (tapşırıq sətri) üzrə birləşir və redaktə keçidi
                # kafedraya görə qurulur (``services.my_workload_lines``).
                "row_id": str(row.pk),
                "task_id": str(row.task_id),
                "chair_id": str(row.task.chair_id),
                # Sahib 2026-10-25: yük bütün kafedralardan gəlir (ştat bir kafedrada, saathesabı başqasında) —
                # hər sətirdə yükü verən kafedra yazılır.
                "chair_name": row.task.chair.name if row.task.chair_id else "",
                "academic_year": row.task.academic_year,
                "season": row.season,
                "season_label": _label(_SEASON_LABELS, row.season),
                "subject": row.subject_label,
                "groups": row.groups_text or ", ".join(group.name for group in row.groups.all()),
                "activity": assignment.activity,
                "activity_label": _label(_ACTIVITY_LABELS, assignment.activity),
                "hours": assignment.hours,
                "education_form": row.education_form,
                "degree_level": row.degree_level,
                "is_hourly_paid": assignment.is_hourly_paid,
                "groups_note": assignment.groups_note,
                "offering_id": offering_id,
                "is_intensive": row.row_kind == RowKind.INTENSIVE,
            }
        )
    return rows


def _offering_links(organization, assignments) -> dict:
    """(subject_id, period_id, group_id) → offering id — jurnal keçidi üçün.

    2026-10-15: açar əvvəl (fənn, semestr) idi — eyni fənnin «631/5K» və «631/5K ing» sətirləri EYNİ
    (təsadüfi) qrupun jurnalına aparırdı. İndi sətrin öz qrupunun açılışıdır; ``group_id=None`` —
    qrupsuz açılış (qrupsuz sətir üçün köhnə davranış).
    """
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
        CourseOffering.objects.filter(organization=organization)
        .filter(lookup)
        .exclude(course_format="intensive")  # intensiv jurnal öz sətrinə bağlıdır (intensive_offering)
        .values("id", "subject_id", "period_id", "group_id")
    )
    return {(row["subject_id"], row["period_id"], row["group_id"]): str(row["id"]) for row in rows}


def teacher_workload_summary(*, organization, teacher, academic_year: str = "", season: str = "") -> dict:
    """İllik KPI-lar + ``rows_total_hours`` — ``teacher_workload_rows(season=…)`` ilə EYNİ süzgəcin cəmi.

    2026-10-08 (müəllim rəyi W1): cədvəlin altındakı «CƏMİ» xanası semestr tabından
    asılı olmayaraq İLLİK cəmi (``total_hours``) göstərirdi — «Payız» tabında 300 saatlıq
    sətirlərin altında 630 yazılırdı. İndi xana ``rows_total_hours``-dur (görünən
    sətirlərin cəmi); «İllik cəmi» KPI-ı illik olaraq qalır.
    """
    queryset = TeacherAssignment.objects.filter(
        organization=organization,
        teacher=teacher,
    ).filter(_visible_q())
    if academic_year:
        queryset = queryset.filter(row__task__academic_year=academic_year)
    by_season = {
        item["row__season"]: int(item["total"] or 0)
        for item in queryset.values("row__season").annotate(total=Sum("hours")).order_by()
    }
    total = sum(by_season.values())
    hourly = int(queryset.filter(is_hourly_paid=True).aggregate(total=Sum("hours"))["total"] or 0)
    fall = by_season.get(Season.FALL, 0)
    spring = by_season.get(Season.SPRING, 0)
    profile = TeacherWorkloadProfile.objects.filter(
        organization=organization, teacher=teacher, academic_year=academic_year
    ).first()
    norm = norm_hours_for(organization, getattr(teacher, "pk", None), profile)
    return {
        "total_hours": total,
        "fall_hours": fall,
        "spring_hours": spring,
        "summer_hours": by_season.get(Season.SUMMER, 0),
        "season": season,
        "rows_total_hours": by_season.get(season, 0) if season else total,
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
    ).filter(_visible_q())
    if academic_year:
        queryset = queryset.filter(row__task__academic_year=academic_year)
    # Kafedra üzrə də bölünür (sahib 2026-10-25: ştat bir kafedrada, saathesabı başqasında) — eyni BİR sorğu.
    sums: dict = {}
    by_chair: dict = {}
    for row in (
        queryset.values("teacher_id", "row__task__chair_id")
        .annotate(
            total=Sum("hours"),
            hourly=Sum("hours", filter=Q(is_hourly_paid=True)),
            fall=Sum("hours", filter=Q(row__season=Season.FALL)),
            spring=Sum("hours", filter=Q(row__season=Season.SPRING)),
        )
        .order_by()
    ):
        bucket = sums.setdefault(row["teacher_id"], {"total": 0, "hourly": 0, "fall": 0, "spring": 0})
        for key in bucket:
            bucket[key] += int(row[key] or 0)
        chair_hours = by_chair.setdefault(row["teacher_id"], {})
        chair_key = str(row["row__task__chair_id"])
        chair_hours[chair_key] = chair_hours.get(chair_key, 0) + int(row["total"] or 0)
    profiles = {
        profile.teacher_id: profile
        for profile in TeacherWorkloadProfile.objects.filter(
            organization=organization, teacher_id__in=ids, academic_year=academic_year
        )
    }
    norms = norms_for(organization, ids, profiles)
    out = {}
    for teacher_id in ids:
        row = sums.get(teacher_id, {})
        profile = profiles.get(teacher_id)
        total = int(row.get("total") or 0)
        norm = norms[teacher_id]
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
            "hours_by_chair": by_chair.get(teacher_id, {}),
        }
    return out


def chair_tasks(*, organization, chair_ids, academic_year: str = ""):
    queryset = TeachingTask.objects.filter(organization=organization, chair_id__in=list(chair_ids))
    if academic_year:
        queryset = queryset.filter(academic_year=academic_year)
    return queryset.select_related("chair").order_by("chair__name")


__all__ = [
    "MAX_PAGE_LIMIT",
    "VACANT_FILTER",
    "chair_tasks",
    "rows_page",
    "serialize_rows",
    "serialize_rows_state",
    "task_rows",
    "teacher_load_panel",
    "teacher_workload_rows",
    "teacher_workload_summaries",
    "teacher_workload_summary",
    "teacher_years",
]
