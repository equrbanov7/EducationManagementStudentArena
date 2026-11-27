"""Labs — tələbənin cəhdə bağlı qaralaması və yekun təhvili."""

import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from ...lab_access import can_student_access_lab
from ...lab_assignment_service import get_lab_assignment_for_student
from ...lab_submission_service import (
    create_lab_submission,
    finalize_submission_answers,
    get_next_attempt_number,
    is_lab_open,
)
from ...models import LabAnswer, LabAssignment
from ..shared._helpers import _get_tenant_lab_or_404, _normalize_extensions, _validate_and_prepare_lab_upload


def _error(message, status):
    return JsonResponse({"success": False, "error": message}, status=status)


def _locked_assignment(lab, student):
    # Bütün tələbə yazıları eyni sətri cəhd nömrəsini oxumazdan əvvəl kilidləyir.
    assignments = LabAssignment.objects.select_for_update()
    assignment = assignments.filter(lab=lab, student=student).first()
    if assignment is None:
        created = get_lab_assignment_for_student(lab, student)
        assignment = assignments.get(pk=created.pk)
    elif not assignment.assigned_questions.exists():
        assignment.assign_questions()
    return assignment


def _question_conflict():
    return _error(
        pgettext("labs.view.error", "The assigned questions have changed. Reload the lab before submitting."), 409
    )


def _locked_questions(assignment):
    # Müəllimin silmə əməliyyatı eyni sual sətirlərini eyni ardıcıllıqla kilidləyir.
    return assignment.assigned_questions.order_by("pk").select_for_update(of=("self",), no_key=True)


def _attempt_conflict():
    return _error(pgettext("labs.view.error", "This attempt is no longer current. Reload the lab to continue."), 409)


def _validate_file(lab, upload):
    _validate_and_prepare_lab_upload(
        upload, allowed_extensions=_normalize_extensions(lab.allowed_extensions), max_size_mb=lab.max_file_size_mb or 25
    )


@login_required
@require_POST
def auto_save_answer(request, pk):
    lab = _get_tenant_lab_or_404(request, pk)
    if not can_student_access_lab(lab, request.user):
        return _error(pgettext("labs.view.permission", "permission_denied"), 403)
    if not is_lab_open(lab):
        return _error(pgettext("labs.view.error", "lab_closed"), 409)

    is_json = request.content_type == "application/json"
    try:
        data = json.loads(request.body) if is_json else request.POST
        text = data.get("answer", "")
        if not isinstance(text, str):
            raise ValueError
        question_id = int(data.get("question_id"))
        # Köhnə açıq səhifədən gələn sorğu sonrakı cəhdə keçməməlidir.
        attempt = int(data.get("attempt_number", 1))
    except (ValueError, TypeError, AttributeError):
        return _error(pgettext("labs.view.error", "Invalid lab answer."), 400)

    upload = request.FILES.get("answer_file")
    if upload:
        try:
            _validate_file(lab, upload)
        except ValidationError as exc:
            return _error(exc.messages[0], 400)

    with transaction.atomic():
        assignment = _locked_assignment(lab, request.user)
        if attempt != get_next_attempt_number(assignment) or attempt > (lab.max_attempts or 1):
            return _attempt_conflict()
        if not _locked_questions(assignment).filter(pk=question_id).exists():
            return _question_conflict()
        changes = {}
        if is_json or text.strip():
            changes["answer"] = text
        if upload:
            changes["answer_file"] = upload
        LabAnswer.objects.update_or_create(
            lab=lab, question_id=question_id, student=request.user, attempt_number=attempt, defaults=changes
        )
    return JsonResponse({"success": True})


def _save_form_answers(request, assignment, attempt, question_ids):
    """Formadakı son mətn/fayl əvvəlki qaralamanı yeniləyir; göndərilməyən sahə qorunur."""
    drafts = {
        answer.question_id: answer
        for answer in LabAnswer.objects.filter(lab=assignment.lab, student=assignment.student, attempt_number=attempt)
    }
    updates = []
    for question_id in question_ids:
        text = request.POST.get(f"answer_{question_id}")
        upload = request.FILES.get(f"file_{question_id}")
        clear_file = request.POST.get(f"clear_file_{question_id}") == "1"
        answer = drafts.get(question_id)
        if answer is None:
            if not text and not upload:
                continue
            answer = LabAnswer(
                lab=assignment.lab, student=assignment.student, question_id=question_id, attempt_number=attempt
            )
        if upload:
            _validate_file(assignment.lab, upload)
            answer.answer_file = upload
        elif clear_file:
            answer.answer_file = None
        elif text is None or text == answer.answer:
            continue
        if text is not None:
            answer.answer = text
        updates.append(answer)

    # Bütün fayllar yoxlanıldıqdan sonra saxla.
    for answer in updates:
        answer.save()


@login_required
@require_POST
def submit_lab(request, pk):
    lab = _get_tenant_lab_or_404(request, pk)
    if not can_student_access_lab(lab, request.user):
        return _error(pgettext("labs.view.permission", "permission_denied"), 403)

    try:
        attempt = int(request.POST.get("attempt_number", 1))
    except (ValueError, TypeError):
        return _attempt_conflict()
    if lab.status != "published":
        return _error(pgettext("labs.view.error", "lab_closed"), 409)

    with transaction.atomic():
        assignment = _locked_assignment(lab, request.user)
        next_attempt = get_next_attempt_number(assignment)
        success = {"success": True, "redirect_url": reverse("courses:course_dashboard", args=[lab.course_id])}
        if (
            attempt < next_attempt
            and "attempt_number" in request.POST
            and assignment.submissions.filter(attempt_number=attempt).exists()
        ):
            # Eyni səhifənin iki klik/retry sorğusu cəhdi ikinci dəfə xərcləmir.
            return JsonResponse(success)
        if not is_lab_open(lab) and not lab.allow_late_submission:
            return _error(pgettext("labs.view.error", "lab_closed"), 409)
        if next_attempt > (lab.max_attempts or 1):
            return _error(pgettext("labs.view.error", "attempts_exhausted"), 409)
        if attempt != next_attempt:
            return _attempt_conflict()
        question_ids = list(_locked_questions(assignment).values_list("pk", flat=True))
        form_ids = {
            key.rsplit("_", 1)[1]
            for key in request.POST.keys() | request.FILES.keys()
            if key.startswith(("answer_", "file_", "clear_file_"))
        }
        if form_ids.difference(str(pk) for pk in question_ids):
            return _question_conflict()
        try:
            _save_form_answers(request, assignment, attempt, question_ids)
        except ValidationError as exc:
            return _error(exc.messages[0], 400)
        submission = create_lab_submission(assignment, attempt_number=attempt)
        finalize_submission_answers(submission)
    return JsonResponse(success)
