from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from apps.exams.features import exam_supervision_enabled, practical_exam_disabled_message, practical_exams_enabled
from apps.exams.models import Exam, ExamAnswer, ExamAnswerFile, ExamAttempt
from apps.exams.services.attempts import (
    _start_or_resume_attempt,
    generate_random_questions_for_attempt,
    get_attempt_limit_result_redirect_url,
)
from apps.exams.services.randomizer import build_shuffled_options
from apps.exams.services.utils import _clear_paint_from_answer, _save_paint_png_to_answer
from apps.exams.validators import ALLOWED_EXTENSIONS as EXAM_ALLOWED_EXTENSIONS
from apps.exams.views.shared.tenant import tenant_scoped_exams
from core.upload_security import randomize_uploaded_filename, validate_uploaded_file

from ._helpers import (
    annotate_attempt_result_visibility,
    append_return_to,
    build_exam_history_url,
    build_exam_result_url,
    current_return_to,
    ensure_student_exam_tenant_context,
    safe_same_origin_redirect_path,
)


def _attempt_answers_queryset(attempt):
    return (
        attempt.answers.select_related("question", "question__exam", "question__block")
        .prefetch_related("question__options", "selected_options", "files")
        .order_by("id")
    )


def _selected_option_ids_from_request(request, question):
    if question.answer_mode == "single":
        raw_option_id = request.POST.get(f"q_{question.id}")
        if not raw_option_id:
            return set()
        try:
            return {int(raw_option_id)}
        except (TypeError, ValueError):
            return set()

    selected_option_ids = set()
    for raw_option_id in request.POST.getlist(f"q_{question.id}"):
        try:
            selected_option_ids.add(int(raw_option_id))
        except (TypeError, ValueError):
            continue
    return selected_option_ids


def _valid_question_option_ids(question):
    return {option.id for option in question.options.all()}


def _correct_question_option_ids(question):
    return {option.id for option in question.options.all() if option.is_correct}


def _save_test_answer_if_changed(answer, question, selected_option_ids, current_selected_option_ids):
    valid_option_ids = _valid_question_option_ids(question)
    selected_option_ids = selected_option_ids & valid_option_ids

    if current_selected_option_ids != selected_option_ids:
        answer.selected_options.set(selected_option_ids)

    correct_option_ids = _correct_question_option_ids(question)
    next_is_correct = bool(correct_option_ids and selected_option_ids == correct_option_ids)
    update_fields = []

    if answer.text_answer:
        answer.text_answer = ""
        update_fields.append("text_answer")

    if answer.is_correct != next_is_correct:
        answer.is_correct = next_is_correct
        update_fields.append("is_correct")

    if (
        getattr(answer, "has_paint", False)
        or getattr(answer, "paint_image", None)
        or getattr(answer, "paint_data_url", None)
    ):
        _clear_paint_from_answer(answer)
        update_fields.extend(["has_paint", "paint_image", "paint_data_url", "paint_updated_at"])

    if update_fields:
        answer.save(update_fields=list(dict.fromkeys(update_fields + ["updated_at"])))


def _save_written_answer_if_changed(request, answer, question):
    update_fields = []
    text = request.POST.get(f"q_{question.id}", "").strip()
    if answer.text_answer != text:
        answer.text_answer = text
        update_fields.append("text_answer")
    if answer.is_correct:
        answer.is_correct = False
        update_fields.append("is_correct")

    files = request.FILES.getlist(f"file_{question.id}[]")
    if files:
        answer.files.all().delete()
        for uploaded_file in files:
            validate_uploaded_file(
                uploaded_file,
                allowed_extensions=EXAM_ALLOWED_EXTENSIONS,
                max_size_mb=10,
            )
            randomize_uploaded_filename(uploaded_file)
            ExamAnswerFile.objects.create(answer=answer, file=uploaded_file)

    paint_enabled = request.POST.get(f"paint_enabled_{question.id}") == "1"
    paint_clear = request.POST.get(f"paint_clear_{question.id}") == "1"
    paint_data_url = (request.POST.get(f"paint_data_{question.id}") or "").strip()

    if not question.paint_enabled_effective:
        if (
            getattr(answer, "has_paint", False)
            or getattr(answer, "paint_image", None)
            or getattr(answer, "paint_data_url", None)
        ):
            _clear_paint_from_answer(answer)
            update_fields.extend(["has_paint", "paint_image", "paint_data_url", "paint_updated_at"])
    elif paint_clear:
        _clear_paint_from_answer(answer)
        update_fields.extend(["has_paint", "paint_image", "paint_data_url", "paint_updated_at"])
    elif paint_enabled and paint_data_url.startswith("data:image/png;base64,"):
        if _save_paint_png_to_answer(answer, paint_data_url):
            update_fields.extend(["paint_image", "paint_updated_at", "has_paint", "paint_data_url"])
    elif not paint_enabled and (getattr(answer, "has_paint", False) or getattr(answer, "paint_image", None)):
        _clear_paint_from_answer(answer)
        update_fields.extend(["has_paint", "paint_image", "paint_data_url", "paint_updated_at"])

    if update_fields:
        answer.save(update_fields=list(dict.fromkeys(update_fields + ["updated_at"])))


