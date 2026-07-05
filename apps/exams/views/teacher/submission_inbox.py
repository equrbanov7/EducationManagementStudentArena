"""
Sual göndərişi view-ları.

Müəllim tərəfi: yeni göndəriş (preview → göndər), öz göndərişinin detalı,
düzəldib yenidən göndərmə. İmtahan mərkəzi tərəfi: qutu (inbox) və baxış
(qəbul → banka yaz / rədd → qeyd).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.exams.constants import EXAM_LANGUAGE_CHOICES, EXAM_LANGUAGE_VALUES
from apps.exams.models import QuestionBank, QuestionSubmission
from apps.exams.services.access_policy import _ensure_teacher, is_exam_center_user
from apps.exams.services.question_submission import (
    accept_submission,
    analyze_submission_text,
    ensure_can_review_submission,
    reject_submission,
    resubmit_question_set,
    submit_question_set,
)
from core.tenancy import get_request_organization


def _profile_section_url(section):
    return f"{reverse('accounts:profile')}?section={section}"


def _require_organization(request):
    organization = get_request_organization(request)
    if organization is None:
        raise PermissionDenied(
            pgettext("exams.view.question_submission.permission", "Aktiv təşkilat konteksti tapılmadı.")
        )
    return organization


def _normalize_language(raw_value):
    value = (raw_value or "").strip().lower()
    return value if value in EXAM_LANGUAGE_VALUES else "az"


def _form_state(request):
    return {
        "title": (request.POST.get("title") or "").strip(),
        "language": _normalize_language(request.POST.get("language")),
        "raw_text": request.POST.get("raw_text") or "",
    }


def _preview_context(raw_text):
    """Preview üçün parse nəticəsi + say xülasəsi (müəllim və mərkəz eyni şeyi görür)."""
    parsed, counts = analyze_submission_text(raw_text)
    return {"preview_parsed": parsed, "preview_counts": counts}


# ---------------------------------------------------------------------------
# Müəllim: yeni göndəriş
# ---------------------------------------------------------------------------
@login_required
def question_submission_create(request):
    _ensure_teacher(request.user)
    organization = _require_organization(request)

    context = {
        "language_choices": EXAM_LANGUAGE_CHOICES,
        "form_state": {"title": "", "language": "az", "raw_text": ""},
        "back_url": _profile_section_url("question-submissions"),
    }

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        form_state = _form_state(request)
        context["form_state"] = form_state

        if action == "preview":
            try:
                context.update(_preview_context(form_state["raw_text"]))
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
        elif action == "submit":
            try:
                submission = submit_question_set(
                    teacher=request.user,
                    organization=organization,
                    title=form_state["title"],
                    language=form_state["language"],
                    raw_text=form_state["raw_text"],
                )
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
            else:
                messages.success(
                    request,
                    pgettext(
                        "exams.view.question_submission.message",
                        "Göndəriş imtahan mərkəzinə çatdırıldı ({count} sual).",
                    ).format(count=submission.question_count),
                )
                return redirect("exams:question_submission_detail", submission_id=submission.id)

    return render(request, "exams/teacher/question_submission_form.html", context)


# ---------------------------------------------------------------------------
# Müəllim: detal + düzəlt/yenidən göndər
# ---------------------------------------------------------------------------
@login_required
def question_submission_detail(request, submission_id):
    _ensure_teacher(request.user)
    organization = _require_organization(request)
    submission = get_object_or_404(QuestionSubmission, id=submission_id, organization=organization)

    is_reviewer = is_exam_center_user(request.user)
    if submission.teacher_id != request.user.id and not is_reviewer:
        raise Http404()

    can_edit = submission.teacher_id == request.user.id and submission.can_be_edited_by_teacher

    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied(
                pgettext("exams.view.question_submission.permission", "Bu göndəriş dəyişdirilə bilməz.")
            )
        action = (request.POST.get("action") or "").strip()
        form_state = _form_state(request)

        if action == "preview":
            context = _detail_context(submission, can_edit=can_edit, is_reviewer=is_reviewer)
            context["form_state"] = form_state
            try:
                context.update(_preview_context(form_state["raw_text"]))
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
            return render(request, "exams/teacher/question_submission_detail.html", context)

        if action == "resubmit":
            try:
                submission = resubmit_question_set(
                    submission,
                    title=form_state["title"],
                    language=form_state["language"],
                    raw_text=form_state["raw_text"],
                )
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
            else:
                messages.success(
                    request,
                    pgettext(
                        "exams.view.question_submission.message",
                        "Göndəriş yeniləndi və imtahan mərkəzinə təkrar çatdırıldı.",
                    ),
                )
            return redirect("exams:question_submission_detail", submission_id=submission.id)

    return render(
        request,
        "exams/teacher/question_submission_detail.html",
        _detail_context(submission, can_edit=can_edit, is_reviewer=is_reviewer),
    )


def _detail_context(submission, *, can_edit, is_reviewer):
    return {
        "submission": submission,
        "parsed_questions": submission.parsed_snapshot or [],
        "can_edit": can_edit,
        "is_reviewer": is_reviewer,
        "language_choices": EXAM_LANGUAGE_CHOICES,
        "form_state": {
            "title": submission.title,
            "language": submission.language,
            "raw_text": submission.raw_text,
        },
        "back_url": _profile_section_url("question-submissions"),
    }


# ---------------------------------------------------------------------------
# İmtahan mərkəzi: qutu + baxış
# ---------------------------------------------------------------------------
@login_required
def question_submission_inbox(request):
    _ensure_teacher(request.user)
    organization = _require_organization(request)
    if not is_exam_center_user(request.user):
        raise PermissionDenied(
            pgettext("exams.service.access.permission", "question_submission_review_exam_center_only")
        )

    status_filter = (request.GET.get("status") or "pending").strip().lower()
    if status_filter not in {"pending", "accepted", "rejected", "all"}:
        status_filter = "pending"

    submissions = QuestionSubmission.objects.filter(organization=organization).select_related(
        "teacher", "accepted_bank"
    )
    if status_filter != "all":
        submissions = submissions.filter(status=status_filter)

    return render(
        request,
        "exams/teacher/question_submission_inbox.html",
        {
            "submissions": submissions[:100],
            "status_filter": status_filter,
            "pending_count": QuestionSubmission.objects.filter(
                organization=organization, status=QuestionSubmission.STATUS_PENDING
            ).count(),
            "back_url": _profile_section_url("question-submissions"),
        },
    )


@login_required
def question_submission_review(request, submission_id):
    _ensure_teacher(request.user)
    organization = _require_organization(request)
    submission = get_object_or_404(
        QuestionSubmission.objects.select_related("teacher", "accepted_bank"),
        id=submission_id,
        organization=organization,
    )
    ensure_can_review_submission(request.user, submission)

    banks = QuestionBank.objects.filter(organization=organization, default_question_type="test").order_by("-created_at")

    return render(
        request,
        "exams/teacher/question_submission_review.html",
        {
            "submission": submission,
            "parsed_questions": submission.parsed_snapshot or [],
            "banks": banks,
            "back_url": reverse("exams:question_submission_inbox"),
        },
    )


@login_required
@require_POST
def question_submission_decide(request, submission_id):
    _ensure_teacher(request.user)
    organization = _require_organization(request)
    submission = get_object_or_404(QuestionSubmission, id=submission_id, organization=organization)
    ensure_can_review_submission(request.user, submission)

    decision = (request.POST.get("decision") or "").strip()
    note = (request.POST.get("note") or "").strip()

    try:
        if decision == "accept":
            bank = None
            bank_id = (request.POST.get("bank_id") or "").strip()
            if bank_id:
                bank = get_object_or_404(QuestionBank, id=bank_id, organization=organization)
            bank, created_count = accept_submission(
                submission,
                reviewer=request.user,
                bank=bank,
                new_bank_name=request.POST.get("new_bank_name") or "",
                note=note,
            )
            messages.success(
                request,
                pgettext(
                    "exams.view.question_submission.message",
                    'Göndəriş qəbul edildi — {count} sual "{bank}" bankına əlavə olundu.',
                ).format(count=created_count, bank=bank.name),
            )
        elif decision == "reject":
            if not note:
                messages.error(
                    request,
                    pgettext(
                        "exams.view.question_submission.message",
                        "Rədd üçün müəllimə qeyd yazın — nəyi düzəltməlidir.",
                    ),
                )
                return redirect("exams:question_submission_review", submission_id=submission.id)
            reject_submission(submission, reviewer=request.user, note=note)
            messages.success(
                request,
                pgettext("exams.view.question_submission.message", "Göndəriş rədd edildi və müəllimə bildirildi."),
            )
        else:
            messages.error(request, pgettext("exams.view.question_submission.message", "Yanlış əməliyyat."))
            return redirect("exams:question_submission_review", submission_id=submission.id)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
        return redirect("exams:question_submission_review", submission_id=submission.id)

    return redirect("exams:question_submission_inbox")


__all__ = [
    "question_submission_create",
    "question_submission_decide",
    "question_submission_detail",
    "question_submission_inbox",
    "question_submission_review",
]
