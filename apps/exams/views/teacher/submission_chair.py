"""Sual göndərişi — KAFEDRA MÜDİRİ tərəfi view-ları.

Kafedra müdiri (kafedra müdiri təyin edilməyibsə dekanlıq) göndərişə baxır və
qərar verir: TƏSDİQLƏ (→ İmtahan Mərkəzinə gedir) · DÜZƏLİŞ İSTƏ · RƏDD ET.
Düzəliş və rədd üçün səbəb MƏCBURİDİR (≥20 simvol) — müəllim nəyi düzəltməli
olduğunu bilməlidir.

Əhatə fail-closed-dur: başqa kafedranın müdiri 403 alır (bax
``apps/exams/services/question_chair_units.py``).  Sual önizləməsi mərkəzin
səthi ilə EYNİ fraqmentdir (``_question_submission_preview_items.html``).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.exams.models import QuestionSubmission
from apps.exams.services.question_chair_review import (
    MIN_REASON_LENGTH,
    chair_approve,
    chair_reject,
    chair_request_revision,
    ensure_can_chair_review,
)
from apps.exams.views.teacher.submission_inbox import (
    _profile_section_url,
    _require_organization,
)
from apps.exams.views.teacher.submission_meta import (
    QUESTIONS_PAGE_SIZE,
    annotate_display_numbers,
    annotate_preview_flags,
    snapshot_flag_counts,
)

_CTX = "exams.view.question_submission.chair"


def _get_submission(request, submission_id):
    organization = _require_organization(request)
    submission = get_object_or_404(
        QuestionSubmission.objects.select_related("teacher", "subject_ref", "chair_unit", "chair_reviewer"),
        id=submission_id,
        organization=organization,
    )
    ensure_can_chair_review(request.user, submission)
    return submission


@login_required
def question_submission_chair_review(request, submission_id):
    """Kafedra baxış səhifəsi — sual önizləməsi + qərar formu + zaman xətti."""
    submission = _get_submission(request, submission_id)
    questions = annotate_display_numbers(annotate_preview_flags(list(submission.parsed_snapshot or [])))
    return render(
        request,
        "exams/teacher/question_submission_chair_review.html",
        {
            "submission": submission,
            "submission_events": list(submission.events.select_related("actor")),
            "parsed_questions": questions[:QUESTIONS_PAGE_SIZE],
            "question_flag_counts": snapshot_flag_counts(questions),
            "questions_has_more": len(questions) > QUESTIONS_PAGE_SIZE,
            "questions_page_size": QUESTIONS_PAGE_SIZE,
            "can_decide": submission.is_at_chair,
            "min_reason_length": MIN_REASON_LENGTH,
            "back_url": _profile_section_url("question-chair-review"),
            "embed_active_section": "question-chair-review",
            "embed_section_title": submission.title,
        },
    )


@login_required
@require_POST
def question_submission_chair_decide(request, submission_id):
    """Kafedra qərarı: approve / revision / reject (səbəb məcburidir)."""
    submission = _get_submission(request, submission_id)
    decision = (request.POST.get("decision") or "").strip()
    reason = (request.POST.get("reason") or "").strip()

    try:
        if decision == "approve":
            chair_approve(submission, actor=request.user, note=reason)
            messages.success(
                request,
                pgettext(_CTX, "Sual dəsti təsdiqləndi və İmtahan Mərkəzinə göndərildi."),
            )
        elif decision == "revision":
            chair_request_revision(submission, actor=request.user, reason=reason)
            messages.success(request, pgettext(_CTX, "Düzəliş tələbi müəllimə göndərildi."))
        elif decision == "reject":
            chair_reject(submission, actor=request.user, reason=reason)
            messages.success(request, pgettext(_CTX, "Sual dəsti rədd edildi və müəllimə bildirildi."))
        else:
            messages.error(request, pgettext(_CTX, "Yanlış əməliyyat."))
            return redirect("exams:question_submission_chair_review", submission_id=submission.id)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
        return redirect("exams:question_submission_chair_review", submission_id=submission.id)

    return redirect(_profile_section_url("question-chair-review"))


__all__ = [
    "question_submission_chair_decide",
    "question_submission_chair_review",
]