def _previous_attempts_for_context(request, exam, attempt):
    previous_attempts = annotate_attempt_result_visibility(
        list(
            ExamAttempt.objects.filter(
                exam=exam,
                user=request.user,
                status__in=["submitted", "graded", "expired"],
            )
            .exclude(id=attempt.id)
            .order_by("-started_at")
        )
    )
    current_path = request.get_full_path()
    for previous_attempt in previous_attempts:
        previous_attempt.result_url = build_exam_result_url(previous_attempt, return_to=current_path)
    return previous_attempts


def _resolve_exam_failure_redirect(request):
    explicit_next = safe_same_origin_redirect_path(request, request.GET.get("next") or request.POST.get("next"))
    if explicit_next:
        return explicit_next

    source_section = (request.GET.get("from_section") or request.POST.get("from_section") or "").strip()
    if source_section == "assigned-exams":
        assigned_type = (request.GET.get("assigned_type") or request.POST.get("assigned_type") or "all").strip().lower()
        allowed_types = {"all", "exams", "courses", "assignments", "labs", "independent"}
        if assigned_type not in allowed_types:
            assigned_type = "all"
        return f"{reverse('accounts:profile')}?section=assigned-exams&assigned_type={assigned_type}"

    return reverse("exams:student_exam_list")


@login_required
def start_exam(request, slug):
    """
    İmtahan başlatma view-ı
    """
    ensure_student_exam_tenant_context(request)
    exam = get_object_or_404(tenant_scoped_exams(request, Exam.objects.filter(is_active=True)), slug=slug)

    # İcazə yoxlaması
    can_start, reason = exam.can_user_start(request.user, code=None)
    if not can_start:
        attempt_limit_result_url = get_attempt_limit_result_redirect_url(request, exam, request.user)
        if attempt_limit_result_url:
            messages.info(
                request,
                pgettext("exams.service.attempt.message", "max_attempts_reached").format(
                    max_attempts=exam.max_attempts_per_user
                ),
            )
            return redirect(attempt_limit_result_url)
        messages.error(request, reason or pgettext("exams.view.access.message", "exam_start_not_allowed"))
        return redirect(_resolve_exam_failure_redirect(request))

    if not exam.questions.filter(is_active=True).exists():
        messages.error(request, pgettext("exams.view.access.message", "exam_has_no_questions"))
        return redirect(_resolve_exam_failure_redirect(request))

    return _start_or_resume_attempt(request, exam)


