"""Mərhələ 4 ekranlarının ƏMƏLLƏRİ — tək JSON POST endpoint-i.

Ekran 12/13/15/16 bütün mutasiyaları buradan keçir (Mərhələ 1/2-nin
``catalog_actions`` / ``semester_actions`` naxışı): `action` sahəsi handler
seçir, hər handler ÖZ icazə qapısını çağırır (fail-closed), səbəb tələb edən
əməllər ≥20 simvol yoxlanışından keçir və hamısı ``core.audit``-ə yazılır.

⚠️ Bu fayl SƏHİFƏ deyil — bölmə paneli oxu-only render olunur, yazma yalnız
bura gəlir (`data-tof-form` / `data-tof-submit`, `static/js/.../teaching_office.js`).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .center_registry import is_archive_year
from .constants import ObjectionStatus, RowReviewStatus
from .models import LoadObjection, TaskFacultySlice, TeachingTask, TeachingTaskRow
from .services import (
    WorkloadDenied,
    apply_import,
    approve_slice,
    build_mapping,
    confirm_own_load,
    create_objection,
    ensure_can_manage,
    generate_rows_from_plan,
    get_or_create_task,
    normalize_academic_year,
    parse_workbook,
    resolve_actor,
    resolve_objection,
    return_slice,
    review_all,
    set_row_review,
    submit_task,
)
from .services.imports import ImportFileError
from .state_machine import IllegalTransition

#: Sessiyada saxlanılan idxal önizləməsinin açarı (addım 1 → 2 → 3).
IMPORT_SESSION_KEY = "workload_import_preview"


def _error(message, *, status=400, code="invalid", field=""):
    payload = {"ok": False, "error": code, "message": message}
    if field:
        payload["field"] = field
    return JsonResponse(payload, status=status)


def _denied(exc: WorkloadDenied):
    # QA dalğa 2: `stale_revision` da konfliktdir (403 deyil) — istifadəçi
    # səlahiyyətsiz deyil, sadəcə səhifəsi köhnəlib.
    status = (
        409
        if exc.code in ("workload.illegal_transition", "workload.slice_not_open", "workload.stale_revision")
        else 403
    )
    if exc.code in (
        "workload.reason_too_short",
        "workload.invalid_reason",
        "workload.no_rows",
        "workload.no_faculty_slice",
        "workload.invalid_review_state",
    ):
        status = 400
    return JsonResponse({"ok": False, "error": exc.code, "message": exc.message}, status=status)


def _uuid(value) -> str:
    """Sərbəst mətn UUID sütununa DÜŞMÜR — yanlış dəyər «tapılmadı» olur."""
    import uuid as _uuid_module

    text = str(value or "").strip()
    try:
        return str(_uuid_module.UUID(text))
    except (TypeError, ValueError):
        return ""


def _ensure_writable(organization, year: str):
    if is_archive_year(organization, year):
        raise WorkloadDenied("workload.archive_readonly", "Keçmiş tədris ili yalnız oxunuş üçün açıqdır.")


# ── Ekran 12 — tədris şöbəsi ────────────────────────────────────────────────


def _create_task(request, organization, actor):
    year = normalize_academic_year(request.POST.get("academic_year") or "")
    chair_id = _uuid(request.POST.get("chair"))
    if not chair_id:
        return _error("Kafedra seçilməyib.", code="chair_required", field="chair")
    _ensure_writable(organization, year)
    task, created = get_or_create_task(
        organization=organization, chair_id=chair_id, academic_year=year, actor=actor, request=request
    )
    return JsonResponse({"ok": True, "id": str(task.pk), "created": created})


def _resolve_task(organization, task_id):
    task = (
        TeachingTask.objects.filter(organization=organization, pk__in=[value for value in (_uuid(task_id),) if value])
        .select_related("chair")
        .first()
    )
    if task is None:
        raise WorkloadDenied("workload.task_not_found", "Tapşırıq tapılmadı.")
    return task


def _generate_rows(request, organization, actor):
    task = _resolve_task(organization, request.POST.get("task"))
    _ensure_writable(organization, task.academic_year)
    program_ids = [value for value in request.POST.getlist("programs") if value]
    result = generate_rows_from_plan(task=task, actor=actor, program_ids=program_ids, request=request)
    return JsonResponse({"ok": True, **result})


def _submit(request, organization, actor):
    task = _resolve_task(organization, request.POST.get("task"))
    _ensure_writable(organization, task.academic_year)
    result = submit_task(task=task, actor=actor, request=request)
    return JsonResponse({"ok": True, **result})


def _import_upload(request, organization, actor):
    task = _resolve_task(organization, request.POST.get("task"))
    # ⚠️ QAPI ADDIM 1-DƏDİR (audit 2026-09-03): əvvəl yalnız `import_apply`
    # yoxlanılırdı, yəni İSTƏNİLƏN autentifikasiya olunmuş üzv 10 MB-lıq xlsx
    # göndərib parser-i (openpyxl) və uyğunlaşdırma sorğularını işlədə bilirdi.
    ensure_can_manage(actor, task.chair_id)
    _ensure_writable(organization, task.academic_year)
    upload = request.FILES.get("file")
    if upload is None:
        return _error("Fayl seçilməyib.", code="file_required", field="file")
    try:
        records = parse_workbook(upload)
    except ImportFileError as exc:
        return _error(exc.message, code=exc.code, field="file")
    preview = build_mapping(organization=organization, records=records)
    request.session[IMPORT_SESSION_KEY] = {
        "task_id": str(task.pk),
        "records": preview["records"],
        "file_name": getattr(upload, "name", ""),
    }
    request.session.modified = True
    return JsonResponse(
        {
            "ok": True,
            "row_count": preview["row_count"],
            "matched": preview["matched"],
            "unmatched": preview["unmatched"],
        }
    )


def _import_apply(request, organization, actor):
    stored = request.session.get(IMPORT_SESSION_KEY) or {}
    records = stored.get("records") or []
    if not records:
        return _error("İdxal önizləməsi tapılmadı — faylı yenidən yükləyin.", code="no_preview")
    task = _resolve_task(organization, stored.get("task_id"))
    _ensure_writable(organization, task.academic_year)
    result = apply_import(task=task, actor=actor, records=records, request=request)
    request.session.pop(IMPORT_SESSION_KEY, None)
    request.session.modified = True
    return JsonResponse({"ok": True, **result})


def _import_cancel(request, organization, actor):
    request.session.pop(IMPORT_SESSION_KEY, None)
    request.session.modified = True
    return JsonResponse({"ok": True})


# ── Ekran 13 — koordinator ──────────────────────────────────────────────────


def _resolve_row(organization, row_id):
    row = (
        TeachingTaskRow.objects.filter(organization=organization, pk__in=[value for value in (_uuid(row_id),) if value])
        .select_related("task", "task__chair", "specialty")
        .first()
    )
    if row is None:
        raise WorkloadDenied("workload.row_not_found", "Sətir tapılmadı.")
    return row


def _row_review(request, organization, actor):
    row = _resolve_row(organization, request.POST.get("row"))
    _ensure_writable(organization, row.task.academic_year)
    status = (request.POST.get("state") or RowReviewStatus.REVIEWED).strip()
    set_row_review(row=row, actor=actor, status=status, comment=request.POST.get("reason") or "", request=request)
    return JsonResponse({"ok": True, "state": status})


def _review_all(request, organization, actor):
    year = request.POST.get("academic_year") or ""
    _ensure_writable(organization, year)
    marked = review_all(actor=actor, academic_year=year, request=request)
    return JsonResponse({"ok": True, "marked": marked})


# ── Ekran 15 — dekanlıq ─────────────────────────────────────────────────────


def _resolve_slice(organization, slice_id):
    item = (
        TaskFacultySlice.objects.filter(
            organization=organization, pk__in=[value for value in (_uuid(slice_id),) if value]
        )
        .select_related("task", "faculty")
        .first()
    )
    if item is None:
        raise WorkloadDenied("workload.slice_not_found", "Fakültə dilimi tapılmadı.")
    return item


def _approve(request, organization, actor):
    item = _resolve_slice(organization, request.POST.get("slice"))
    _ensure_writable(organization, item.task.academic_year)
    result = approve_slice(slice_obj=item, actor=actor, comment=request.POST.get("comment") or "", request=request)
    return JsonResponse({"ok": True, **result})


def _return(request, organization, actor):
    item = _resolve_slice(organization, request.POST.get("slice"))
    _ensure_writable(organization, item.task.academic_year)
    row_ids = [value for value in request.POST.getlist("ids") if value]
    result = return_slice(
        slice_obj=item, actor=actor, reason=request.POST.get("reason") or "", row_ids=row_ids, request=request
    )
    return JsonResponse({"ok": True, **result})


# ── Ekran 16 — müəllim ──────────────────────────────────────────────────────


def _object(request, organization, actor):
    objection = create_objection(
        actor=actor,
        assignment_id=_uuid(request.POST.get("assignment")),
        reason_key=(request.POST.get("reason_key") or "").strip(),
        text=request.POST.get("reason") or "",
        request=request,
    )
    return JsonResponse({"ok": True, "id": str(objection.pk)})


def _confirm_load(request, organization, actor):
    result = confirm_own_load(
        actor=actor, academic_year=(request.POST.get("academic_year") or "").strip(), request=request
    )
    return JsonResponse({"ok": True, "confirmed_at": result["confirmed_at"].isoformat()})


def _resolve_objection(request, organization, actor):
    objection = (
        LoadObjection.objects.filter(
            organization=organization, pk__in=[value for value in (_uuid(request.POST.get("objection")),) if value]
        )
        .select_related("row", "row__task")
        .first()
    )
    if objection is None:
        return _error("Etiraz tapılmadı.", status=404, code="not_found")
    status = (request.POST.get("state") or ObjectionStatus.ACCEPTED).strip()
    resolve_objection(
        objection=objection, actor=actor, status=status, note=request.POST.get("reason") or "", request=request
    )
    return JsonResponse({"ok": True, "state": status})


_HANDLERS = {
    "create_task": _create_task,
    "generate_rows": _generate_rows,
    "submit": _submit,
    "import_upload": _import_upload,
    "import_apply": _import_apply,
    "import_cancel": _import_cancel,
    "row_review": _row_review,
    "review_all": _review_all,
    "approve_slice": _approve,
    "return_slice": _return,
    "object": _object,
    "confirm_load": _confirm_load,
    "resolve_objection": _resolve_objection,
}


@login_required
@require_POST
def workload_action(request):
    """Dərs yükü zəncirinin bütün mutasiyaları (tək endpoint, fail-closed)."""
    organization = getattr(request, "organization", None)
    if organization is None:
        return _error("Aktiv təşkilat konteksti yoxdur.", status=403, code="no_org")
    handler = _HANDLERS.get((request.POST.get("action") or "").strip())
    if handler is None:
        return _error("Naməlum əməl.", code="unknown_action")
    actor = resolve_actor(request.user, organization, request=request)
    try:
        return handler(request, organization, actor)
    except IllegalTransition as exc:
        return JsonResponse({"ok": False, "error": exc.code, "message": exc.message}, status=409)
    except WorkloadDenied as exc:
        return _denied(exc)


__all__ = ["IMPORT_SESSION_KEY", "workload_action"]
