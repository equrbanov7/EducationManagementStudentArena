"""Cavab açarı düzəlişi endpoint-ləri — imtahan mərkəzi (2026-10-13, gecə).

Yalnız POST + JSON (qərar modalından AJAX). Təhlükəsizlik:

* IDOR: item / düzəliş həmişə ``can_review_appeal`` (tenant + imtahan mərkəzi) ilə yoxlanır;
  özgə təşkilatın obyekti «yoxdur» kimi 404 qaytarır (mövcudluq orakulu yoxdur);
* qərar səlahiyyəti AÇARLA: ``appeal.respond`` + ``appeal.decide`` (rol auditi B1) — işçi/RİM
  modalda düzəlişi görür, amma edə bilmir (403);
* bütün yazı servis qatında tranzaksiyalı, audit + ledger izi ilə (bax ``services.key_corrections``).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from ...models import AnswerKeyCorrection, AppealItem
from ...services import can_review_appeal
from ...services.key_corrections import apply_key_correction, ensure_can_correct_key, revoke_key_correction


def _not_found():
    return JsonResponse(
        {"ok": False, "error": str(pgettext("appeals.view.message", "Apellyasiya tapılmadı."))}, status=404
    )


def _forbidden(exc):
    message = str(exc) or str(pgettext("appeals.view.message", "Apellyasiya qərarı vermək icazəniz yoxdur."))
    return JsonResponse({"ok": False, "error": message}, status=403)


def _invalid(exc):
    return JsonResponse({"ok": False, "error": exc.messages[0] if exc.messages else str(exc)}, status=400)


@login_required
@require_POST
def key_correction_apply(request, item_id):
    item = AppealItem.objects.select_related("appeal", "appeal__exam").filter(pk=item_id).first()
    if item is None or not can_review_appeal(request, item.appeal):
        return _not_found()
    try:
        ensure_can_correct_key(request, item.appeal)
        correction = apply_key_correction(
            item,
            reviewer=request.user,
            corrected_option_ids=request.POST.getlist("corrected_option_ids"),
            reason=request.POST.get("reason", ""),
            request=request,
        )
    except PermissionDenied as exc:
        return _forbidden(exc)
    except ValidationError as exc:
        return _invalid(exc)
    return JsonResponse(
        {
            "ok": True,
            "correction_id": correction.pk,
            "affected_count": correction.affected_count,
            "credited_count": correction.credited_count,
            "toast": str(
                pgettext(
                    "appeals.view.message",
                    "Cavab açarı düzəldildi: sualı cavablayan {affected} tələbədən {credited} nəfərin balı artırıldı.",
                ).format(affected=correction.affected_count, credited=correction.credited_count)
            ),
        }
    )


@login_required
@require_POST
def key_correction_revoke(request, correction_id):
    correction = AnswerKeyCorrection.objects.select_related("source_item__appeal").filter(pk=correction_id).first()
    appeal = getattr(getattr(correction, "source_item", None), "appeal", None)
    if correction is None or appeal is None or not can_review_appeal(request, appeal):
        return _not_found()
    try:
        ensure_can_correct_key(request, appeal)
        revoke_key_correction(correction, reviewer=request.user, reason=request.POST.get("reason", ""), request=request)
    except PermissionDenied as exc:
        return _forbidden(exc)
    except ValidationError as exc:
        return _invalid(exc)
    return JsonResponse({"ok": True, "toast": str(pgettext("appeals.view.message", "Açar düzəlişi geri alındı."))})


__all__ = ["key_correction_apply", "key_correction_revoke"]
