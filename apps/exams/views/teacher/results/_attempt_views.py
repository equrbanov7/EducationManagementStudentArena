"""results paketi — müəllim nəticə view funksiyaları (qrup)."""

import json
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext, pgettext_lazy
from django.views.decorators.http import require_http_methods

from apps.exams.models import ExamAttempt
from apps.exams.services.access_policy import _ensure_can_view_attempt_results, _ensure_teacher
from apps.exams.services.randomizer import generate_random_questions_for_attempt
from apps.exams.services.result_calculation import calculate_test_attempt_result
from apps.exams.services.review_visibility import attempt_review_window_locked as _attempt_review_window_locked
from apps.exams.services.review_visibility import (
    resolve_exam_attempt_name_visibility as _resolve_attempt_name_visibility,
)
from apps.exams.views.shared.tenant import (
    get_result_viewable_exam_or_404,
    get_teacher_exam_or_404,
    tenant_scoped_exams,
)
from core.permissions import request_has_permission

from ._helpers import (
    _append_query_params,
    _build_anonymous_name,
    _build_answer_review_item,
    _build_attempt_timing_context,
    _resolve_profile_navigation,
    _safe_same_origin_redirect_path,
    _sync_coding_answers_from_final_submissions,
    _user_display_name,
)


@login_required
@require_http_methods(["POST"])
def delete_exam_attempts(request, slug):
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    redirect_url = _safe_same_origin_redirect_path(request, request.POST.get("next"))
    if not redirect_url:
        nav_params = {}
        from_section = (request.POST.get("from_section") or "").strip()
        return_to = _safe_same_origin_redirect_path(request, request.POST.get("return_to"))
        if from_section:
            nav_params["from_section"] = from_section
        if return_to:
            nav_params["return_to"] = return_to
        redirect_url = _append_query_params(
            reverse("exams:teacher_exam_results", kwargs={"slug": exam.slug}),
            **nav_params,
        )

    if not request_has_permission(request, "exam.delete"):
        messages.error(request, pgettext_lazy("exams.view.results.message", "delete_permission_required"))
        return redirect(redirect_url)

    raw_ids = request.POST.getlist("attempt_ids")
    single_attempt_id = (request.POST.get("attempt_id") or "").strip()
    if single_attempt_id:
        raw_ids.append(single_attempt_id)

    attempt_ids = sorted({int(raw_id) for raw_id in raw_ids if str(raw_id).isdigit()})
    if not attempt_ids:
        messages.warning(request, pgettext_lazy("exams.view.results.message", "select_attempt_to_delete"))
        return redirect(redirect_url)

    attempts_qs = exam.attempts.filter(id__in=attempt_ids)
    attempt_count = attempts_qs.count()
    if attempt_count == 0:
        messages.warning(request, pgettext_lazy("exams.view.results.message", "attempt_not_found"))
        return redirect(redirect_url)

    attempts_qs.delete()
    messages.success(
        request,
        pgettext_lazy("exams.view.results.message", "attempts_deleted").format(count=attempt_count),
    )
    return redirect(redirect_url)


