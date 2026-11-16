"""exam_center paketi — nəticənin ləğvi / bərpası cəhd üzrə (sahib 2026-11-17).

Nəticələr siyahısından (müəllim/mərkəz nəticə səhifəsi) və zal oturumu səhifəsindən çağırılır: hər iki səth
eyni formanı (səbəb siyahıdan, izahat, tarix, sənəd) təsdiq pəncərəsi ilə göndərir. Məntiq
``services/final_center/result_annul.py``-dadır (0 bal, tələbəyə qeyd, audit, jurnal; bərpada əvvəlki bal).

Qapılar: POST + CSRF; tenant + YALNIZ imtahan mərkəzi (``center_org_or_403``) — nəzarətçi və müəllim ləğv
etmir; cəhd aktiv təşkilatın imtahanına aid olmalıdır. Sənəd yalnız imtahan mərkəzinə verilir.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET, require_POST

from apps.exams.domain.result_annulment import ExamResultAnnulment
from apps.exams.models import ExamAttempt
from apps.exams.services.final_center import TicketStateError, annul_attempt_result, restore_attempt_result
from core.audit import log_action
from core.constants import AuditAction

from ._shared import center_org_or_403

_CTX = "exams.final_center.message"


def _attempt_or_404(request, attempt_id):
    organization = center_org_or_403(request)
    attempt = get_object_or_404(
        ExamAttempt.objects.select_related("exam", "exam__organization", "user"),
        pk=attempt_id,
        exam__organization=organization,
    )
    return organization, attempt


def _back(request, attempt):
    candidate = request.POST.get("next") or ""
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(candidate)
    return redirect(reverse("exams:teacher_exam_results", kwargs={"slug": attempt.exam.slug}))


@login_required
@require_POST
def exam_center_attempt_annul(request, attempt_id):
    """Bitmiş cəhdin nəticəsini ləğv et (köçürmə və s.) — jurnalda 0, tələbəyə qeyd; «Bərpa et» ilə geri qaytarılır."""
    _organization, attempt = _attempt_or_404(request, attempt_id)
    try:
        done = annul_attempt_result(
            attempt,
            request.user,
            reason_key=(request.POST.get("reason") or "").strip(),
            note=request.POST.get("note") or "",
            incident_date=request.POST.get("incident_date") or None,
            document=request.FILES.get("document"),
            request=request,
        )
    except TicketStateError as exc:
        messages.error(request, str(exc))
        return _back(request, attempt)
    if done:
        messages.success(request, pgettext(_CTX, "Nəticə ləğv edildi: jurnalda 0 bal, tələbəyə qeyd göstərilir."))
    else:
        messages.info(request, pgettext(_CTX, "Bu nəticə artıq ləğv olunub."))
    return _back(request, attempt)


@login_required
@require_POST
def exam_center_attempt_restore(request, attempt_id):
    """Ləğvi geri qaytar — əvvəlki bal və jurnal dəyəri qayıdır (səbəb məcburi)."""
    _organization, attempt = _attempt_or_404(request, attempt_id)
    try:
        done = restore_attempt_result(attempt, request.user, note=request.POST.get("note") or "", request=request)
    except TicketStateError as exc:
        messages.error(request, str(exc))
        return _back(request, attempt)
    if done:
        messages.success(request, pgettext(_CTX, "Ləğv geri qaytarıldı: əvvəlki nəticə bərpa olundu."))
    else:
        messages.info(request, pgettext(_CTX, "Bu nəticə ləğv olunmayıb — bərpa ediləcək bir şey yoxdur."))
    return _back(request, attempt)


@login_required
@require_GET
def exam_center_annulment_document(request, annulment_id):
    """Ləğv qeydinə əlavə olunmuş sənəd — yalnız imtahan mərkəzi; hər açılış audit-ə yazılır."""
    organization = center_org_or_403(request)
    annulment = get_object_or_404(ExamResultAnnulment, pk=annulment_id, organization=organization)
    if not annulment.document:
        raise Http404
    log_action(
        AuditAction.VIEW,
        user=request.user,
        organization=organization,
        obj=annulment,
        reason="exam_result_annulment_document_viewed",
        request=request,
        resource_type="exams.ExamResultAnnulment",
        resource_id=str(annulment.pk),
    )
    try:
        handle = annulment.document.open("rb")
    except OSError:
        raise Http404 from None
    return FileResponse(handle, as_attachment=True, filename=annulment.document.name.rsplit("/", 1)[-1])


__all__ = ["exam_center_annulment_document", "exam_center_attempt_annul", "exam_center_attempt_restore"]
