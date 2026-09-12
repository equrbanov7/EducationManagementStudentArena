"""İmtahan Mərkəzi — yazılı imtahan ballarının FAYLDAN köçürülməsi (JSON endpoint-lər).

Sahib (2026-09-12): «tələbələrin balları sistemə yüklənsin». Üç marşrut:

* ``exam_score_import_template`` — seçilmiş açılışın siyahısı ilə DOLDURULMUŞ
  şablon (GET, .xlsx / .csv);
* ``exam_score_import_preview`` — QURU İCRA: fayl yüklənir, sətir-sətir yoxlanılır,
  HEÇ NƏ YAZILMIR (POST, multipart);
* ``exam_score_import_apply`` — tətbiq: partiya (``ExamScoreSheet``) + sətir başına
  savepoint, yazı YALNIZ ``registrar.exam_score_entry`` servisindən keçir
  (POST, multipart).

Hər üçü FAIL-CLOSED: ``final_score.entry`` (+ superadmin) və açılışın struktur
əhatəsi olmayan aktor 403 alır. Ön baxış və tətbiq EYNİ plan qurucusundan
keçir («gördüyün nəticə = alacağın nəticə»); fayl serverdə saxlanılmır.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.registrar.models import CorrectionReason, ExamScoreSheetSource
from apps.registrar.public import exam_score_entry as service
from apps.registrar.public import exam_score_import as importer
from apps.registrar.public import exam_score_sheets as sheets_service

from ._helpers import _is_superadmin_user
from .exam_score_entry import ExamScoreEntryError, _can_manage, _offering_or_error, _resolve_target_org

_CTX = "accounts.exam_score_entry"


def _denied(message=""):
    return JsonResponse(
        {
            "ok": False,
            "error": "permission_denied",
            "message": message
            or pgettext(_CTX, "Bu bölmə yalnız imtahan balı daxil etmə səlahiyyəti olanlar üçündür."),
        },
        status=403,
    )


def _bad(code, message, status=400):
    return JsonResponse({"ok": False, "error": code, "message": message}, status=status)


def _gate(request):
    """``(organization, offering, error_response)`` — icazə + əhatə qapısı (fail-closed)."""
    organization = _resolve_target_org(request)
    if organization is None or not _can_manage(request.user, organization):
        return None, None, _denied()
    offering_id = request.POST.get("offering_id") or request.GET.get("offering") or ""
    try:
        offering = _offering_or_error(request, organization, offering_id)
    except ExamScoreEntryError as exc:
        return organization, None, _bad("offering_not_found", str(exc), status=404)
    if not _is_superadmin_user(request.user):
        try:
            service.assert_offering_in_actor_scope(request.user, organization, offering)
        except PermissionDenied as exc:
            return organization, None, _denied(str(exc))
    return organization, offering, None


@never_cache
@login_required
@require_GET
def exam_score_import_template(request):
    """Siyahı ilə doldurulmuş şablon faylı (Tələbə № · FİN · Ad Soyad · Qrup · Cari bal · Bal)."""
    _organization, offering, error = _gate(request)
    if error is not None:
        return error
    fmt = "csv" if (request.GET.get("format") or "").strip().lower() == "csv" else "xlsx"
    roster = service.roster_for_offering(offering=offering)
    payload, content_type, filename = importer.build_template(roster=roster, fmt=fmt)
    response = HttpResponse(payload, content_type=content_type)
    response["Content-Disposition"] = 'attachment; filename="%s"' % filename
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _plan_from_request(request, offering):
    """``(roster, plan, error_response)`` — faylı oxuyub planı qurur (ön baxış = tətbiq)."""
    try:
        rows = importer.read_rows(request.FILES.get("file"))
    except importer.ImportFileError as exc:
        return None, None, _bad(exc.code, exc.message)
    roster = service.roster_for_offering(offering=offering)
    return roster, importer.build_plan(roster=roster, rows=rows), None


def _payload(plan, roster, *, applied=False, result=None, sheet=None):
    summary = importer.summarize(plan, roster=roster)
    data = {
        "ok": True,
        "applied": applied,
        "summary": summary,
        "needs_justification": importer.needs_justification(plan),
        "rows": plan,
    }
    if result is not None:
        data["result"] = {
            "written": result["written"],
            "skipped": result["skipped"],
            "failed": result["failed"],
            "total": result["total"],
        }
    if sheet is not None:
        data["sheet"] = sheets_service.sheet_row(sheet)
    return data


@never_cache
@login_required
@require_POST
def exam_score_import_preview(request):
    """Quru icra — nə yazılacaq, nə ötürüləcək, harada xəta var."""
    _organization, offering, error = _gate(request)
    if error is not None:
        return error
    roster, plan, error = _plan_from_request(request, offering)
    if error is not None:
        return error
    return JsonResponse(_payload(plan, roster))


def _justification_error(plan, request):
    """Dəyişən sətir varsa səbəb + qeyd + skan (partiya sənədi) BİRLİKDƏ tələb olunur.

    Servis onsuz da hər sətri ayrıca rədd edərdi; burada ƏVVƏLCƏDƏN yoxlanır ki,
    yarımçıq partiya (yeni ballar yazılıb, dəyişikliklər rədd olunub) yaranmasın —
    operator quru icrada K dəyişikliyi görüb, dialoqda üçünü də verir.
    """
    if not importer.needs_justification(plan):
        return None
    reason = (request.POST.get("reason") or "").strip()
    note = (request.POST.get("note") or "").strip()
    evidence = request.FILES.get("sheet_evidence")
    if reason not in CorrectionReason.values or not note or evidence is None:
        return _bad(
            "justification_required",
            pgettext(_CTX, "Yazılmış balı dəyişən sətirlər var — səbəb, qeyd və skan edilmiş sənəd tələb olunur."),
        )
    return None


@never_cache
@login_required
@require_POST
def exam_score_import_apply(request):
    """Tətbiq — partiya + sətir başına savepoint; bir pis sətir faylı dayandırmır."""
    _organization, offering, error = _gate(request)
    if error is not None:
        return error
    roster, plan, error = _plan_from_request(request, offering)
    if error is not None:
        return error
    error = _justification_error(plan, request)
    if error is not None:
        return error
    upload = request.FILES.get("file")
    try:
        metadata = sheets_service.sheet_metadata_from_post(request.POST, request.FILES, offering=offering)
        with transaction.atomic():
            sheet = sheets_service.create_sheet(
                offering=offering,
                by_user=request.user,
                source=ExamScoreSheetSource.IMPORT,
                original_filename=getattr(upload, "name", "") or "",
                request=request,
                **metadata,
            )
            result = importer.apply_plan(
                offering=offering,
                plan=plan,
                by_user=request.user,
                request=request,
                sheet=sheet,
                reason=(request.POST.get("reason") or "").strip(),
                note=(request.POST.get("note") or "").strip(),
            )
            sheet = sheets_service.finalize_sheet(sheet, result, by_user=request.user, request=request)
    except ValidationError as exc:
        return _bad("validation_error", " ".join(exc.messages))
    return JsonResponse(_payload(plan, roster, applied=True, result=result, sheet=sheet))


__all__ = ["exam_score_import_apply", "exam_score_import_preview", "exam_score_import_template"]
