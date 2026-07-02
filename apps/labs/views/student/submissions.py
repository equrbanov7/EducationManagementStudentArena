"""Labs — tələbə submission axını: autosave + submit (F2, 2026-07-02)."""

import json
import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from ...lab_access import can_student_access_lab
from ...lab_assignment_service import get_lab_assignment_for_student
from ...lab_submission_service import finalize_submission_answers, get_next_attempt_number, is_lab_open
from ...models import LabAnswer, LabAssignment, LabSubmission
from ..shared._helpers import (
    _get_tenant_lab_or_404,
    _normalize_extensions,
    _tenant_scoped_questions,
    _validate_and_prepare_lab_upload,
)

logger = logging.getLogger(__name__)


def _lab_student_access_denied_json():
    return JsonResponse(
        {"success": False, "error": pgettext("labs.view.permission", "permission_denied")},
        status=403,
    )


@login_required
@require_POST
def auto_save_answer(request, pk):
    """Cavabı avtomatik saxla - cari cəhd üçün"""
    lab = _get_tenant_lab_or_404(request, pk)

    if not can_student_access_lab(lab, request.user):
        return _lab_student_access_denied_json()

    if not is_lab_open(lab):
        return JsonResponse({"success": False, "error": pgettext("labs.view.error", "lab_closed")})

    try:
        assignment = LabAssignment.objects.filter(lab=lab, student=request.user).first()
        current_attempt = get_next_attempt_number(assignment)

        update_answer_text = False
        if request.content_type == "application/json":
            data = json.loads(request.body)
            question_id = data.get("question_id")
            answer = data.get("answer", "")
            answer_file = None
            update_answer_text = True
        else:
            question_id = request.POST.get("question_id")
            answer = request.POST.get("answer", "")
            answer_file = request.FILES.get("answer_file")
            # File autosave zamanı boş text ilə mövcud cavabı silməmək üçün
            # yalnız real mətn gələndə answer sahəsini yenilə.
            update_answer_text = bool((answer or "").strip())

        from django.shortcuts import get_object_or_404

        question = get_object_or_404(_tenant_scoped_questions(request), id=question_id, block__lab=lab)

        # Validate file BEFORE creating/updating the LabAnswer record so that
        # a rejected upload never leaves a partially-saved answer in the DB.
        if answer_file:
            allowed_extensions = _normalize_extensions(lab.allowed_extensions)
            _validate_and_prepare_lab_upload(
                answer_file,
                allowed_extensions=allowed_extensions,
                max_size_mb=lab.max_file_size_mb or 25,
            )

        # Bu cəhd üçün cavab yarat/yenilə
        lab_answer, created = LabAnswer.objects.get_or_create(
            lab=lab,
            question=question,
            student=request.user,
            attempt_number=current_attempt,
            defaults={"answer": answer, "is_draft": True},
        )

        if not created:
            if update_answer_text:
                lab_answer.answer = answer
            lab_answer.is_draft = True

        if answer_file:
            lab_answer.answer_file = answer_file

        lab_answer.save()

        return JsonResponse({"success": True})

    except ValidationError as exc:
        return JsonResponse({"success": False, "error": exc.messages[0]}, status=400)
    except Exception:
        logger.exception("Unexpected error in save_answer")
        return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)


@login_required
@require_POST
def submit_lab(request, pk):
    """Labı göndər"""
    lab = _get_tenant_lab_or_404(request, pk)

    if not can_student_access_lab(lab, request.user):
        return _lab_student_access_denied_json()

    if not is_lab_open(lab) and not lab.allow_late_submission:
        return JsonResponse({"success": False, "error": pgettext("labs.view.error", "lab_closed")})

    try:
        assignment = get_lab_assignment_for_student(lab, request.user)
        next_attempt_number = get_next_attempt_number(assignment)
        current_attempts = next_attempt_number - 1
        max_attempts = lab.max_attempts or 1

        if current_attempts >= max_attempts:
            return JsonResponse({"success": False, "error": pgettext("labs.view.error", "attempts_exhausted")})

        submission = LabSubmission.objects.create(
            assignment=assignment,
            status="submitted",
            attempt_number=next_attempt_number,
        )

        finalize_submission_answers(submission)

        return JsonResponse(
            {
                "success": True,
                "redirect_url": reverse("courses:course_dashboard", args=[lab.course.id]),
            }
        )

    except Exception:
        logger.exception("Unexpected error in submit_lab")
        return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)
