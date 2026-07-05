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
from apps.exams.models import QuestionBank, QuestionSubmission, StudentGroup
from apps.exams.services.access_policy import _ensure_teacher, is_exam_center_user
from apps.exams.services.bulk_workbench import (
    analyze_mcq_bulk,
    parse_points_payload,
    parse_selected_indices,
)
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
        "subject": (request.POST.get("subject") or "").strip(),
        "group_id": (request.POST.get("group_id") or "").strip(),
        "group_label": (request.POST.get("group_label") or "").strip(),
        "teacher_note": (request.POST.get("teacher_note") or "").strip(),
        "language": _normalize_language(request.POST.get("language")),
        "raw_text": request.POST.get("raw_text") or "",
    }


def _teacher_groups(request, organization):
    """Müəllimin bu təşkilatdakı qrupları (dropdown üçün)."""
    from django.db.models import Q

    return (
        StudentGroup.objects.filter(organization=organization)
        .filter(Q(teacher=request.user) | Q(teachers=request.user))
        .distinct()
        .order_by("name")
    )


def _resolve_group(form_state, groups):
    """
    Formadan qrupu həll edir: seçilmiş FK-dırsa (student_group, adı) qaytarır,
    seçilməyibsə sərbəst mətn etiketi. Heç biri yoxdursa ("", "") qayıdır.
    """
    group_id = form_state.get("group_id") or ""
    if group_id.isdigit():
        group = next((g for g in groups if str(g.id) == group_id), None)
        if group is not None:
            return group, group.name
    return None, form_state.get("group_label") or ""


def _preview_context(raw_text):
    """Preview üçün parse nəticəsi + say xülasəsi (müəllim və mərkəz eyni şeyi görür)."""
    parsed, counts = analyze_submission_text(raw_text)
    return {"preview_parsed": parsed, "preview_counts": counts}