@login_required
def take_exam(request, slug, attempt_id):
    ensure_student_exam_tenant_context(request)
    attempt = get_object_or_404(
        ExamAttempt,
        id=attempt_id,
        exam__in=tenant_scoped_exams(request),
        exam__slug=slug,
        user=request.user,
    )
    exam = attempt.exam
    return_to = current_return_to(request)
    history_url = build_exam_history_url(exam, return_to=return_to)
    supervision_feature_enabled = exam_supervision_enabled()

    if exam.exam_type == "coding" and not practical_exams_enabled():
        messages.error(request, practical_exam_disabled_message())
        return redirect(_resolve_exam_failure_redirect(request))

    is_manual_supervision_lock = bool(
        supervision_feature_enabled and attempt.supervision_manual_lock and attempt.supervision_status == "locked"
    )
    if not is_manual_supervision_lock:
        attempt.expire_if_time_limit_reached()
    # If the resume window already lapsed before the student got here, finish now.
    if supervision_feature_enabled:
        attempt.expire_if_resume_window_expired()
    if attempt.is_finished:
        return redirect(build_exam_result_url(attempt, return_to=return_to))

    # Student is actually back in the exam → clear the pending "resumed" state
    # so the periodic sweep does not auto-finish an active student.
    if supervision_feature_enabled and attempt.supervision_status == "resumed":
        from apps.exams.services.supervision import mark_student_returned

        mark_student_returned(attempt)

    # Sualları Attempt-ə bağlanmış cavablardan götürürük
    answers = list(_attempt_answers_queryset(attempt))

    if not answers:
        generate_random_questions_for_attempt(attempt)
        answers = list(_attempt_answers_queryset(attempt))

    if not answers:
        message_key = (
            "exam_has_no_questions" if not exam.questions.filter(is_active=True).exists() else "exam_start_failed"
        )
        messages.error(request, pgettext("exams.view.access.message", message_key))
        return redirect(_resolve_exam_failure_redirect(request))

    # Server tərəfli Vaxt Hesablaması
    remaining_seconds = None
    is_time_up = False
    if exam.total_duration_minutes and attempt.started_at:
        now = timezone.now()
        finish_time = attempt.started_at + timedelta(minutes=exam.total_duration_minutes)
        diff = finish_time - now
        total_seconds = diff.total_seconds()
        if total_seconds <= 0:
            is_time_up = True
            remaining_seconds = 0
        else:
            remaining_seconds = int(total_seconds)

    if exam.exam_type == "coding":
        from apps.exams.services.supervision import get_attempt_supervision_status
        from apps.exams.views.student.coding import take_coding_exam

        return take_coding_exam(
            request,
            exam=exam,
            attempt=attempt,
            remaining_seconds=remaining_seconds,
            history_url=history_url,
            previous_attempts=_previous_attempts_for_context(request, exam, attempt),
            supervision=get_attempt_supervision_status(attempt),
        )

    questions = [a.question for a in answers]

    # ✅ Hər cavab üçün seçilmiş option ID-lərini set olaraq saxla
    answers_by_qid = {}
    for a in answers:
        answers_by_qid[a.question_id] = {
            "answer": a,
            "selected_option_ids": {option.id for option in a.selected_options.all()},
        }

    if request.method == "POST":
        action = (request.POST.get("submit_action") or "").strip()
        is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
        autosave_changed_question_ids = None
        raw_changed_question_ids = request.POST.getlist("changed_questions[]") or request.POST.getlist(
            "changed_questions"
        )
        if action == "autosave" and raw_changed_question_ids:
            autosave_changed_question_ids = set()
            for raw_question_id in raw_changed_question_ids:
                try:
                    autosave_changed_question_ids.add(int(raw_question_id))
                except (TypeError, ValueError):
                    continue

        for q in questions:
            if autosave_changed_question_ids is not None and q.id not in autosave_changed_question_ids:
                continue

            answer_data = answers_by_qid.get(q.id) or {}
            ans = answer_data.get("answer")
            if ans is None:
                ans, _ = ExamAnswer.objects.get_or_create(attempt=attempt, question=q)
                answer_data = {"answer": ans, "selected_option_ids": set()}

            if exam.exam_type == "test" and q.answer_mode in ("single", "multiple"):
                _save_test_answer_if_changed(
                    ans,
                    q,
                    _selected_option_ids_from_request(request, q),
                    answer_data.get("selected_option_ids", set()),
                )

            else:  # Yazılı sual
                try:
                    _save_written_answer_if_changed(request, ans, q)
                except ValidationError as exc:
                    if is_ajax:
                        return JsonResponse({"success": False, "error": exc.messages[0]}, status=400)
                    messages.error(request, exc.messages[0])
                    return redirect(
                        append_return_to(
                            reverse("exams:take_exam", kwargs={"slug": exam.slug, "attempt_id": attempt.id}),
                            return_to,
                        )
                    )

        if exam.exam_type == "test" and (action != "autosave" or is_time_up):
            attempt.recalculate_score()

        # ✅ Finish və ya time up
        if action == "finish" or is_time_up:
            status = "expired" if is_time_up else "submitted"
            attempt.mark_finished(status=status)
            if is_ajax:
                return JsonResponse(
                    {
                        "success": True,
                        "finished": True,
                        "redirect_url": build_exam_result_url(attempt, return_to=return_to),
                    }
                )
            return redirect(build_exam_result_url(attempt, return_to=return_to))

        if action == "save_draft" and attempt.status != "draft":
            attempt.status = "draft"
            attempt.save(update_fields=["status"])

        if is_ajax:
            return JsonResponse({"success": True, "finished": False})

        # ✅ Normal POST (AJAX deyilsə) - səhifəni yenilə
        return redirect(
            append_return_to(
                reverse("exams:take_exam", kwargs={"slug": exam.slug, "attempt_id": attempt.id}), return_to
            )
        )

    # GET sorğusu
    # Load supervision status
    from apps.exams.services.supervision import get_attempt_supervision_status

    supervision_data = get_attempt_supervision_status(attempt)

    # If attempt is locked/removed by supervision, show the locked state
    if attempt.supervision_status in ("locked", "removed") and not attempt.is_finished:
        pass  # Template will handle the locked overlay

    previous_attempts = _previous_attempts_for_context(request, exam, attempt)
    q_payload = []
    for q in questions:
        opts = []
        if exam.exam_type == "test" and q.answer_mode in ("single", "multiple"):
            opts = build_shuffled_options(attempt.id, q)
        q_payload.append({"q": q, "opts": opts})

    context = {
        "exam": exam,
        "attempt": attempt,
        "questions": questions,
        "q_payload": q_payload,
        "answers_by_qid": answers_by_qid,
        "remaining_seconds": remaining_seconds,
        "history_url": history_url,
        "previous_attempts": previous_attempts,
        "previous_attempts_count": len(previous_attempts),
        "supervision": supervision_data,
        "exam_autosave_interval_ms": settings.EXAM_AUTOSAVE_INTERVAL_MS,
        "exam_autosave_jitter_ms": settings.EXAM_AUTOSAVE_JITTER_MS,
    }
    return render(request, "exams/student/take_exam.html", context)
