import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlencode, urlparse

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from apps.exams import score_adjustments
from apps.exams.constants import ATTEMPT_FINISHED_STATUSES
from apps.exams.models import CodingSubmission, ExamAttempt
from apps.exams.services.result_calculation import attach_test_result_summaries, calculate_test_attempt_result
from apps.exams.views.shared.tenant import tenant_scoped_exams

from ._helpers import (
    annotate_attempt_result_visibility,
    append_query_params,
    build_exam_history_url,
    build_exam_result_url,
    current_return_to,
    ensure_student_exam_tenant_context,
    safe_same_origin_redirect_path,
)

FINAL_RESULT_REVIEW_SECONDS = 5 * 60


def _is_final_exam(exam):
    return getattr(exam, "exam_type_extended", "") == "final"


def _is_profile_results_request(request, return_to):
    source_section = (request.GET.get("from_section") or request.POST.get("from_section") or "").strip()
    if source_section == "my-results":
        return True
    return "section=my-results" in (return_to or "")


def _hide_test_answer_correctness_in_cabinet(exam, *, is_profile_results):
    return bool(
        is_profile_results
        and getattr(exam, "exam_type", "") == "test"
        and getattr(exam, "exam_type_extended", "") in {"final", "midterm"}
    )


def _exam_answers_release_locked(exam):
    """
    EXAM-P0-05: imtahan pəncərəsi hələ bağlanmayıbsa (digər tələbələr işləyə
    bilər) düzgün cavab, variant düzgünlüyü və per-sual verdikt açılmır —
    erkən bitirən tələbə cavabları paylaşa bilməsin. end_datetime olmayan
    (həmişə açıq, məşq tipli) imtahanlara kilid tətbiq olunmur.
    """
    if not getattr(exam, "end_datetime", None):
        return False
    return not exam.is_after_end()


def _final_entry_url():
    return reverse("exams:final_exam_entry")


def _final_result_timeout_url(request):
    separator = "&" if request.GET.urlencode() else "?"
    return f"{request.get_full_path()}{separator}final_timeout=1"


def _final_result_remaining_seconds(attempt):
    finished_at = getattr(attempt, "finished_at", None)
    if not finished_at:
        return FINAL_RESULT_REVIEW_SECONDS
    expires_at = finished_at + timedelta(seconds=FINAL_RESULT_REVIEW_SECONDS)
    return max(0, int((expires_at - timezone.now()).total_seconds()))


