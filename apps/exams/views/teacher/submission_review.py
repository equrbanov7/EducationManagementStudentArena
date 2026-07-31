"""
Sual göndərişi — İMTAHAN MƏRKƏZİ tərəfi view-ları.

``submission_inbox.py``-dan ayrılıb (modul ölçü qapısı): baxış (review) +
qərar (qəbul/rədd) + sual siyahısının lazy fraqment endpoint-i. Müəllim tərəfi
(yeni göndəriş, detal/redaktə) ``submission_inbox.py``-dadır.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET, require_POST

from apps.exams.models import QuestionBank, QuestionSubmission
from apps.exams.services.access_policy import _ensure_teacher, is_exam_center_user
from apps.exams.services.question_submission import (
    accept_submission,
    ensure_can_review_submission,
    reject_submission,
)
from apps.exams.views.teacher.submission_inbox import (
    _profile_section_url,
    _require_organization,
)
from apps.exams.views.teacher.submission_meta import (
    QUESTION_FLAG_VALUES,
    QUESTIONS_PAGE_SIZE,
    annotate_display_numbers,
    annotate_preview_flags,
    filter_snapshot_questions,
    snapshot_flag_counts,
)


# ---------------------------------------------------------------------------
# İmtahan mərkəzi: baxış (köhnə "qutu" səhifəsi profil bölməsinə köçüb)
# ---------------------------------------------------------------------------
@login_required
def question_submission_inbox(request):
    """Köhnə ayrıca qutu (inbox) səhifəsi ləğv edilib — göndərişlər indi profil
    bölməsində inline filtrlənir (axtarış + fakültə/kafedra/müəllim/dövr/dil).
    Route köhnə bookmark/linklər üçün yönləndirmə kimi saxlanılır."""
    return redirect(_profile_section_url("question-submissions"))


@login_required
def question_submission_review(request, submission_id):
    _ensure_teacher(request.user)
    organization = _require_organization(request)
    submission = get_object_or_404(
        QuestionSubmission.objects.select_related("teacher", "accepted_bank", "subject_ref"),
        id=submission_id,
        organization=organization,
    )
    ensure_can_review_submission(request.user, submission)

    # Bank seçimi: göndərişin fənninə/imtahan növünə uyğun banklar önə düşür
    # (0 = fənn+növ, 1 = fənn, 2 = növ, 3 = qalan) — mərkəz düzgün bankı
    # axtarmadan görsün.
    from django.db.models import Case, IntegerField, Value, When

    rank_conditions = []
    if submission.subject_ref_id:
        if submission.exam_kind:
            rank_conditions.append(
                When(subject_ref_id=submission.subject_ref_id, exam_kind=submission.exam_kind, then=Value(0))
            )
        rank_conditions.append(When(subject_ref_id=submission.subject_ref_id, then=Value(1)))
    if submission.exam_kind:
        rank_conditions.append(When(exam_kind=submission.exam_kind, then=Value(2)))
    banks = (
        QuestionBank.objects.filter(organization=organization, default_question_type="test")
        .select_related("subject_ref")
        .annotate(
            match_rank=(
                Case(*rank_conditions, default=Value(3), output_field=IntegerField())
                if rank_conditions
                else Value(3, output_field=IntegerField())
            )
        )
        .order_by("match_rank", "-created_at")
    )

    # Sual siyahısı LAZY yüklənir: ilkin render yalnız birinci səhifədir,
    # qalanını JS fraqment endpoint-dən (filtr + axtarış ilə) gətirir.
    questions = annotate_display_numbers(annotate_preview_flags(list(submission.parsed_snapshot or [])))

    return render(
        request,
        "exams/teacher/question_submission_review.html",
        {
            "submission": submission,
            "parsed_questions": questions[:QUESTIONS_PAGE_SIZE],
            "question_flag_counts": snapshot_flag_counts(questions),
            "questions_has_more": len(questions) > QUESTIONS_PAGE_SIZE,
            "questions_page_size": QUESTIONS_PAGE_SIZE,
            "banks": banks,
            "back_url": _profile_section_url("question-submissions"),
        },
    )


@login_required
@require_GET
def question_submission_questions(request, submission_id):
    """Göndərişin sual kartları — AJAX fraqmenti (lazy load + filtr + axtarış).

    Parametrlər: ``offset``/``limit`` (səhifələmə), ``flag``
    (error/warning/clean) və ``q`` (sual/variant mətnində axtarış). Cavab:
    render olunmuş <li> fraqmenti + filtr sayları + has_more.
    """
    _ensure_teacher(request.user)
    organization = _require_organization(request)
    submission = get_object_or_404(QuestionSubmission, id=submission_id, organization=organization)
    if submission.teacher_id != request.user.id and not is_exam_center_user(request.user):
        raise Http404()

    questions = annotate_display_numbers(annotate_preview_flags(list(submission.parsed_snapshot or [])))
    counts = snapshot_flag_counts(questions)

    flag = (request.GET.get("flag") or "").strip().lower()
    if flag not in QUESTION_FLAG_VALUES:
        flag = ""
    query = (request.GET.get("q") or "").strip()[:120]
    filtered = filter_snapshot_questions(questions, flag=flag, query=query)

    try:
        offset = max(0, int(request.GET.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = int(request.GET.get("limit", QUESTIONS_PAGE_SIZE))
    except (TypeError, ValueError):
        limit = QUESTIONS_PAGE_SIZE
    limit = max(1, min(limit, 50))

    window = filtered[offset : offset + limit]
    html = render_to_string(
        "exams/teacher/partials/_question_submission_preview_items.html",
        {"questions": window, "submission": submission},
        request=request,
    )
    return JsonResponse(
        {
            "html": html,
            "returned": len(window),
            "filtered_total": len(filtered),
            "has_more": offset + limit < len(filtered),
            "counts": counts,
        }
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

    return redirect(_profile_section_url("question-submissions"))


__all__ = [
    "question_submission_decide",
    "question_submission_inbox",
    "question_submission_questions",
    "question_submission_review",
]
