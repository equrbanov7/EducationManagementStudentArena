import json
from urllib.parse import parse_qs, urlencode, urlparse

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import pgettext

from apps.exams.models import CodingSubmission, ExamAttempt
from apps.exams.services.result_calculation import attach_test_result_summaries, calculate_test_attempt_result
from apps.exams.views.shared.tenant import tenant_scoped_exams

from ._helpers import (
    annotate_attempt_result_visibility,
    build_exam_history_url,
    build_exam_result_url,
    current_return_to,
    ensure_student_exam_tenant_context,
    safe_same_origin_redirect_path,
)


def _default_exam_back_url(exam):
    if exam.course_id:
        return reverse("courses:course_dashboard", kwargs={"course_id": exam.course_id})
    return reverse("exams:student_exam_list")


def _coding_submission_file_items(submission):
    code_files = list(submission.code_files.all())
    if code_files:
        return [
            {
                "name": code_file.name,
                "content": code_file.content or "",
            }
            for code_file in code_files
        ]
    return [
        {
            "name": item.get("name") or "file.txt",
            "content": item.get("content") or "",
        }
        for item in (submission.files or [])
        if isinstance(item, dict)
    ]


def _resolve_result_navigation(request, exam, return_to):
    history_view_path = reverse("exams:student_exam_history")
    default_back_url = _default_exam_back_url(exam)

    if not return_to:
        return default_back_url, build_exam_history_url(exam, return_to=default_back_url)

    if history_view_path in return_to:
        nested_return_to = parse_qs(urlparse(return_to).query).get("return_to", [""])[0]
        safe_nested_return_to = safe_same_origin_redirect_path(request, nested_return_to)
        return safe_nested_return_to or default_back_url, return_to

    return return_to, build_exam_history_url(exam, return_to=return_to)


@login_required
def exam_result(request, slug, attempt_id):
    """
    Student üçün konkret attempt-in nəticə səhifəsi.
    Yalnız həmin attempt üçün seçilmiş suallar göstərilir.
    """
    ensure_student_exam_tenant_context(request)
    exam = get_object_or_404(tenant_scoped_exams(request), slug=slug)
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, exam=exam, user=request.user)
    return_to = current_return_to(request)
    back_url, history_url = _resolve_result_navigation(request, exam, return_to)

    attempt = annotate_attempt_result_visibility([attempt])[0]
    if not attempt.can_view_result:
        message = (
            "Bu imtahanın nəticəsi müəllim tərəfindən tələbələrdən gizlədilib."
            if getattr(attempt, "result_hidden_by_teacher", False)
            else pgettext(
                "exams.view.student.result.message",
                "Result is not available yet. It will appear after the teacher review window closes.",
            )
        )
        messages.info(
            request,
            message,
        )
        return redirect(return_to or f"{reverse('accounts:profile')}?section=my-results")

    previous_attempts = list(
        ExamAttempt.objects.filter(
            user=request.user,
            exam=exam,
            status__in=["submitted", "graded", "expired"],
        )
        .exclude(id=attempt.id)
        .order_by("-started_at")
    )
    previous_attempts = annotate_attempt_result_visibility(previous_attempts)
    attach_test_result_summaries(previous_attempts)
    for previous_attempt in previous_attempts:
        previous_attempt.result_url = build_exam_result_url(previous_attempt, return_to=request.get_full_path())

    # YALNIZ bu attempt-ə düşən suallar:
    answers_qs = (
        attempt.answers.select_related("question")
        .prefetch_related(
            "selected_options",
            "files",
            "question__options",
        )
        .order_by("id")  # attempt yaranma ardıcıllığı ilə
    )

    answers = list(answers_qs)

    # Template-də istifadə üçün:
    questions = [a.question for a in answers]
    answers_by_qid = {a.question_id: a for a in answers}
    answer_has_selection_by_qid = {a.question_id: bool(list(a.selected_options.all())) for a in answers}
    marked_question_ids = {
        int(question_id)
        for question_id in (getattr(attempt, "marked_question_ids", None) or [])
        if str(question_id).isdigit()
    }
    test_result = calculate_test_attempt_result(attempt, answers=answers) if exam.exam_type == "test" else None
    coding_submissions_by_qid = {}
    if exam.exam_type == "coding":
        for submission in (
            CodingSubmission.objects.filter(
                attempt=attempt,
                student=request.user,
                is_final=True,
            )
            .select_related("question", "question__question")
            .prefetch_related("code_files")
            .order_by("question__question__order", "-submitted_at")
        ):
            submission.file_items = _coding_submission_file_items(submission)
            coding_submissions_by_qid.setdefault(submission.question.question_id, submission)

    # ── Apellyasiya konteksti ──────────────────────────────────────────────
    # Lazy import: exams view-larını appeals-dən asılı saxlamamaq üçün.
    from apps.appeals.services import (
        appeal_score_state,
        can_create_appeal,
        effective_test_score,
        remaining_window_seconds,
    )

    can_appeal = can_create_appeal(request, attempt)
    appeal_create_url = reverse("appeals:appeal_create", kwargs={"attempt_id": attempt.id})
    appeal_remaining_seconds = remaining_window_seconds(attempt)
    # Qəbul olunmuş apellyasiya bonusları nəticədə əks olunsun (test üçün).
    effective_score_info = effective_test_score(attempt, answers=answers) if exam.exam_type == "test" else None
    _appeal_state = appeal_score_state(attempt)
    appeal_bonus_points = _appeal_state["bonus_points"]
    # Hansı sualların balı apellyasiya ilə düzəlib (nəticədə işarələmək üçün).
    appeal_corrected_qids = {question_id: True for question_id in _appeal_state["credited_question_ids"]}
    # Baş bal göstəricisi də EFFEKTİV balı göstərsin — bonus yalnız aşağıdakı
    # qeyddə yox, əsas faiz/bal blokunda da əks olunmalıdır.
    if test_result is not None and appeal_bonus_points:
        from apps.appeals.services import apply_bonus_to_test_result

        test_result = apply_bonus_to_test_result(test_result, appeal_bonus_points)

    return render(
        request,
        "exams/student/exam_result.html",
        {
            "exam": exam,
            "attempt": attempt,
            "questions": questions,
            "answers_by_qid": answers_by_qid,
            "answer_has_selection_by_qid": answer_has_selection_by_qid,
            "marked_question_by_qid": {question_id: True for question_id in marked_question_ids},
            "marked_question_count": len(marked_question_ids),
            "marked_question_ids_json": json.dumps(sorted(marked_question_ids)),
            "test_result": test_result,
            "coding_submissions_by_qid": coding_submissions_by_qid,
            "history_url": history_url,
            "back_url": back_url,
            "previous_attempts": previous_attempts,
            "previous_attempts_count": len(previous_attempts) + 1,
            "can_appeal": can_appeal,
            "appeal_create_url": appeal_create_url,
            "appeal_remaining_seconds": appeal_remaining_seconds,
            # Tələbə apellyasiyalarını ayrıca səhifə yox, dashboard bölməsində görür.
            "my_appeals_url": reverse("accounts:profile") + "?section=my-appeals",
            "effective_score_info": effective_score_info,
            "appeal_bonus_points": appeal_bonus_points,
            "appeal_corrected_qids": appeal_corrected_qids,
        },
    )