# ---------------------------------------------------------------------------
# Müəllim: yeni göndəriş (toplu sual workbench dizaynı ilə)
# ---------------------------------------------------------------------------
@login_required
def question_submission_create(request):
    """
    Yeni göndəriş — sual bankı "toplu əlavə" workbench-i ilə EYNİ UI:
    fayl yüklə (PDF/TXT/PNG/JPG), redaktor, AI generasiya, önizləmə + xəta/
    xəbərdarlıq kartları, sual seçimi. Fərq: sonda "İmtahan mərkəzinə göndər".
    """
    _ensure_teacher(request.user)
    organization = _require_organization(request)
    groups = list(_teacher_groups(request, organization))

    raw_text = ""
    parsed = []
    selected = set()
    from apps.exams.views.teacher.question_library._shared import _empty_analysis

    analysis = _empty_analysis()
    form_state = {
        "title": "",
        "subject": "",
        "group_id": "",
        "group_label": "",
        "teacher_note": "",
        "language": "az",
        "raw_text": "",
    }

    if request.method == "POST":
        action = (request.POST.get("action") or "preview").strip()
        form_state = _form_state(request)

        if action in ("preview", "save"):
            raw_text = form_state["raw_text"]
            uploaded = request.FILES.get("upload_file")
            if uploaded:
                from apps.exams.services.parsing import extract_text_from_upload

                try:
                    raw_text = extract_text_from_upload(uploaded)
                    form_state["raw_text"] = raw_text
                except Exception as exc:  # noqa: BLE001
                    messages.error(
                        request,
                        pgettext("exams.view.question_submission.message", "Fayl oxunmadı: {error}").format(error=exc),
                    )

            analysis = analyze_mcq_bulk(raw_text)
            parsed = analysis["parsed"]

            selected_from_request = parse_selected_indices(request.POST)
            selected = set(range(1, len(parsed) + 1)) if selected_from_request is None else selected_from_request

            if action == "save":
                points_payload = parse_points_payload(request.POST)
                chosen = []
                for index, question in enumerate(parsed, start=1):
                    if index not in selected:
                        continue
                    raw_points = str(points_payload.get(str(index)) or "").strip()
                    if raw_points.isdigit() and int(raw_points) > 0:
                        question["points"] = int(raw_points)
                    chosen.append(question)

                student_group, group_label = _resolve_group(form_state, groups)
                try:
                    submission = submit_question_set(
                        teacher=request.user,
                        organization=organization,
                        title=form_state["title"],
                        subject=form_state["subject"],
                        student_group=student_group,
                        group_label=group_label,
                        language=form_state["language"],
                        raw_text=raw_text,
                        parsed=chosen,
                        teacher_note=form_state["teacher_note"],
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

    context = {
        "exam": None,
        "raw_text": raw_text,
        "parsed": parsed,
        "selected": selected,
        "category_counts": analysis["category_counts"],
        "warning_count": analysis["warning_count"],
        "duplicate_count": analysis["duplicate_count"],
        "error_count": analysis["error_count"],
        "test_level_warnings": analysis["test_level_warnings"],
        "rq_value": "",
        "dp_value": "1",
        "math_token": "",
        # Meta sahələri (workbench-dən kənar kart)
        "teacher_groups": groups,
        "form_state": form_state,
        # Workbench konteksti
        "wb_workbench_key": "question-submission",
        "wb_title": pgettext("exams.template.question_submission", "İmtahan mərkəzinə sual göndər"),
        "wb_subtitle": pgettext(
            "exams.template.question_submission",
            "Sualları yazın və ya fayl yükləyin, önizləyin — xəbərdarlıqları görün, sonra göndərin.",
        ),
        "wb_back_url": _profile_section_url("question-submissions"),
        "wb_back_label": pgettext("exams.template.question_submission", "Göndərişlərə qayıt"),
        "wb_show_settings": False,
        "wb_ai_url": reverse("exams:ai_generate_submission_questions"),
        "wb_ai_context": "test",
        "wb_show_language": True,
        "wb_languages": EXAM_LANGUAGE_CHOICES,
        "wb_selected_language": form_state["language"],
        "wb_show_format": False,
        "wb_format": "test",
        "wb_show_report": False,
        "wb_templates": [],
        "wb_save_label": pgettext("exams.template.question_submission", "İmtahan mərkəzinə göndər"),
    }
    return render(request, "exams/teacher/question_submission_form.html", context)


@login_required
@require_POST
def ai_generate_submission_questions(request):
    """Göndəriş workbench-inin AI kartı — bank/imtahan AI axını ilə eyni mexanizm."""
    _ensure_teacher(request.user)
    _require_organization(request)

    from apps.exams.views.teacher.extract_jobs import start_ai_generation_job

    payload = {
        "exam_title": pgettext("exams.view.question_submission.ai", "Sual göndərişi"),
        "exam_type": "test",
        "prompt_text": request.POST.get("prompt", ""),
        "source_text": (request.POST.get("source_text") or "").strip(),
        "question_count": request.POST.get("question_count") or 5,
        "difficulty": request.POST.get("difficulty") or "medium",
        "block_name": "",
        "language_code": request.LANGUAGE_CODE,
        "user_id": request.user.pk,
    }
    return start_ai_generation_job(
        request,
        payload=payload,
        uploaded=request.FILES.get("source_file") or request.FILES.get("ai_source_file"),
        service_error_message=pgettext(
            "exams.view.question_submission.ai", "AI sual yaratma alınmadı. Bir az sonra yenidən yoxlayın."
        ),
    )


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
            context["teacher_groups"] = list(_teacher_groups(request, organization))
            context["form_state"] = form_state
            try:
                context.update(_preview_context(form_state["raw_text"]))
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
            return render(request, "exams/teacher/question_submission_detail.html", context)

        if action == "resubmit":
            groups = list(_teacher_groups(request, organization))
            student_group, group_label = _resolve_group(form_state, groups)
            try:
                submission = resubmit_question_set(
                    submission,
                    title=form_state["title"],
                    subject=form_state["subject"],
                    student_group=student_group,
                    group_label=group_label,
                    language=form_state["language"],
                    raw_text=form_state["raw_text"],
                    teacher_note=form_state["teacher_note"],
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

    context = _detail_context(submission, can_edit=can_edit, is_reviewer=is_reviewer)
    if can_edit:
        context["teacher_groups"] = list(_teacher_groups(request, organization))
    return render(request, "exams/teacher/question_submission_detail.html", context)


def _detail_context(submission, *, can_edit, is_reviewer):
    return {
        "submission": submission,
        "parsed_questions": submission.parsed_snapshot or [],
        "can_edit": can_edit,
        "is_reviewer": is_reviewer,
        "language_choices": EXAM_LANGUAGE_CHOICES,
        "form_state": {
            "title": submission.title,
            "subject": submission.subject,
            "group_id": str(submission.student_group_id or ""),
            "group_label": submission.group_label,
            "teacher_note": submission.teacher_note,
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
    "ai_generate_submission_questions",
    "question_submission_create",
    "question_submission_decide",
    "question_submission_detail",
    "question_submission_inbox",
    "question_submission_review",
]
