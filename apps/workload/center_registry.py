"""Ekran 12 «Dərs yükü mərkəzi» — OXU qatı (tədris şöbəsi).

Beş görünüş (dizayn `state.view`): `dashboard` · `tasks` · `import` ·
`reports` · `settings`. Sonuncu ikisi QƏSDƏN boş vəziyyətdədir (handoff onları
belə saxlayır) — «Bu bölmədə hələ məlumat yoxdur».

`tasks` görünüşünün iki daxili tabı var (`state.tab`): `editor` (sətir-sətir
tapşırıq cədvəli) və `tracking` (fakültə dilimlərinin izlənməsi).

FİLTR SEMANTİKASI (§8/14): `applied` = URL sorğu parametrləri; draft dəyər
sorğu göndərmir. Sıralama/səhifələmə serverdədir.

ARXİV (§6.3): keçmiş tədris ili YALNIZ OXUNUŞ — yazma düymələri render
olunmur və servis qatı da onu bloklayır (``is_archive_year``).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db.models import Count, Q, Sum

from .constants import PERM_MANAGE, PERM_SUBMIT, Season, TaskStatus
from .models import TaskFacultySlice, TeachingTask, TeachingTaskRow
from .services import (
    manageable_chairs,
    normalize_academic_year,
    resolve_actor,
    slice_progress,
    submit_summary,
)

VIEWS = ("dashboard", "tasks", "import", "reports", "settings")
TABS = ("editor", "tracking")
PAGE_SIZE = 25


def current_academic_year(organization) -> str:
    """Cari tədris ili — TƏK MƏNBƏ: akademik dövr.

    Sıra: (1) `is_current` dövr, (2) ən son başlayan dövr, (3) ən son tapşırıq ili.

    QA 2026-09-05 (UX-09): əvvəl `is_current` yoxdursa dərhal ən son TAPŞIRIQ
    ilinə keçirdi — nəticədə dashboard «2025/2026 Yaz», dərs yükü isə
    «2026/2027» göstərirdi. Dövr cədvəli hər iki səthin ortaq mənbəyidir, ona
    görə tapşırıq ili yalnız ƏN SON ehtiyatdır.
    """
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    period = AcademicPeriod.objects.filter(organization=organization, is_current=True).first()
    if period is not None and period.academic_year:
        return period.academic_year
    latest_period = (
        AcademicPeriod.objects.filter(organization=organization)
        .exclude(academic_year="")
        .order_by("-start_date")
        .values_list("academic_year", flat=True)
        .first()
    )
    if latest_period:
        return latest_period
    latest = (
        TeachingTask.objects.filter(organization=organization)
        .order_by("-academic_year")
        .values_list("academic_year", flat=True)
        .first()
    )
    return latest or ""


def known_years(organization) -> list[str]:
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    years = set(
        TeachingTask.objects.filter(organization=organization).values_list("academic_year", flat=True).distinct()
    )
    years |= set(
        AcademicPeriod.objects.filter(organization=organization).values_list("academic_year", flat=True).distinct()
    )
    return sorted({year for year in years if year}, reverse=True)


def is_archive_year(organization, year: str) -> bool:
    """Keçmiş il = arxiv (yalnız oxunuş). Cari il boşdursa arxiv sayılmır."""
    current = current_academic_year(organization)
    if not current or not year:
        return False
    return year < current


def safe_uuid(value) -> str:
    """URL-dən gələn id — UUID deyilsə BOŞ sətir (sorğu 500 vermir)."""
    import uuid as _uuid

    try:
        return str(_uuid.UUID(str(value or "").strip()))
    except (TypeError, ValueError):
        return ""


def _faculty_of(unit, faculty_paths):
    path = unit.path or ""
    for faculty_path, faculty in faculty_paths:
        if path.startswith(f"{faculty_path}/"):
            return faculty
    return None


def build_center(request, organization) -> dict:
    """«Dərs yükü mərkəzi» konteksti (yalnız oxu; mutasiyalar `actions.py`-da)."""
    from core.constants import OrgUnitType

    actor = resolve_actor(request.user, organization, request=request)
    if not actor.has(PERM_MANAGE):
        return {"has_access": False}

    params = request.GET
    view = params.get("wc_view") or "dashboard"
    if view not in VIEWS:
        view = "dashboard"
    tab = params.get("wc_tab") or "editor"
    if tab not in TABS:
        tab = "editor"

    years = known_years(organization)
    year = normalize_academic_year(params.get("wc_year") or "") or current_academic_year(organization)
    if year and year not in years:
        years = sorted(set(years) | {year}, reverse=True)

    chairs = list(manageable_chairs(actor).only("id", "name", "path"))
    chair_ids = [chair.pk for chair in chairs]
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    faculties = list(
        OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.FACULTY, is_active=True).only(
            "id", "name", "path"
        )
    )
    faculty_paths = sorted(
        ((faculty.path or "", faculty) for faculty in faculties), key=lambda item: len(item[0]), reverse=True
    )

    tasks = {
        task.chair_id: task
        for task in TeachingTask.objects.filter(
            organization=organization, academic_year=year, chair_id__in=chair_ids
        ).only("id", "chair_id", "status", "revision", "submitted_at", "updated_at")
    }
    hours = {
        item["task_id"]: item
        for item in TeachingTaskRow.objects.filter(task_id__in=[task.pk for task in tasks.values()])
        .values("task_id")
        .annotate(
            total=Sum("total_hours"),
            fall=Sum("total_hours", filter=Q(season=Season.FALL)),
            spring=Sum("total_hours", filter=Q(season=Season.SPRING)),
            credits=Sum("credits_value"),
            rows=Count("id"),
        )
    }

    faculty_filter = safe_uuid(params.get("wc_faculty"))
    status_filter = params.get("wc_status") or ""
    cards = []
    for chair in chairs:
        task = tasks.get(chair.pk)
        stats = hours.get(getattr(task, "pk", None), {})
        faculty = _faculty_of(chair, faculty_paths)
        card = {
            "chair_id": str(chair.pk),
            "name": chair.name,
            "faculty_id": str(faculty.pk) if faculty else "",
            "faculty_name": faculty.name if faculty else "",
            "task_id": str(task.pk) if task else "",
            "status": task.status if task else "",
            "revision": task.revision if task else 0,
            "total_hours": int(stats.get("total") or 0),
            "fall_hours": int(stats.get("fall") or 0),
            "spring_hours": int(stats.get("spring") or 0),
            "credits": int(stats.get("credits") or 0),
            "row_count": int(stats.get("rows") or 0),
            "updated_at": task.updated_at if task else None,
        }
        if faculty_filter and card["faculty_id"] != faculty_filter:
            continue
        if status_filter and card["status"] != status_filter:
            continue
        cards.append(card)
    cards.sort(key=lambda item: (item["faculty_name"], item["name"]))

    payload = {
        "has_access": True,
        "can_submit": actor.has(PERM_SUBMIT),
        "view": view,
        "tab": tab,
        "year": year,
        "years": years,
        "is_archive": is_archive_year(organization, year),
        "cards": cards,
        "faculty_options": [{"value": str(unit.pk), "label": unit.name} for unit in faculties],
        "filters": {"faculty": faculty_filter, "status": status_filter},
        "kpi": {
            "chairs": len(cards),
            "submitted": sum(1 for card in cards if card["status"] == TaskStatus.SUBMITTED),
            "approved": sum(
                1
                for card in cards
                if card["status"] in (TaskStatus.APPROVED, TaskStatus.DISTRIBUTING, TaskStatus.DISTRIBUTED)
            ),
            "returned": sum(1 for card in cards if card["status"] == TaskStatus.RETURNED),
        },
    }
    payload.update(_task_view(request, organization, actor, payload))
    payload["import_preview"] = _import_preview(request, organization) if view == "import" else None
    return payload


def _import_preview(request, organization) -> dict | None:
    """Sessiyadakı idxal önizləməsi (addım 2) — YAZMA YOXDUR.

    Önizləmə `actions.workload_action` tərəfindən sessiyaya yazılır; burada
    yalnız oxunur və kataloq uyğunluğu YENİDƏN hesablanır (kataloq arada
    dəyişsə önizləmə köhnəlmiş qalmasın).
    """
    from .actions import IMPORT_SESSION_KEY
    from .services import build_mapping

    stored = request.session.get(IMPORT_SESSION_KEY) or {}
    records = stored.get("records") or []
    if not records:
        return None
    preview = build_mapping(organization=organization, records=records)
    preview["file_name"] = stored.get("file_name", "")
    return preview


def _task_view(request, organization, actor, payload) -> dict:
    """`tasks` görünüşü — sətir cədvəli + izləmə paneli (seçilmiş kafedra)."""
    params = request.GET
    chair_id = safe_uuid(params.get("wc_chair"))
    if not chair_id and payload["cards"]:
        chair_id = payload["cards"][0]["chair_id"]
    task = None
    if chair_id:
        task = (
            TeachingTask.objects.filter(organization=organization, chair_id=chair_id, academic_year=payload["year"])
            .select_related("chair")
            .first()
        )

    result = {
        "chair_id": chair_id,
        "chair_options": [{"value": card["chair_id"], "label": card["name"]} for card in payload["cards"]],
        "task": None,
        "rows": [],
        "row_total": 0,
        "page": 1,
        "page_count": 1,
        "totals": {"fall": 0, "spring": 0, "total": 0, "credits": 0},
        "slices": [],
        "slice_progress": {"total": 0, "approved": 0, "returned": 0, "pending": 0},
        "returned_rows": [],
        "submit_summary": None,
        "row_filters": {"season": "", "specialty": "", "form": ""},
        "specialty_options": [],
        "program_options": [],
        "plan_preview": None,
    }
    if task is None:
        return result

    result["task"] = {
        "id": str(task.pk),
        "status": task.status,
        "revision": task.revision,
        "chair_name": task.chair.name,
        "is_office_editable": task.status in (TaskStatus.DRAFT, TaskStatus.RETURNED),
        "submitted_at": task.submitted_at,
    }

    queryset = (
        TeachingTaskRow.objects.filter(task=task)
        .select_related("subject", "specialty", "faculty", "period")
        .prefetch_related("groups")
        .order_by("season", "order", "created_at")
    )
    season = params.get("wc_sem") or ""
    specialty = safe_uuid(params.get("wc_spec"))
    form = params.get("wc_form") or ""
    if season:
        queryset = queryset.filter(season=season)
    if specialty:
        queryset = queryset.filter(specialty_id=specialty)
    if form:
        queryset = queryset.filter(education_form=form)

    totals = TeachingTaskRow.objects.filter(task=task).aggregate(
        total=Sum("total_hours"),
        fall=Sum("total_hours", filter=Q(season=Season.FALL)),
        spring=Sum("total_hours", filter=Q(season=Season.SPRING)),
        credits=Sum("credits_value"),
    )
    result["totals"] = {
        "total": int(totals["total"] or 0),
        "fall": int(totals["fall"] or 0),
        "spring": int(totals["spring"] or 0),
        "credits": int(totals["credits"] or 0),
    }

    row_total = queryset.count()
    try:
        page = max(int(params.get("wc_page") or 1), 1)
    except (TypeError, ValueError):
        page = 1
    page_count = max((row_total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    page = min(page, page_count)
    offset = (page - 1) * PAGE_SIZE
    rows = list(queryset[offset : offset + PAGE_SIZE])

    result["rows"] = [_serialize_row(row) for row in rows]
    result["row_total"] = row_total
    result["page"] = page
    result["page_count"] = page_count
    # ⚠️ AÇAR ADI «filters» OLA BİLMƏZ — dashboard filtrlərini əzərdi.
    result["row_filters"] = {"season": season, "specialty": specialty, "form": form}

    slices = list(
        TaskFacultySlice.objects.filter(task=task, revision=task.revision)
        .select_related("faculty", "decided_by")
        .order_by("faculty__name")
    )
    review_counts = _review_counts_by_faculty(task)
    result["slices"] = [
        {
            "id": str(item.pk),
            "faculty": item.faculty.name,
            "status": item.status,
            # `workload_line` ailəsi üç pill saxlayır: pending → «sent».
            "status_key": "sent" if item.status == "pending" else item.status,
            "comment": item.comment,
            "decided_at": item.decided_at,
            "decided_by": ((item.decided_by.get_full_name() or item.decided_by.username) if item.decided_by_id else ""),
            "visa": review_counts.get(item.faculty_id, {"reviewed": 0, "total": 0}),
        }
        for item in slices
    ]
    result["slice_progress"] = slice_progress(task)
    result["returned_rows"] = [
        _serialize_row(row)
        for row in TeachingTaskRow.objects.filter(task=task, review_status="returned").select_related(
            "subject", "specialty"
        )[:50]
    ]
    if task.status in (TaskStatus.DRAFT, TaskStatus.RETURNED):
        from .services import plan_preview

        preview = plan_preview(organization=organization, chair=task.chair, academic_year=payload["year"])
        result["plan_preview"] = preview
        result["program_options"] = [
            {"value": item["id"], "label": item["name"], "has_plan": item["has_plan"]} for item in preview["programs"]
        ]
        if actor.has(PERM_SUBMIT):
            result["submit_summary"] = submit_summary(task)

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    specialty_ids = (
        TeachingTaskRow.objects.filter(task=task, specialty__isnull=False)
        .values_list("specialty_id", flat=True)
        .distinct()
    )
    result["specialty_options"] = [
        {"value": str(unit.pk), "label": unit.name}
        for unit in OrgUnit.objects.filter(pk__in=list(specialty_ids)).order_by("name")
    ]
    return result


def _review_counts_by_faculty(task) -> dict:
    rows = (
        TeachingTaskRow.objects.filter(task=task, faculty__isnull=False)
        .values("faculty_id")
        .annotate(
            total=Count("id"),
            reviewed=Count("id", filter=Q(review_status__in=("reviewed", "flagged"))),
            flagged=Count("id", filter=Q(review_status="flagged")),
        )
    )
    return {
        item["faculty_id"]: {
            "total": int(item["total"] or 0),
            "reviewed": int(item["reviewed"] or 0),
            "flagged": int(item["flagged"] or 0),
        }
        for item in rows
    }


def _serialize_row(row) -> dict:
    return {
        "id": str(row.pk),
        "season": row.season,
        "season_label": str(Season(row.season).label) if row.season in Season.values else row.season,
        "groups": row.groups_text or ", ".join(unit.name for unit in row.groups.all()),
        "subject": row.subject_label,
        "specialty": row.specialty.name if row.specialty_id else row.specialty_text,
        "education_form": row.education_form,
        "degree_level": row.degree_level,
        "students": row.student_count,
        "union_count": row.union_count,
        "subgroup_count": row.subgroup_count,
        "lecture_plan": row.lecture_plan,
        "lecture_total": row.lecture_total,
        "seminar_plan": row.seminar_plan,
        "seminar_total": row.seminar_total,
        "lab_plan": row.lab_plan,
        "lab_total": row.lab_total,
        "consult_hours": row.consult_hours,
        "exam_hours": row.exam_hours,
        "thesis_hours": row.thesis_hours,
        "postgrad_hours": row.postgrad_hours,
        "practice_hours": row.practice_research_hours + row.practice_production_hours,
        "total_hours": row.total_hours,
        "credits": row.credits or (str(row.credits_value) if row.credits_value else ""),
        "review_status": row.review_status,
    }


__all__ = [
    "PAGE_SIZE",
    "safe_uuid",
    "TABS",
    "VIEWS",
    "build_center",
    "current_academic_year",
    "is_archive_year",
    "known_years",
]