@login_required
def student_exam_history(request):
    ensure_student_exam_tenant_context(request)
    active_tenant_exams = tenant_scoped_exams(request)
    return_to = current_return_to(request)
    exam_slug = (request.GET.get("exam") or "").strip()
    search_query = (request.GET.get("q") or "").strip()
    exam = None

    attempts = (
        ExamAttempt.objects.filter(
            user=request.user,
            exam__in=active_tenant_exams,
            status__in=["submitted", "graded", "expired"],
        )
        .select_related("exam")
        .prefetch_related("answers__question__options", "answers__selected_options")
        .order_by("-started_at")
    )

    if exam_slug:
        exam = get_object_or_404(active_tenant_exams, slug=exam_slug)
        attempts = attempts.filter(exam=exam)

    if search_query:
        attempts = attempts.filter(Q(exam__title__icontains=search_query))

    total_attempt_count = attempts.count()

    # Pagination
    paginator = Paginator(attempts, 12)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    visible_attempts = annotate_attempt_result_visibility(list(page_obj.object_list))
    attach_test_result_summaries(visible_attempts)
    current_path = request.get_full_path()
    for attempt in visible_attempts:
        attempt.result_url = build_exam_result_url(attempt, return_to=current_path)

    # Build extra_query for pagination links (preserve filters)
    pagination_params = {}
    if exam_slug:
        pagination_params["exam"] = exam_slug
    if search_query:
        pagination_params["q"] = search_query
    if return_to:
        pagination_params["return_to"] = return_to
    extra_query = urlencode(pagination_params)

    back_url = return_to
    if not back_url:
        if exam and exam.course_id:
            back_url = reverse("courses:course_dashboard", kwargs={"course_id": exam.course_id})
        else:
            back_url = reverse("exams:student_exam_list")

    history_max_score = None
    if exam:
        if exam.exam_type == "test":
            history_max_score = 100
        else:
            has_custom_points = exam.default_question_points > 1 or exam.questions.filter(points__gt=1).exists()
            if has_custom_points:
                history_max_score = exam.questions.aggregate(total=Sum("points")).get("total") or 0

    context = {
        "attempts": visible_attempts,
        "exam": exam,
        "back_url": back_url,
        "can_start_exam": bool(exam and exam.can_user_start(request.user, code=None)[0]),
        "history_title": exam.title if exam else "",
        "history_attempt_count": total_attempt_count,
        "history_attempts_left": exam.attempts_left_for(request.user) if exam else None,
        "history_max_score": history_max_score,
        "page_obj": page_obj,
        "search_query": search_query,
        "extra_query": extra_query,
    }
    return render(request, "exams/student/student_exam_history.html", context)
