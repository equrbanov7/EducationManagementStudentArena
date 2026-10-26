"""«Xarici nəticənin tanınması» — HTTP səthi (multipart / form POST, CSRF ``EMSCore.fetchJSON`` ilə, 2026-10-25).

Zəncir (fail-closed): tenant (aktiv təşkilat, əks halda 404) → view-as (yazı yoxdur, 403) → açar
(``student.credit_recognition`` struktur əhatəsi yoxdursa **403**) → əhatə (tələbə aktorun alt-ağacında deyilsə
**404**, mövcudluq sızmasın) → servis (:mod:`apps.registrar.credit_recognition`). Cavab ``{"ok", "message"|"error"}``.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from core.tenancy import get_request_organization, request_has_active_organization_context

from . import credit_recognition
from . import credit_recognition_read as read
from .models import ExternalCreditRecognition

_CTX = "registrar.recognition"


def _error(message, status=400, code=""):
    return JsonResponse({"ok": False, "error": str(message), "code": code}, status=status)


def _guard(request):
    """``(organization, None)`` və ya ``(None, JsonResponse)``."""
    organization = get_request_organization(request)
    if organization is None or not request_has_active_organization_context(request):
        raise Http404
    if getattr(request, "is_view_as", False):
        message = pgettext(_CTX, "Başqasının adından baxış rejimində dəyişiklik etmək olmaz.")
        return None, JsonResponse({"ok": False, "view_as_blocked": True, "detail": message}, status=403)
    if not read.can_manage(request.user, organization):
        return None, _error(pgettext(_CTX, "Xarici nəticəni tanımaq üçün səlahiyyətiniz yoxdur."), 403, "forbidden")
    return organization, None


@never_cache
@login_required
@require_POST
def create(request, student_id):
    organization, denied = _guard(request)
    if denied is not None:
        return denied
    if not read.student_in_scope(request.user, organization, student_id):
        raise Http404
    try:
        cleaned = credit_recognition.validate(
            organization=organization,
            student_id=student_id,
            data=request.POST,
            document=request.FILES.get("document"),
            actor=request.user,
        )
        result = credit_recognition.create(
            organization=organization, student_id=student_id, cleaned=cleaned, actor=request.user, request=request
        )
    except credit_recognition.RecognitionError as exc:
        return _error(exc.message, exc.status, exc.code)
    if result["exempted"]:
        message = pgettext(_CTX, "Xarici nəticə tanındı — tələbə bu fəndən azad edildi (jurnaldan çıxdı).")
    else:
        message = pgettext(
            _CTX,
            "Xarici nəticə tanındı. Jurnal bağlı olduğundan jurnal sətri dəyişmədi — transkriptdə tanınmış nəticə "
            "göstərilir.",
        )
    return JsonResponse({"ok": True, "message": message, "id": str(result["recognition"].pk)})


@never_cache
@login_required
@require_POST
def revoke(request, recognition_id):
    organization, denied = _guard(request)
    if denied is not None:
        return denied
    # Əhatədən kənar tələbənin tanınması — 404 (servis ``allowed_students`` ilə kilid altında da yoxlayır).
    student_id = (
        ExternalCreditRecognition.objects.filter(organization=organization, pk=recognition_id)
        .values_list("student_id", flat=True)
        .first()
    )
    if student_id is None or not read.student_in_scope(request.user, organization, student_id):
        raise Http404
    allowed = {student_id}
    try:
        result = credit_recognition.revoke(
            organization=organization,
            recognition_id=recognition_id,
            actor=request.user,
            reason=request.POST.get("reason") or "",
            request=request,
            allowed_students=allowed,
        )
    except credit_recognition.RecognitionError as exc:
        return _error(exc.message, exc.status, exc.code)
    if result["restored"]:
        message = pgettext(_CTX, "Tanınma ləğv edildi — tələbə fənnin jurnalına qaytarıldı.")
    else:
        message = pgettext(_CTX, "Tanınma ləğv edildi.")
    return JsonResponse({"ok": True, "message": message})


__all__ = ["create", "revoke"]