@login_required
def teacher_view_attempt(request, slug, attempt_id):
    """
    ✅ Müəllim cavabları YALNIZ GÖRMƏK üçün (bal verə bilməz)
    Test və Yazılı hər ikisi üçün işləyir

    İmtahan mərkəzi rolu da (statistika bölməsindəki "Bax") org daxilində
    istənilən imtahanın nəticəsinə read-only baxa bilir.
    """
    _ensure_can_view_attempt_results(request.user)

    exam = get_result_viewable_exam_or_404(request, slug=slug)
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, exam=exam)
    profile_return_url, navigation_params = _resolve_profile_navigation(request, default_section="my-exams")
    _sync_coding_answers_from_final_submissions(attempt)

    # Cavabları al
    answers_qs = (
        attempt.answers.select_related("question")
        .prefetch_related("files", "selected_options", "question__options")
        .order_by("id")
    )

    if not answers_qs.exists() and not attempt.is_finished:
        generate_random_questions_for_attempt(attempt)
        answers_qs = (
            attempt.answers.select_related("question")
            .prefetch_related("files", "selected_options", "question__options")
            .order_by("id")
        )

    qa_list = [_build_answer_review_item(a) for a in answers_qs]
    test_result = calculate_test_attempt_result(attempt, answers=list(answers_qs)) if exam.exam_type == "test" else None

    # Apellyasiya nəticəsində bal düzəlibsə effektiv balı + düzəlmiş sualları göstər.
    effective_score_info = None
    appeal_bonus_points = 0
    appeal_corrected_qids = {}
    if exam.exam_type == "test":
        from apps.exams import score_adjustments

        effective_score_info = score_adjustments.effective_test_score(attempt)
        _appeal_state = score_adjustments.score_state(attempt)
        appeal_bonus_points = _appeal_state["bonus_points"]
        appeal_corrected_qids = {qid: True for qid in _appeal_state["credited_question_ids"]}
    can_view_name, identity_window_seconds = _resolve_attempt_name_visibility(attempt, current_time=timezone.now())
    if attempt.exam.exam_type == "test":
        student_display = attempt.user.get_full_name() or attempt.user.username
    else:
        anonymous_name = _build_anonymous_name(
            attempt_id=attempt.id,
            user_id=attempt.user_id,
            exam_id=attempt.exam_id,
        )
        student_display = attempt.user.get_full_name() or attempt.user.username if can_view_name else anonymous_name

    search_query = (request.GET.get("q") or "").strip()
    if search_query:
        search_token = search_query.lower()
        filtered = []
        for item in qa_list:
            question = item["question"]
            answer = item["answer"]
            question_text = (question.text or "").lower()
            answer_text = (getattr(answer, "text_answer", "") or "").lower()
            options_text = " ".join(opt.text for opt in question.options.all()).lower()
            if search_token in question_text or search_token in answer_text or search_token in options_text:
                filtered.append(item)
        qa_list = filtered

    questions_page = Paginator(qa_list, 6).get_page(request.GET.get("questions_page"))
    pagination_query = urlencode(
        {
            **navigation_params,
            "q": search_query,
        }
    )
    clear_search_url = _append_query_params(request.path, **navigation_params)

    context = {
        "exam": exam,
        "attempt": attempt,
        "attempt_timing": _build_attempt_timing_context(attempt),
        "qa_list": questions_page.object_list,
        "qa_page": questions_page,
        "qa_search_query": search_query,
        "test_result": test_result,
        "effective_score_info": effective_score_info,
        "appeal_bonus_points": appeal_bonus_points,
        "appeal_corrected_qids": appeal_corrected_qids,
        "qa_pagination_query": pagination_query,
        "qa_clear_search_url": clear_search_url,
        "read_only": True,  # ✅ Yalnız oxumaq rejimi
        "profile_return_url": profile_return_url,
        "source_back_label": pgettext("exams.template.teacher_exam_detail", "action_back"),
        "student_display": student_display,
        "exam_evaluator_display": _user_display_name(exam.author),
        "can_view_student_identity": can_view_name,
        "identity_window_seconds_left": identity_window_seconds,
    }

    return render(request, "exams/teacher/teacher_view_attempt.html", context)


