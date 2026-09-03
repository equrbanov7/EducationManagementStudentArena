"""QuestionSubmission visual preview endpoint-i."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from apps.exams.models import QuestionSubmission
from apps.exams.services.access_policy import _ensure_teacher, is_exam_center_user
from apps.exams.services.import_preview import render_stashed_question_preview
from apps.exams.services.question_chair_units import can_review_submission_as_chair
from core.tenancy import get_request_organization


def _visual_response(png):
    response = HttpResponse(png, content_type="image/png")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_GET
def question_import_visual_preview(request, token, source_index):
    """Workbench-də saxlanmamış private import bundle-ını yalnız sahibinə göstər."""

    _ensure_teacher(request.user)
    organization = get_request_organization(request)
    if organization is None:
        raise Http404()
    try:
        png = render_stashed_question_preview(
            token,
            source_index,
            owner_id=request.user.pk,
            organization_id=organization.pk,
        )
    except (OSError, PermissionDenied, ValueError):
        raise Http404()
    return _visual_response(png)


@login_required
@require_GET
def question_submission_visual_preview(request, submission_id, source_index):
    # `_ensure_teacher` QƏSDƏN YOXDUR: kafedra müdirinin profil rolu müəllim
    # olmaya bilər, amma o, təsdiq üçün vizual mənbəni GÖRMƏLİDİR. Əhatə
    # aşağıda üç yolla (sahib / kafedra / kafedra təsdiqindən keçmiş mərkəz)
    # fail-closed yoxlanılır.
    organization = get_request_organization(request)
    if organization is None:
        raise Http404()
    submission = get_object_or_404(
        QuestionSubmission,
        id=submission_id,
        organization=organization,
    )
    # Mərkəz YALNIZ kafedra təsdiqindən sonra görür (mövcudluq sızması yoxdur).
    is_center = is_exam_center_user(request.user) and submission.has_reached_center
    if (
        submission.teacher_id != request.user.id
        and not is_center
        and not can_review_submission_as_chair(request.user, submission)
    ):
        raise Http404()
    if not submission.import_token:
        raise Http404()
    allowed_indices = {
        question.get("source_index") for question in (submission.parsed_snapshot or []) if isinstance(question, dict)
    }
    if source_index not in allowed_indices:
        raise Http404()
    try:
        png = render_stashed_question_preview(
            submission.import_token,
            source_index,
            owner_id=submission.teacher_id,
            organization_id=submission.organization_id,
        )
    except (OSError, ValueError):
        raise Http404()

    return _visual_response(png)


__all__ = [
    "question_import_visual_preview",
    "question_submission_visual_preview",
]
