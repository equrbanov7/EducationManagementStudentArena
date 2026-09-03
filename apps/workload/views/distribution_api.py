"""«Yük bölgüsü» bölməsinin JSON endpoint-ləri (kafedra müdiri / RİM).

Hamısı FAIL-CLOSED: icazə/əhatə pozuntusu ``WorkloadDenied`` ilə 403 qaytarır,
heç bir data sızmır. Yazma endpoint-ləri POST + CSRF tələb edir.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from ..constants import TaskStatus
from ..models import TeacherAssignment, TeachingTask, TeachingTaskRow
from ..public import STATUS_LABELS
from ..services import (
    WorkloadDenied,
    assign_teacher,
    confirm_distribution,
    curriculum_row_suggestions,
    delete_row,
    distribution_readiness,
    ensure_can_manage,
    ensure_can_view,
    find_task,
    get_or_create_task,
    manageable_chairs,
    open_amendment,
    resolve_chair,
    row_warnings,
    save_row,
    serialize_rows,
    teacher_load_panel,
    teacher_pool,
    unassign,
)
from ._base import active_organization, actor_for, denied, error, json_body, no_org


def _task_payload(task) -> dict:
    return {
        "id": str(task.pk),
        "status": task.status,
        "status_label": STATUS_LABELS.get(task.status, task.status),
        "revision": task.revision,
        "is_locked": task.is_locked,
        "is_editable": task.is_editable,
        "academic_year": task.academic_year,
        "chair_id": str(task.chair_id),
    }


def _resolve_task(request, actor, *, task_id=None, chair_id=None, year=""):
    organization = active_organization(request)
    if task_id:
        task = TeachingTask.objects.filter(organization=organization, pk=task_id).select_related("chair").first()
    else:
        task = find_task(organization=organization, chair_id=chair_id, academic_year=year) if chair_id else None
    if task is None:
        raise WorkloadDenied("workload.task_not_found", "Tapşırıq tapılmadı.")
    ensure_can_view(actor, task)
    return task


# ── OXU ─────────────────────────────────────────────────────────────────────


@never_cache
@login_required
@require_GET
def rows(request) -> JsonResponse:
    """Tapşırıq sətirləri + balans + müəllim yük paneli + hazırlıq xülasəsi."""
    organization = active_organization(request)
    if organization is None:
        return no_org()
    actor = actor_for(request)
    chair_id = request.GET.get("chair") or ""
    year = request.GET.get("year") or ""
    try:
        task = _resolve_task(request, actor, task_id=request.GET.get("task") or None, chair_id=chair_id, year=year)
    except WorkloadDenied as exc:
        if exc.code == "workload.task_not_found":
            return JsonResponse({"ok": True, "task": None, "rows": [], "teachers": [], "readiness": None})
        return denied(exc)
    return JsonResponse(
        {
            "ok": True,
            "task": _task_payload(task),
            "rows": serialize_rows(task, season=request.GET.get("season") or "", search=request.GET.get("q") or ""),
            "teachers": teacher_load_panel(task),
            "readiness": distribution_readiness(task),
        }
    )


@never_cache
@login_required
@require_GET
def teachers(request) -> JsonResponse:
    """Kafedranın müəllim hovuzu (axtarışlı) + hər birinin cari yükü."""
    organization = active_organization(request)
    if organization is None:
        return no_org()
    actor = actor_for(request)
    chair_id = request.GET.get("chair") or ""
    try:
        chair = resolve_chair(organization, chair_id)
        ensure_can_manage(actor, chair.pk)
    except WorkloadDenied as exc:
        return denied(exc)
    pool = teacher_pool(organization, chair, search=(request.GET.get("q") or "").strip())
    year = request.GET.get("year") or ""
    if year:
        loads = {}
        assignments = TeacherAssignment.objects.filter(
            organization=organization,
            row__task__academic_year=year,
            teacher__isnull=False,
        ).values_list("teacher_id", "hours")
        for teacher_id, hours in assignments:
            loads[str(teacher_id)] = loads.get(str(teacher_id), 0) + int(hours or 0)
        for item in pool:
            item["current_hours"] = loads.get(item["id"], 0)
    return JsonResponse({"ok": True, "results": pool})


@never_cache
@login_required
@require_GET
def options(request) -> JsonResponse:
    """Sətir modalının açılış siyahıları: semestrlər, ixtisaslar, qruplar, fənlər."""
    from django.apps import apps as django_apps

    from core.constants import OrgUnitType

    organization = active_organization(request)
    if organization is None:
        return no_org()
    actor = actor_for(request)
    try:
        chair = resolve_chair(organization, request.GET.get("chair") or "")
        ensure_can_manage(actor, chair.pk)
    except WorkloadDenied as exc:
        return denied(exc)

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    Subject = django_apps.get_model("registrar", "Subject")

    specialties = list(
        OrgUnit.objects.filter(
            organization=organization,
            unit_type=OrgUnitType.SPECIALTY,
            is_active=True,
        ).values(
            "id", "name", "path"
        )[:500]
    )
    groups = list(
        OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.GROUP, is_active=True).values(
            "id", "name", "path"
        )[:2000]
    )
    periods = list(
        AcademicPeriod.objects.filter(organization=organization, is_active=True)
        .order_by("-start_date")
        .values("id", "name", "academic_year")[:40]
    )
    search = (request.GET.get("q") or "").strip()
    subjects = Subject.objects.filter(organization=organization, is_active=True)
    if search:
        subjects = subjects.filter(name__icontains=search)
    return JsonResponse(
        {
            "ok": True,
            "specialties": [
                {"id": str(item["id"]), "name": item["name"], "path": item["path"]} for item in specialties
            ],
            "groups": [{"id": str(item["id"]), "name": item["name"], "path": item["path"]} for item in groups],
            "periods": [
                {
                    "id": str(item["id"]),
                    "name": item["name"],
                    "academic_year": item["academic_year"],
                    "label": f"{item['name']} · {item['academic_year']}",
                }
                for item in periods
            ],
            "subjects": [
                {"id": str(item["id"]), "code": item["code"], "name": item["name"]}
                for item in subjects.values("id", "code", "name")[:200]
            ],
        }
    )


@never_cache
@login_required
@require_GET
def curriculum(request) -> JsonResponse:
    """Tədris planından sətir təklifləri (deqradasiya ilə — bax servis docstring-i)."""
    organization = active_organization(request)
    if organization is None:
        return no_org()
    actor = actor_for(request)
    try:
        chair = resolve_chair(organization, request.GET.get("chair") or "")
        ensure_can_manage(actor, chair.pk)
    except WorkloadDenied as exc:
        return denied(exc)
    suggestions = curriculum_row_suggestions(organization=organization, chair=chair)
    return JsonResponse({"ok": True, "results": suggestions, "count": len(suggestions)})


# ── YAZMA ───────────────────────────────────────────────────────────────────


@never_cache
@login_required
@require_POST
def task(request) -> JsonResponse:
    """Kafedra + il üçün tapşırıq yaradır (varsa qaytarır)."""
    organization = active_organization(request)
    if organization is None:
        return no_org()
    payload = json_body(request)
    actor = actor_for(request)
    try:
        instance, created = get_or_create_task(
            organization=organization,
            chair_id=payload.get("chair") or "",
            academic_year=payload.get("year") or "",
            actor=actor,
            request=request,
        )
    except WorkloadDenied as exc:
        return denied(exc)
    return JsonResponse({"ok": True, "created": created, "task": _task_payload(instance)})


@never_cache
@login_required
@require_POST
def row_save(request) -> JsonResponse:
    organization = active_organization(request)
    if organization is None:
        return no_org()
    payload = json_body(request)
    actor = actor_for(request)
    try:
        instance = _resolve_task(request, actor, task_id=payload.get("task_id"))
        row = None
        if payload.get("row_id"):
            row = TeachingTaskRow.objects.filter(pk=payload["row_id"], task=instance).first()
            if row is None:
                return error("workload.row_not_found", "Sətir tapılmadı.", status=404)
        saved = save_row(task=instance, actor=actor, data=payload, row=row, request=request)
    except WorkloadDenied as exc:
        return denied(exc)
    return JsonResponse(
        {"ok": True, "row_id": str(saved.pk), "warnings": row_warnings(saved), "task": _task_payload(instance)}
    )


@never_cache
@login_required
@require_POST
def row_delete(request) -> JsonResponse:
    organization = active_organization(request)
    if organization is None:
        return no_org()
    payload = json_body(request)
    actor = actor_for(request)
    try:
        instance = _resolve_task(request, actor, task_id=payload.get("task_id"))
        row = TeachingTaskRow.objects.filter(pk=payload.get("row_id"), task=instance).first()
        if row is None:
            return error("workload.row_not_found", "Sətir tapılmadı.", status=404)
        delete_row(task=instance, row=row, actor=actor, request=request)
    except WorkloadDenied as exc:
        return denied(exc)
    return JsonResponse({"ok": True})


@never_cache
@login_required
@require_POST
def assign(request) -> JsonResponse:
    organization = active_organization(request)
    if organization is None:
        return no_org()
    payload = json_body(request)
    actor = actor_for(request)
    row = (
        TeachingTaskRow.objects.filter(organization=organization, pk=payload.get("row_id"))
        .select_related("task", "task__chair")
        .first()
    )
    if row is None:
        return error("workload.row_not_found", "Sətir tapılmadı.", status=404)
    assignment = None
    if payload.get("assignment_id"):
        assignment = TeacherAssignment.objects.filter(pk=payload["assignment_id"], row=row).first()
        if assignment is None:
            return error("workload.assignment_not_found", "Bölgü tapılmadı.", status=404)
    try:
        saved = assign_teacher(
            row=row,
            actor=actor,
            activity=payload.get("activity") or "",
            teacher_id=payload.get("teacher_id") or None,
            hours=payload.get("hours"),
            groups_note=payload.get("groups_note") or "",
            is_hourly_paid=str(payload.get("is_hourly_paid") or "").lower() in ("1", "true", "on", "yes"),
            note=payload.get("note") or "",
            assignment=assignment,
            request=request,
        )
    except WorkloadDenied as exc:
        return denied(exc)
    return JsonResponse({"ok": True, "assignment_id": str(saved.pk)})


@never_cache
@login_required
@require_POST
def unassign_view(request) -> JsonResponse:
    organization = active_organization(request)
    if organization is None:
        return no_org()
    payload = json_body(request)
    actor = actor_for(request)
    assignment = (
        TeacherAssignment.objects.filter(organization=organization, pk=payload.get("assignment_id"))
        .select_related("row", "row__task", "row__task__chair")
        .first()
    )
    if assignment is None:
        return error("workload.assignment_not_found", "Bölgü tapılmadı.", status=404)
    try:
        unassign(assignment=assignment, actor=actor, request=request)
    except WorkloadDenied as exc:
        return denied(exc)
    return JsonResponse({"ok": True})


@never_cache
@login_required
@require_POST
def confirm(request) -> JsonResponse:
    organization = active_organization(request)
    if organization is None:
        return no_org()
    payload = json_body(request)
    actor = actor_for(request)
    try:
        instance = _resolve_task(request, actor, task_id=payload.get("task_id"))
        result = confirm_distribution(
            task=instance,
            actor=actor,
            allow_vacant=str(payload.get("allow_vacant") or "1").lower() not in ("0", "false", "no"),
            request=request,
        )
    except WorkloadDenied as exc:
        return denied(exc)
    return JsonResponse(
        {
            "ok": True,
            "status": result["status"],
            "status_label": STATUS_LABELS.get(result["status"], result["status"]),
            "sync": {key: value for key, value in result["sync"].items() if key != "offering_ids"},
            "notified": result["notified"],
        }
    )


@never_cache
@login_required
@require_POST
def amend(request) -> JsonResponse:
    organization = active_organization(request)
    if organization is None:
        return no_org()
    payload = json_body(request)
    actor = actor_for(request)
    try:
        instance = _resolve_task(request, actor, task_id=payload.get("task_id"))
        amendment = open_amendment(
            task=instance,
            actor=actor,
            target_kind=payload.get("target_kind") or "",
            target_id=payload.get("target_id") or "",
            reason=payload.get("reason") or "",
            note=payload.get("note") or "",
            document=request.FILES.get("document") if hasattr(request, "FILES") else None,
            new_values=payload.get("new_values") if isinstance(payload.get("new_values"), dict) else None,
            request=request,
        )
    except WorkloadDenied as exc:
        return denied(exc)
    return JsonResponse(
        {
            "ok": True,
            "amendment_id": str(amendment.pk),
            "status": TaskStatus.AMENDED.value,
            "status_label": STATUS_LABELS.get(TaskStatus.AMENDED.value, ""),
        }
    )


@never_cache
@login_required
@require_GET
def chairs(request) -> JsonResponse:
    """Aktorun əhatəsindəki kafedralar (RİM/rektorluq üçün seçici)."""
    organization = active_organization(request)
    if organization is None:
        return no_org()
    actor = actor_for(request)
    units = manageable_chairs(actor)
    return JsonResponse({"ok": True, "results": [{"id": str(unit.pk), "name": unit.name} for unit in units]})


__all__ = [
    "amend",
    "assign",
    "chairs",
    "confirm",
    "curriculum",
    "options",
    "row_delete",
    "row_save",
    "rows",
    "task",
    "teachers",
    "unassign_view",
]
