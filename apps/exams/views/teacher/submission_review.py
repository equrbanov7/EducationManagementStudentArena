"""
Sual göndərişi — İMTAHAN MƏRKƏZİ tərəfi view-ları.

``submission_inbox.py``-dan ayrılıb (modul ölçü qapısı): baxış (review) +
qərar (qəbul/rədd) + sual siyahısının lazy fraqment endpoint-i. Müəllim tərəfi
(yeni göndəriş, detal/redaktə) ``submission_inbox.py``-dadır.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET, require_POST

from apps.exams.models import QuestionBank, QuestionSubmission
from apps.exams.services.access_policy import _ensure_teacher, is_exam_center_user
from apps.exams.services.question_chair_review import MIN_REASON_LENGTH
from apps.exams.services.question_chair_units import can_review_submission_as_chair
from apps.exams.services.question_submission import (
    accept_submission,
    ensure_can_review_submission,
    open_center_review,
    reject_submission,
    request_center_revision,
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
from apps.exams.views.teacher.submission_page_ui import ROLE_CENTER, page_context
from core.permissions import request_has_permission

#: 2026-10-13 (rol auditi B1): qəbul / rədd / düzəlişə qaytarma QƏRARDIR — əvvəl mərkəz rolu ADI
#: (``is_exam_center_user``) kifayət edirdi, işçi və RİM əməkdaşı da müəllimin suallarını banka yazırdı.
#: İndi açar lazımdır (şablonda rəhbərdə); işçi göndərişi və sualları GÖRÜR. Kataloq açarı:
#: ``organizations/permissions_role_audit.py`` (xüsusi modul — sətir burada lokal saxlanılır).
PERM_EXAM_CENTER_DECIDE = "exam_center.decide"


def _can_decide_as_center(request):
    # Görünüş qapısı (``ensure_can_review_submission``) çağırandadır; burada yalnız qərar açarı.
    return request_has_permission(request, PERM_EXAM_CENTER_DECIDE)


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
        QuestionSubmission.objects.select_related(
            "teacher", "accepted_bank", "subject_ref", "chair_unit", "chair_reviewer", "reviewer"
        ),
        id=submission_id,
        organization=organization,
    )
    ensure_can_review_submission(request.user, submission)
    can_decide = _can_decide_as_center(request)
    # Mərkəz göndərişi AÇDI — iz lentinə düşür (chair_approved → center_review). Yalnız qərar verə
    # bilən açanda: yalnız-oxu işçinin baxışı «mərkəz baxır» statusu yaratmamalıdır (rol auditi B1).
    if can_decide:
        open_center_review(submission, reviewer=request.user)

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
    # ``actor_label`` sətirdə saxlanılır — istifadəçi cədvəlinə JOIN lazım deyil.
    events = list(submission.events.all())

    context = {
        "submission": submission,
        "can_decide": can_decide,
        "parsed_questions": questions[:QUESTIONS_PAGE_SIZE],
        "question_flag_counts": snapshot_flag_counts(questions),
        "questions_has_more": len(questions) > QUESTIONS_PAGE_SIZE,
        "questions_page_size": QUESTIONS_PAGE_SIZE,
        "banks": banks,
        # Kafedra qərarı və tam zaman xətti mərkəzin ekranında AÇIQ görünür.
        "submission_events": events,
        "min_reason_length": MIN_REASON_LENGTH,
        "back_url": _profile_section_url("question-submissions"),
        # Paket C 2026-10-17: baxış profil örtüyünün içində açılır (sidebar qalır).
        "embed_active_section": "question-submissions",
        "embed_section_title": submission.title,
        "is_reviewer": True,
    }
    context.update(page_context(submission, events, role=ROLE_CENTER, can_decide=can_decide))
    return render(request, "exams/teacher/question_submission_review.html", context)


@login_required
@require_GET
def question_submission_questions(request, submission_id):
    """Göndərişin sual kartları — AJAX fraqmenti (lazy load + filtr + axtarış).

    Parametrlər: ``offset``/``limit`` (səhifələmə), ``flag``
    (error/warning/clean) və ``q`` (sual/variant mətnində axtarış). Cavab:
    render olunmuş <li> fraqmenti + filtr sayları + has_more.
    """
    organization = _require_organization(request)
    submission = get_object_or_404(QuestionSubmission, id=submission_id, organization=organization)
    is_center = is_exam_center_user(request.user) and submission.has_reached_center
    if (
        submission.teacher_id != request.user.id
        and not is_center
        and not can_review_submission_as_chair(request.user, submission)
    ):
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
    if not _can_decide_as_center(request):
        raise PermissionDenied(
            pgettext("exams.view.question_submission.permission", "Göndərişə qərar vermək səlahiyyətiniz yoxdur.")
        )

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
        elif decision in ("reject", "revision"):
            if len(note) < MIN_REASON_LENGTH:
                messages.error(
                    request,
                    pgettext(
                        "exams.view.question_submission.message",
                        "Rədd/düzəliş üçün müəllimə ən azı {count} simvolluq qeyd yazın — nəyi düzəltməlidir.",
                    ).format(count=MIN_REASON_LENGTH),
                )
                return redirect("exams:question_submission_review", submission_id=submission.id)
            if decision == "revision":
                request_center_revision(submission, reviewer=request.user, note=note)
                messages.success(
                    request,
                    pgettext(
                        "exams.view.question_submission.message",
                        "Düzəliş tələbi müəllimə göndərildi — düzəlişdən sonra yenidən kafedradan keçəcək.",
                    ),
                )
            else:
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
