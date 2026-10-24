"""«Yük bölgüsü» bölməsinin JSON endpoint-ləri (kafedra müdiri / RİM).

Hamısı FAIL-CLOSED: icazə/əhatə pozuntusu ``WorkloadDenied`` ilə 403 qaytarır,
heç bir data sızmır. Yazma endpoint-ləri POST + CSRF tələb edir.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from core.http_ids import parse_uuid
from core.search_text import tolerant_q
from core.write_rate_limit import score_write_rate_limited

from ..constants import TaskStatus
from ..models import TeacherAssignment, TeachingTask, TeachingTaskRow
from ..public import STATUS_LABELS
from ..services import (
    AMENDMENT_REQUIRED,
    WorkloadDenied,
    amend_from_payload,
    assign_amended,
    confirm_distribution,
    curriculum_row_suggestions,
    delete_row_amended,
    distribution_readiness,
    ensure_can_manage,
    ensure_can_view,
    find_task,
    get_or_create_task,
    open_amendment,
    resolve_chair,
    row_warnings,
    save_row_amended,
    serialize_rows_state,
    teacher_load_panel,
    teacher_pool,
    unassign_amended,
)
from ..services.tasks import TOTAL_BELOW_ASSIGNED
from ._base import active_organization, actor_for, denied, error, json_body, no_org

# Backend auditi 2026-09-13, F-01: gövdədən gələn qeyri-UUID ``row_id`` /
# ``task_id`` / ``assignment_id`` ``filter(pk=...)``-də ValidationError → 500
# verirdi (sandbox: ``workload:assign``, ``workload:row_save``). İndi pk-lar
# ortaq ``core.http_ids.parse_uuid`` ilə süzülür; pozuq dəyər = «tapılmadı».

#: Vəziyyət toqquşması (409) kodları: bölünmüş saatdan az cəm (W2) və təsdiqlənmiş sənəddə səbəbsiz yazı
#: (2026-10-15 — UI düzəliş dialoqunu açıb sorğunu ``amend_reason`` / ``amend_note`` ilə təkrarlayır).
_CONFLICT_CODES = frozenset({TOTAL_BELOW_ASSIGNED, AMENDMENT_REQUIRED, "workload.hours_exceeded"})
#: QA-2 F-09 (2026-10-17): məzmun xətası icazə xətası deyil — 403 yox, 400 (səhv səbəb / say / qeyd).
_INPUT_CODES = frozenset(
    {
        "workload.invalid_reason",
        "workload.hours_positive",
        "workload.invalid_number",
        "workload.negative_number",
        "workload.note_required",
    }
)


def _write_denied(exc: WorkloadDenied) -> JsonResponse:
    if exc.code in _INPUT_CODES:
        return denied(exc, status=400)
    return denied(exc, status=409 if exc.code in _CONFLICT_CODES else 403)


def _truthy(value) -> bool:
    return str(value or "").lower() in ("1", "true", "on", "yes")


def _task_payload(task) -> dict:
    return {
        "id": str(task.pk),
        "status": task.status,
        "status_label": STATUS_LABELS.get(task.status, task.status),
        "revision": task.revision,
        "is_locked": task.is_locked,
        "is_editable": task.is_editable,
        # 2026-10-15: təsdiqlənmiş sənəddə hər yazı düzəliş (səbəb + qeyd) ilə gedir.
        "needs_amendment": task.status in (TaskStatus.DISTRIBUTED, TaskStatus.AMENDED),
        "academic_year": task.academic_year,
        "chair_id": str(task.chair_id),
    }


def _resolve_task(request, actor, *, task_id=None, chair_id=None, year=""):
    organization = active_organization(request)
    task_pk = parse_uuid(task_id) if task_id else None
    if task_id:
        task = (
            TeachingTask.objects.filter(organization=organization, pk=task_pk).select_related("chair").first()
            if task_pk is not None
            else None
        )
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
    task_id = request.GET.get("task") or None
    try:
        # Audit `access` F-13 (2026-09-13): `?chair=<yad tenantın kafedrası>`
        # `teachers`/`options`-da `chair_not_found` 403 verirdi, burada isə
        # `find_task` boş qaytarıb 200 «tapşırıq yoxdur» qabığı gedirdi — sızma
        # yox, amma üç qardaş endpoint fərqli cavab verirdi. Kafedra əvvəlcə eyni
        # resolver ilə aktiv təşkilata bağlanır; öz kafedrası üçün tapşırıq
        # olmayanda boş 200 (UI-nin «hələ yaradılmayıb» halı) dəyişmir.
        if chair_id and not task_id:
            resolve_chair(organization, chair_id)
        task = _resolve_task(request, actor, task_id=task_id, chair_id=chair_id, year=year)
    except WorkloadDenied as exc:
        if exc.code == "workload.task_not_found":
            return JsonResponse({"ok": True, "task": None, "rows": [], "teachers": [], "readiness": None})
        return denied(exc)
    season = request.GET.get("season") or ""
    search = request.GET.get("q") or ""
    payload_rows, loaded_rows, balance = serialize_rows_state(task, season=season, search=search)
    # PERF-1 F-09: süzgəcsiz görünüşdə hazırlıq eyni sətirlərdən; süzgəc varsa — tapşırığın hamısı yenidən.
    readiness = (
        distribution_readiness(task)
        if season or search
        else distribution_readiness(task, rows=loaded_rows, balance=balance)
    )
    return JsonResponse(
        {
            "ok": True,
            "task": _task_payload(task),
            "rows": payload_rows,
            "teachers": teacher_load_panel(task),
            "readiness": readiness,
        }
    )


@never_cache
@login_required
@require_GET
def teachers(request) -> JsonResponse:
    """Kafedranın müəllim hovuzu (axtarışlı) + hər birinin cari yükü (bütün kafedralar üzrə)."""
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
    # ``outside=1`` — başqa kafedraların müəllimləri də (ştat kafedrası yazılı; təyinatda ƏLAVƏ üzvlük alır).
    pool = teacher_pool(
        organization,
        chair,
        search=(request.GET.get("q") or "").strip(),
        include_outside=request.GET.get("outside") == "1",
    )
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
    search_q = tolerant_q(search, ("name",))
    if search_q is not None:
        subjects = subjects.filter(search_q)
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
            row_pk = parse_uuid(payload["row_id"])
            row = TeachingTaskRow.objects.filter(pk=row_pk, task=instance).first() if row_pk is not None else None
            if row is None:
                return error("workload.row_not_found", "Sətir tapılmadı.", status=404)
        saved = save_row_amended(
            task=instance,
            actor=actor,
            data=payload,
            row=row,
            amend=amend_from_payload(payload),
            shrink=_truthy(payload.get("shrink_assignments")),
            request=request,
        )
    except WorkloadDenied as exc:
        # Audit 2026-09-28 W2: bölünmüş saatdan az cəm — vəziyyət toqquşması (409).
        return _write_denied(exc)
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
        row_pk = parse_uuid(payload.get("row_id"))
        row = TeachingTaskRow.objects.filter(pk=row_pk, task=instance).first() if row_pk is not None else None
        if row is None:
            return error("workload.row_not_found", "Sətir tapılmadı.", status=404)
        delete_row_amended(task=instance, row=row, actor=actor, amend=amend_from_payload(payload), request=request)
    except WorkloadDenied as exc:
        return _write_denied(exc)
    return JsonResponse({"ok": True})


@never_cache
@login_required
@require_POST
@score_write_rate_limited("workload_assign")  # F-15 (2026-09-14): istifadəçi başına yazı vedrəsi
def assign(request) -> JsonResponse:
    organization = active_organization(request)
    if organization is None:
        return no_org()
    payload = json_body(request)
    actor = actor_for(request)
    row_pk = parse_uuid(payload.get("row_id"))
    row = (
        TeachingTaskRow.objects.filter(organization=organization, pk=row_pk)
        .select_related("task", "task__chair")
        .first()
        if row_pk is not None
        else None
    )
    if row is None:
        return error("workload.row_not_found", "Sətir tapılmadı.", status=404)
    assignment = None
    if payload.get("assignment_id"):
        assignment_pk = parse_uuid(payload["assignment_id"])
        assignment = (
            TeacherAssignment.objects.filter(pk=assignment_pk, row=row).first() if assignment_pk is not None else None
        )
        if assignment is None:
            return error("workload.assignment_not_found", "Bölgü tapılmadı.", status=404)
    try:
        saved = assign_amended(
            row=row,
            actor=actor,
            amend=amend_from_payload(payload),
            activity=payload.get("activity") or "",
            teacher_id=payload.get("teacher_id") or None,
            hours=payload.get("hours"),
            groups_note=payload.get("groups_note") or "",
            is_hourly_paid=_truthy(payload.get("is_hourly_paid")),
            note=payload.get("note") or "",
            assignment=assignment,
            request=request,
        )
    except WorkloadDenied as exc:
        return _write_denied(exc)
    body = {"ok": True, "assignment_id": str(saved.pk)}
    conflicts = int((getattr(saved, "offering_sync", None) or {}).get("schedule_conflicts") or 0)
    if conflicts:
        # Audit 2026-09-28 W4: müəllim dəyişikliyi cədvəldə toqquşma yaradıb — səssiz keçmir.
        body["schedule_conflicts"] = conflicts
        body["warning"] = pgettext(
            "workload",
            "Diqqət: yeni müəllimin cədvəldə eyni saatda başqa dərsi var (%(count)s toqquşma). "
            "Dərs cədvəlini yoxlayın.",
        ) % {"count": conflicts}
    return JsonResponse(body)


@never_cache
@login_required
@require_POST
def unassign_view(request) -> JsonResponse:
    organization = active_organization(request)
    if organization is None:
        return no_org()
    payload = json_body(request)
    actor = actor_for(request)
    assignment_pk = parse_uuid(payload.get("assignment_id"))
    assignment = (
        TeacherAssignment.objects.filter(organization=organization, pk=assignment_pk)
        .select_related("row", "row__task", "row__task__chair")
        .first()
        if assignment_pk is not None
        else None
    )
    if assignment is None:
        return error("workload.assignment_not_found", "Bölgü tapılmadı.", status=404)
    try:
        unassign_amended(assignment=assignment, actor=actor, amend=amend_from_payload(payload), request=request)
    except WorkloadDenied as exc:
        return _write_denied(exc)
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
            # QA-2 F-09: id siyahıları (``offering_ids``, ``group_offering_ids`` — yüzlərlə UUID) UI-a lazım deyil.
            "sync": {
                key: value for key, value in result["sync"].items() if key not in ("offering_ids", "group_offering_ids")
            },
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


__all__ = [
    "amend",
    "assign",
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
