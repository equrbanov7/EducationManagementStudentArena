"""«Dərs yükü faylı» — Dərs yükü mərkəzinin ``load`` görünüşünün əməlləri (sahib 2026-10-23).

Üç addım (``actions.workload_action`` endpoint-i, ``action`` sahəsi ilə):

* ``load_upload`` — kafedra + fayl (Excel şablonu / Forma 1) → oxu → ÖNİZLƏMƏ (bütün axın savepoint-də işləyir və
  geri qaytarılır; saylar real tətbiqlə eynidir). Oxunmuş yazılar + hesabat sessiyada saxlanılır.
* ``load_apply`` — sessiyadakı yazılarla EYNİ axın, bu dəfə yazılır (fayl ikinci dəfə göndərilmir).
* ``load_cancel`` — önizləməni sil.

Qapı: ``workload.load_import`` + aktorun bu açarla əhatəsi seçilmiş kafedranı tutmalıdır (fail-closed). Şablon
endirmə (``load_template``) eyni qapıdan keçir.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

from .center_registry import current_academic_year, is_archive_year
from .constants import PERM_LOAD_IMPORT
from .services.load_upload import run_load_upload
from .services.load_upload_parsing import LoadEntry, LoadFileError, build_template, parse_upload, safe_filename
from .services.scoping import WorkloadDenied, manageable_chairs, resolve_actor

#: Sessiyadakı önizləmənin açarı.
LOAD_SESSION_KEY = "workload_load_preview"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def load_chairs(actor):
    """Aktorun fayl yükləyə bildiyi kafedralar (``workload.load_import`` əhatəsi)."""
    return manageable_chairs(actor, permission=PERM_LOAD_IMPORT)


def _chair(actor, chair_id):
    import uuid

    try:
        value = uuid.UUID(str(chair_id or "").strip())
    except (TypeError, ValueError):
        value = None
    chair = load_chairs(actor).filter(pk=value).first() if value else None
    if chair is None:
        raise WorkloadDenied("workload.load_chair_denied", "Kafedra seçilməyib və ya bu kafedraya icazəniz yoxdur.")
    return chair


def _year(request, organization) -> str:
    from .services import normalize_academic_year

    year = normalize_academic_year(request.POST.get("academic_year") or "") or current_academic_year(organization)
    if not year or is_archive_year(organization, year):
        raise WorkloadDenied("workload.archive_readonly", "Keçmiş tədris ili yalnız oxunuş üçün açıqdır.")
    return year


def _error(message, *, code, field=""):
    payload = {"ok": False, "error": code, "message": message}
    if field:
        payload["field"] = field
    return JsonResponse(payload, status=400)


def load_upload(request, organization, actor):
    chair = _chair(actor, request.POST.get("chair"))
    year = _year(request, organization)
    upload = request.FILES.get("file")
    if upload is None:
        return _error("Fayl seçilməyib.", code="file_required", field="file")
    try:
        entries, skipped, file_format = parse_upload(upload)
    except LoadFileError as exc:
        return _error(exc.message, code=exc.code, field="file")
    if not entries:
        return _error("Faylda dərs saatı olan sətir tapılmadı.", code="no_rows", field="file")
    report = run_load_upload(
        organization=organization,
        chair=chair,
        actor_user=request.user,
        entries=entries,
        skipped=skipped,
        year=year,
        apply=False,
    )
    request.session[LOAD_SESSION_KEY] = {
        "chair_id": str(chair.pk),
        "chair_name": chair.name,
        "year": year,
        "file_name": (getattr(upload, "name", "") or "")[:120],
        "format": file_format,
        "entries": [entry.to_dict() for entry in entries],
        "skipped": skipped,
        "report": report,
    }
    request.session.modified = True
    return JsonResponse({"ok": True, "entries": len(entries), "counters": report["counters"]})


def load_apply(request, organization, actor):
    stored = request.session.get(LOAD_SESSION_KEY) or {}
    if not stored.get("entries"):
        return _error("Önizləmə tapılmadı — faylı yenidən yükləyin.", code="no_preview")
    chair = _chair(actor, stored.get("chair_id"))
    if is_archive_year(organization, stored.get("year") or ""):
        raise WorkloadDenied("workload.archive_readonly", "Keçmiş tədris ili yalnız oxunuş üçün açıqdır.")
    report = run_load_upload(
        organization=organization,
        chair=chair,
        actor_user=request.user,
        entries=[LoadEntry.from_dict(item) for item in stored["entries"]],
        skipped=stored.get("skipped") or [],
        year=stored["year"],
        apply=True,
    )
    request.session[LOAD_SESSION_KEY] = {**stored, "entries": [], "report": report}
    request.session.modified = True
    return JsonResponse({"ok": True, "applied": True, "counters": report["counters"]})


def load_cancel(request, organization, actor):
    request.session.pop(LOAD_SESSION_KEY, None)
    request.session.modified = True
    return JsonResponse({"ok": True})


LOAD_HANDLERS = {"load_upload": load_upload, "load_apply": load_apply, "load_cancel": load_cancel}


@login_required
@require_GET
def load_template(request):
    """Boş Excel şablonu (seçilmiş kafedranın adı «Təlimat» vərəqində)."""
    organization = getattr(request, "organization", None)
    if organization is None:
        return HttpResponse(status=403)
    actor = resolve_actor(request.user, organization, request=request)
    if not actor.has(PERM_LOAD_IMPORT):
        return HttpResponse(status=403)
    chair_name = ""
    chair_id = request.GET.get("chair")
    if chair_id:
        try:
            chair_name = _chair(actor, chair_id).name
        except WorkloadDenied:
            return HttpResponse(status=403)
    response = HttpResponse(build_template(chair_name), content_type=_XLSX)
    response["Content-Disposition"] = f'attachment; filename="{safe_filename(chair_name)}"'
    response["Cache-Control"] = "no-store"
    return response


__all__ = ["LOAD_HANDLERS", "LOAD_SESSION_KEY", "load_chairs", "load_template"]