def _format_score_delta(value):
    try:
        decimal_value = Decimal(str(value if value is not None else "0"))
    except (InvalidOperation, TypeError, ValueError):
        decimal_value = Decimal("0")
    if decimal_value == decimal_value.to_integral_value():
        return str(int(decimal_value))
    return format(decimal_value.normalize(), "f")


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
    is_profile_results = _is_profile_results_request(request, return_to)
    is_final_exam_result = _is_final_exam(exam)
    is_final_center_result = is_final_exam_result and not is_profile_results
    answers_release_locked = _exam_answers_release_locked(exam)
    hide_test_answer_correctness = _hide_test_answer_correctness_in_cabinet(
        exam, is_profile_results=is_profile_results
    ) or (getattr(exam, "exam_type", "") == "test" and answers_release_locked)
    final_result_remaining_seconds = None
    final_result_timeout_url = ""

    if is_final_center_result:
        final_result_remaining_seconds = _final_result_remaining_seconds(attempt)
        final_result_timeout_url = _final_result_timeout_url(request)
        if request.GET.get("final_timeout") == "1" or final_result_remaining_seconds <= 0:
            logout(request)
            return redirect(_final_entry_url())
        back_url = reverse("exams:final_exam_entry")
        history_url = ""

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
            status__in=ATTEMPT_FINISHED_STATUSES,
        )
        .exclude(id=attempt.id)
        .order_by("-started_at")
    )
    previous_attempts = annotate_attempt_result_visibility(previous_attempts)
    attach_test_result_summaries(previous_attempts, bonus_map_fn=score_adjustments.student_visible_bonus_map)
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
    # Hər sual üzrə verdikt (düz/səhv/cavabsız) — cavab detalları gizli olan
    # kabinet rejimində də tələbə öz cavabının nəticəsini görsün. Qayda
    # calculate_test_attempt_result ilə eynidir (prefetch olunmuş cavablar üzərində).
    answer_verdict_by_qid = {}
    # EXAM-P0-05: pəncərə açıq olduqca verdikt də (düz/səhv) sızıntıdır —
    # tələbə öz seçiminin düzgünlüyünü bilib paylaşa bilər.
    if exam.exam_type == "test" and not answers_release_locked:
        for answer in answers:
            # EXAM-P0-03: verdikt də dondurulmuş seçimdən hesablanır ki,
            # bal ilə eyni mənbədən gəlsin.
            frozen_selection = getattr(answer, "selected_option_ids_snapshot", None)
            if frozen_selection is not None:
                selected_ids = {int(option_id) for option_id in frozen_selection}
            else:
                selected_ids = {opt.id for opt in answer.selected_options.all()}
            if not selected_ids:
                answer_verdict_by_qid[answer.question_id] = "unanswered"
                continue
            # EXAM-INTEGRITY-001: snapshot varsa düzgünlük ondan götürülür ki,
            # nəticə səhifəsindəki verdikt qiymətlə eyni (dondurulmuş) mənbədən
            # gəlsin; snapshot yoxdursa canlı suala düşürük.
            snapshot = getattr(answer, "question_snapshot", None)
            snapshot_options = snapshot.get("options") if isinstance(snapshot, dict) else None
            if snapshot_options:
                correct_ids = {opt["id"] for opt in snapshot_options if opt.get("is_correct")}
            else:
                correct_ids = {opt.id for opt in answer.question.options.all() if opt.is_correct}
            answer_verdict_by_qid[answer.question_id] = (
                "correct" if (correct_ids and selected_ids == correct_ids) else "wrong"
            )
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

    can_appeal = score_adjustments.can_create(request, attempt)
    appeal_create_url = reverse("appeals:appeal_create", kwargs={"attempt_id": attempt.id})
    if is_profile_results:
        appeal_create_url = append_query_params(
            appeal_create_url,
            from_section="my-results",
            return_to=return_to or f"{reverse('accounts:profile')}?section=my-results",
        )
    appeal_remaining_seconds = score_adjustments.remaining_window_seconds(attempt)
    # Qəbul olunmuş apellyasiya bonusları tələbəyə yalnız 5 dəqiqəlik redaktə
    # pəncərəsi bağlanandan sonra görünür.
    effective_score_info = (
        score_adjustments.student_visible_effective_test_score(attempt, answers=answers)
        if exam.exam_type == "test"
        else None
    )
    _appeal_state = score_adjustments.student_visible_score_state(attempt)
    appeal_bonus_points = _appeal_state["bonus_points"]
    appeal_bonus_by_qid = {
        question_id: _format_score_delta(delta)
        for question_id, delta in (_appeal_state.get("bonus_by_question_id") or {}).items()
        if delta and delta > 0
    }
    # Hansı sualların balı apellyasiya ilə düzəlib (nəticədə işarələmək üçün).
    appeal_corrected_qids = {
        question_id: True
        for question_id in _appeal_state["credited_question_ids"]
        if question_id in appeal_bonus_by_qid
    }
    # Hər sual üzrə tələbəyə görünən apellyasiya statusu (pending/accepted/rejected)
    # — sual kartında "cavab gözlənilir / qəbul edildi / rədd edildi" çipi üçün.
    appeal_status_by_qid = score_adjustments.student_visible_status_by_qid(attempt)
    appeal_pending_count = sum(1 for status in appeal_status_by_qid.values() if status == "pending")
    # Baş bal göstəricisi də EFFEKTİV balı göstərsin — bonus yalnız aşağıdakı
    # qeyddə yox, əsas faiz/bal blokunda da əks olunmalıdır.
    if test_result is not None and appeal_bonus_points:
        test_result = score_adjustments.apply_bonus(test_result, appeal_bonus_points)

    return render(
        request,
        "exams/student/exam_result.html",
        {
            "exam": exam,
            "attempt": attempt,
            "questions": questions,
            "answers_by_qid": answers_by_qid,
            "answer_has_selection_by_qid": answer_has_selection_by_qid,
            "answer_verdict_by_qid": answer_verdict_by_qid,
            "marked_question_by_qid": {question_id: True for question_id in marked_question_ids},
            "marked_question_count": len(marked_question_ids),
            "marked_question_ids_json": json.dumps(sorted(marked_question_ids)),
            "test_result": test_result,
            "coding_submissions_by_qid": coding_submissions_by_qid,
            "history_url": history_url,
            "back_url": back_url,
            "is_final_exam_result": is_final_center_result,
            "hide_test_answer_correctness": hide_test_answer_correctness,
            "answers_release_locked": answers_release_locked,
            "final_result_remaining_seconds": final_result_remaining_seconds,
            "final_result_timeout_url": final_result_timeout_url,
            "previous_attempts": previous_attempts,
            "previous_attempts_count": len(previous_attempts) + 1,
            "can_appeal": can_appeal,
            "appeal_create_url": appeal_create_url,
            "appeal_remaining_seconds": appeal_remaining_seconds,
            # "Apellyasiyalarım" keçidi yalnız profildən (my-results) baxılan
            # nəticədə görünür — imtahan yenicə bitəndə (midterm/final) yox.
            "my_appeals_url": (reverse("accounts:profile") + "?section=my-appeals") if is_profile_results else "",
            # Yuxarıdakı "Profilə qayıt" düyməsi də yalnız profildən gələndə
            # görünür və HƏMİŞƏ profil "Nəticələrim" bölməsinə aparır
            # (return_to filtr/səhifə parametrlərini saxlayırsa, o üstün tutulur).
            "is_profile_results": is_profile_results,
            "result_profile_back_url": (
                return_to
                if (return_to and "section=my-results" in return_to)
                else reverse("accounts:profile") + "?section=my-results"
            ),
            "effective_score_info": effective_score_info,
            "appeal_bonus_points": appeal_bonus_points,
            "appeal_bonus_points_display": _format_score_delta(appeal_bonus_points),
            "appeal_bonus_by_qid": appeal_bonus_by_qid,
            "appeal_corrected_qids": appeal_corrected_qids,
            "appeal_status_by_qid": appeal_status_by_qid,
            "appeal_pending_count": appeal_pending_count,
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
            status__in=ATTEMPT_FINISHED_STATUSES,
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
    attach_test_result_summaries(visible_attempts, bonus_map_fn=score_adjustments.student_visible_bonus_map)
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