@login_required
def teacher_check_attempt(request, slug, attempt_id):
    """
    Müəllim yazılı/praktiki imtahandakı BİR cəhdi sual-sual yoxlayır.

    ✅ MÜDAFİƏ: 5 dəqiqə keçibsə, yalnız oxumaq üçün yönləndir
    """
    _ensure_teacher(request.user)

    exam = get_teacher_exam_or_404(request, slug=slug)
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, exam=exam)
    profile_return_url, navigation_params = _resolve_profile_navigation(request, default_section="my-exams")
    _sync_coding_answers_from_final_submissions(attempt)
    if navigation_params.get("from_section") == "pending-review":
        results_return_url = profile_return_url
    else:
        results_return_url = _append_query_params(
            reverse("exams:teacher_exam_results", kwargs={"slug": exam.slug}),
            **navigation_params,
        )
    view_attempt_url = _append_query_params(
        reverse("exams:teacher_view_attempt", kwargs={"slug": exam.slug, "attempt_id": attempt.id}),
        **navigation_params,
    )

    # ✅ 5 dəqiqə keçibsə, yalnız "bax" səhifəsinə yönləndir
    if _attempt_review_window_locked(attempt, current_time=timezone.now()):
        messages.warning(
            request,
            pgettext_lazy("exams.view.results.message", "cannot_edit_after_five_minutes"),
        )
        return redirect(view_attempt_url)

    # YALNIZ bu attempt-ə düşən suallar
    answers_qs = (
        attempt.answers.select_related("question")
        .prefetch_related("files", "selected_options", "question__options")
        .order_by("id")
    )

    if not answers_qs.exists() and not attempt.is_finished:
        generate_random_questions_for_attempt(attempt)
        answers_qs = (
            attempt.answers.select_related("question")
            .prefetch_related("files", "selected_options", "question__options")
            .order_by("id")
        )

    qa_list = [_build_answer_review_item(a) for a in answers_qs]
    can_view_name, identity_window_seconds = _resolve_attempt_name_visibility(attempt, current_time=timezone.now())
    if attempt.exam.exam_type == "test":
        student_display = attempt.user.get_full_name() or attempt.user.username
    else:
        anonymous_name = _build_anonymous_name(
            attempt_id=attempt.id,
            user_id=attempt.user_id,
            exam_id=attempt.exam_id,
        )
        student_display = attempt.user.get_full_name() or attempt.user.username if can_view_name else anonymous_name

    if request.method == "POST":
        if not request_has_permission(request, "grade.input"):
            messages.error(
                request,
                pgettext_lazy("exams.view.results.message", "grading_permission_required"),
            )
            return redirect(view_attempt_url)

        # ✅ DOUBLE-CHECK: POST zamanı da yoxla
        if _attempt_review_window_locked(attempt, current_time=timezone.now()):
            messages.error(
                request,
                pgettext_lazy("exams.view.results.message", "cannot_edit_after_five_minutes"),
            )
            return redirect(view_attempt_url)

        total_score = 0
        any_score = False
        from apps.notifications.public import notify_student_about_feedback

        for a in answers_qs:
            q = a.question

            score_raw = (request.POST.get(f"score_{q.id}") or "").strip()
            max_points_raw = (request.POST.get(f"max_points_{q.id}") or "").strip()
            feedback = (request.POST.get(f"feedback_{q.id}") or "").strip()

            if max_points_raw:
                try:
                    max_points_val = int(max_points_raw)
                except ValueError:
                    max_points_val = q.points
                max_points_val = max(1, max_points_val)
            else:
                max_points_val = max(1, q.points)

            if score_raw == "":
                a.teacher_score = None
            else:
                try:
                    score_val = int(score_raw)
                except ValueError:
                    score_val = 0
                score_val = max(0, score_val)
                if score_val > max_points_val:
                    max_points_val = score_val
                a.teacher_score = score_val
                total_score += score_val
                any_score = True

            if q.points != max_points_val:
                q.points = max_points_val
                q.save(update_fields=["points"])

            a.teacher_feedback = feedback
            a.save(update_fields=["teacher_score", "teacher_feedback", "updated_at"])

        # İlk yoxlama vaxtını saxla; 5 dəqiqəlik redaktə pəncərəsi bu vaxtdan hesablanır.
        attempt.teacher_score = total_score if any_score else None
        attempt.checked_by_teacher = True
        if not attempt.teacher_checked_at:
            attempt.teacher_checked_at = timezone.now()
        attempt.save(update_fields=["teacher_score", "checked_by_teacher", "teacher_checked_at"])
        notify_student_about_feedback(
            task=exam,
            student=attempt.user,
            task_kind="exam",
            extra_metadata={"attempt_id": attempt.id},
        )

        messages.success(request, pgettext_lazy("exams.view.results.message", "attempt_checked_success"))
        return redirect(results_return_url)

    context = {
        "exam": exam,
        "attempt": attempt,
        "attempt_timing": _build_attempt_timing_context(attempt),
        "qa_list": qa_list,
        "profile_return_url": profile_return_url,
        "results_return_url": results_return_url,
        "student_display": student_display,
        "exam_creator_display": _user_display_name(exam.author),
        "can_view_student_identity": can_view_name,
        "identity_window_seconds_left": identity_window_seconds,
    }
    return render(request, "exams/teacher/teacher_check_attempt.html", context)


