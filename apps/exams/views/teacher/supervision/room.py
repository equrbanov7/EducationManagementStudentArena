"""«Nəzarət otağı» — imtahan səviyyəli canlı nəzarət səhifəsi + API (sahib 2026-11-06).

Bütün imtahan növləri (quiz, yazılı, praktiki, midterm/final) üçün eynidir: heyət imtahanın
səhifəsindən «Nəzarət otağı»na keçir, cəhdləri canlı izləyir, kilidlənən tələbəni «Bərpa et»
ilə qaytarır və ya imtahanı müvəqqəti dayandırır. Zal axınındakı imtahanlar üçün İmtahan
Mərkəzinin oturum monitoru da qalır — bu səhifə biletdən asılı deyil, birbaşa cəhdlər üzərindədir.

İcazə: ``get_teacher_exam_or_404`` — imtahanın müəllifi; midterm/final üçün həm də imtahan mərkəzi
(``manageable_exams_q``). Tenant sərhədi ``tenant_scoped_exams``-dadır. Dəyişdirici əməllər
CSRF-li POST-dur, audit-ə yazılır; xəta mətni brauzerə daxili detal vermir (SA-10 qaydası).
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.exams.features import exam_supervision_enabled
from apps.exams.models import ExamAttempt
from apps.exams.services.supervision import get_supervision_config, teacher_lock_attempt, teacher_resume_attempt
from apps.exams.services.supervision.room import exam_room_snapshot, resume_refusal
from apps.exams.views.shared.breadcrumbs import exam_breadcrumbs
from apps.exams.views.shared.tenant import get_teacher_exam_or_404
from core.audit import log_action
from core.constants import AuditAction

from ..exams._shared import _organization_selection_redirect, _resolve_required_organization

logger = logging.getLogger(__name__)

#: Otaq JS-inin sorğu tezliyi (saniyə). WS yoxdur — kiçik qrup imtahanı üçün yüngül poll kifayətdir.
ROOM_POLL_SECONDS = 5
_CTX = "exams.supervision_room"


def _room_exam(request, slug):
    """Otağın imtahanı (icazə + tenant) — aktiv təşkilat konteksti yoxdursa ``None``."""
    from apps.exams.views.shared.tenant import get_active_organization
    from core.tenancy import request_has_active_organization_context

    if get_active_organization(request) is None or not request_has_active_organization_context(request):
        return None
    return get_teacher_exam_or_404(request, slug=slug)


def _json_error(message, status):
    return JsonResponse({"success": False, "error": message}, status=status)


def _no_org_response():
    return _json_error(pgettext(_CTX, "Aktiv təşkilat seçilməyib."), 403)


def _room_attempt(exam, attempt_id):
    return get_object_or_404(
        ExamAttempt.objects.select_related("user", "exam", "exam__organization", "exam__supervision_config"),
        pk=attempt_id,
        exam=exam,
        is_trial=False,
    )


@login_required
@require_GET
def exam_supervision_room(request, slug):
    organization = _resolve_required_organization(request)
    if organization is None:
        return _organization_selection_redirect(request)
    exam = get_teacher_exam_or_404(request, slug=slug)
    from apps.exams.services.center_exams import is_center_exam
    from apps.exams.services.final_center import can_manage_final_center

    return render(
        request,
        "exams/teacher/supervision_room.html",
        {
            "exam": exam,
            "exam_crumbs": exam_breadcrumbs(request, exam, current=pgettext(_CTX, "Nəzarət otağı")),
            "snapshot": exam_room_snapshot(exam),
            "supervision_config": get_supervision_config(exam),
            "supervision_feature_enabled": exam_supervision_enabled(),
            "poll_seconds": ROOM_POLL_SECONDS,
            "is_center_exam": is_center_exam(exam),
            "can_manage_center": can_manage_final_center(request.user),
        },
    )


@login_required
@require_GET
@never_cache
def exam_supervision_room_snapshot(request, slug):
    exam = _room_exam(request, slug)
    if exam is None:
        return _no_org_response()
    return JsonResponse(exam_room_snapshot(exam))


@login_required
@require_GET
@never_cache
def exam_supervision_attempt_snapshot(request, slug, attempt_id):
    """Bir tələbənin «çiyni üzərindən» görüntüsü + proktorinq xronologiyası (yalnız oxu)."""
    from apps.exams.services.final_center import can_manage_final_center
    from apps.exams.services.supervision import get_attempt_live_snapshot
    from apps.exams.services.supervision.monitor_enrich import attempt_proctor_detail

    exam = _room_exam(request, slug)
    if exam is None:
        return _no_org_response()
    attempt = _room_attempt(exam, attempt_id)
    include_answer_key = exam.author_id == request.user.id or can_manage_final_center(request.user)
    snapshot = get_attempt_live_snapshot(attempt, include_answer_key=include_answer_key)
    snapshot["proctor"] = attempt_proctor_detail(attempt, exam.organization_id)
    snapshot["attempt_id"] = attempt.pk
    return JsonResponse(snapshot)


def _audit(request, exam, attempt, reason, changes):
    log_action(
        AuditAction.UPDATE,
        user=request.user,
        organization=exam.organization,
        obj=attempt,
        reason=reason,
        request=request,
        resource_type="exam_attempt",
        resource_id=str(attempt.pk),
        changes=changes,
    )


@login_required
@require_POST
def exam_supervision_attempt_resume(request, slug, attempt_id):
    """«Bərpa et» — kilidlənmiş (avtomatik və ya əl ilə) cəhdi davam etdirir.

    ``grant_extra_chance=1`` → tələbəyə əlavə şans (pozuntu sayğacı bir vahid azalır).
    """
    exam = _room_exam(request, slug)
    if exam is None:
        return _no_org_response()
    attempt = _room_attempt(exam, attempt_id)
    refusal = resume_refusal(attempt, get_supervision_config(exam))
    if refusal:
        return _json_error(_resume_refusal_message(refusal), 409)
    grant_extra_chance = request.POST.get("grant_extra_chance") == "1"
    previous = attempt.supervision_status
    try:
        teacher_resume_attempt(attempt, request.user, grant_extra_chance=grant_extra_chance)
    except ValueError:
        logger.warning("exam_supervision_attempt_resume refused: attempt=%s", attempt.pk, exc_info=True)
        return _json_error(pgettext(_CTX, "Cəhdi bərpa etmək mümkün olmadı."), 409)
    _audit(
        request,
        exam,
        attempt,
        "supervision_room_resume",
        {"supervision_status": [previous, attempt.supervision_status], "extra_chance": grant_extra_chance},
    )
    return JsonResponse({"success": True, "supervision_status": attempt.supervision_status})


@login_required
@require_POST
def exam_supervision_attempt_pause(request, slug, attempt_id):
    """«Dayandır» — tələbənin ekranını müvəqqəti kilidləyir (cəhd təhvil verilmir, «Bərpa et» qaytarır)."""
    exam = _room_exam(request, slug)
    if exam is None:
        return _no_org_response()
    attempt = _room_attempt(exam, attempt_id)
    if get_supervision_config(exam) is None:
        return _json_error(pgettext(_CTX, "Bu imtahanda nəzarət rejimi aktiv deyil."), 409)
    reason = (request.POST.get("reason") or "").strip()
    previous = attempt.supervision_status
    try:
        teacher_lock_attempt(attempt, request.user, reason=reason)
    except ValueError:
        logger.warning("exam_supervision_attempt_pause refused: attempt=%s", attempt.pk, exc_info=True)
        return _json_error(pgettext(_CTX, "Cəhdi dayandırmaq mümkün olmadı."), 409)
    _audit(
        request,
        exam,
        attempt,
        "supervision_room_pause",
        {"supervision_status": [previous, attempt.supervision_status], "reason": reason[:200]},
    )
    return JsonResponse({"success": True, "supervision_status": attempt.supervision_status})


def _resume_refusal_message(code):
    messages = {
        "finished": pgettext(_CTX, "İmtahan artıq bitib."),
        "not_locked": pgettext(_CTX, "Tələbə kilidli deyil — bərpa lazım deyil."),
        "no_config": pgettext(_CTX, "Bu imtahanda nəzarət rejimi aktiv deyil."),
        "policy": pgettext(_CTX, "Nəzarət siyasəti bərpaya icazə vermir («İkinci şans yoxdur»)."),
        "chance_used": pgettext(_CTX, "Tələbə əlavə şansından artıq istifadə edib."),
    }
    return messages.get(code) or pgettext(_CTX, "Cəhdi bərpa etmək mümkün olmadı.")


__all__ = [
    "exam_supervision_attempt_pause",
    "exam_supervision_attempt_resume",
    "exam_supervision_attempt_snapshot",
    "exam_supervision_room",
    "exam_supervision_room_snapshot",
]