@login_required
@require_http_methods(["POST"])
def ai_grade_answer(request, slug, attempt_id):
    """AJAX endpoint — AI grades a single written answer."""
    from django.http import JsonResponse

    from apps.exams.services.ai_grading import grade_written_answer

    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, exam=exam)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    question_id = data.get("question_id")
    if not question_id:
        return JsonResponse({"ok": False, "error": "question_id required"}, status=400)

    answer = (
        attempt.answers.select_related("question").prefetch_related("files").filter(question_id=question_id).first()
    )
    if not answer:
        return JsonResponse({"ok": False, "error": "Answer not found"}, status=404)

    q = answer.question
    try:
        max_points = int(data.get("max_points", q.points) or q.points)
    except (TypeError, ValueError):
        max_points = q.points
    max_points = max(1, max_points)

    result = grade_written_answer(
        question_text=q.text,
        student_answer=answer.text_answer or "",
        max_points=int(max_points),
        correct_answer=getattr(q, "correct_answer", "") or "",
        language_code=request.LANGUAGE_CODE,
        user_id=request.user.pk,
        answer_files=answer.files.all(),
        paint_image=getattr(answer, "paint_image", None),
    )
    return JsonResponse(result)


@login_required
def teacher_pending_attempts(request):
    """
    Müəllimin bütün imtahanlarından yığılmış,
    yoxlanılmağı gözləyən (Pending) işlərin siyahısı.
    """
    _ensure_teacher(request.user)

    teacher_exams = tenant_scoped_exams(request, request.user.exams.all())

    # Yoxlanılacaq işləri tapırıq
    pending_attempts = (
        ExamAttempt.objects.filter(
            exam__in=teacher_exams,  # Bu müəllimin aktiv tenant imtahanları
            status__in=["submitted", "expired"],  # Bitmiş imtahanlar
            checked_by_teacher=False,  # Hələ yoxlanmayıb
        )
        .exclude(exam__exam_type="test")  # Testləri çıxarırıq
        .select_related("user", "exam")
        .order_by("finished_at")
    )

    now = timezone.now()
    attempts_data = []

    for att in pending_attempts:
        anonymous_name = _build_anonymous_name(attempt_id=att.id, user_id=att.user_id, exam_id=att.exam_id)

        can_view_name, seconds_remaining = _resolve_attempt_name_visibility(att, current_time=now)

        attempts_data.append(
            {
                "attempt": att,
                "anonymous_name": anonymous_name,
                "real_name": att.user.get_full_name() or att.user.username,
                "can_view_name": can_view_name,
                "seconds_remaining": seconds_remaining,
            }
        )

    # ═══════════════════════════════════════════════════════════════════
    # ✅ YENİ: Tip üzrə saylar (Yazılı və Praktiki)
    # ═══════════════════════════════════════════════════════════════════
    essay_count = sum(1 for att in pending_attempts if att.exam.exam_type == "written")
    practical_count = sum(1 for att in pending_attempts if att.exam.exam_type == "coding")

    context = {
        "pending_attempts": pending_attempts,
        "attempts_data": attempts_data,  # ✅ YENİ - anonim adlar
        "essay_count": essay_count,  # ✅ YENİ - yazılı say
        "practical_count": practical_count,  # ✅ YENİ - praktiki say
    }
    return render(request, "exams/teacher/teacher_pending_attempts.html", context)
