from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.exams.models import Exam, ExamAttempt
from apps.exams.views.shared.tenant import tenant_scoped_exams
from ._helpers import (
    annotate_attempt_result_visibility,
    build_exam_history_url,
    build_exam_result_url,
    current_return_to,
)


@login_required
def exam_result(request, slug, attempt_id):
    """
    Student üçün konkret attempt-in nəticə səhifəsi.
    Yalnız həmin attempt üçün seçilmiş suallar göstərilir.
    """
    exam = get_object_or_404(tenant_scoped_exams(request), slug=slug)
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, exam=exam, user=request.user)
    return_to = current_return_to(request)
    default_history_url = build_exam_history_url(exam, return_to=return_to)
    history_url = return_to if return_to and reverse("exams:student_exam_history") in return_to else default_history_url

    if not annotate_attempt_result_visibility([attempt])[0].can_view_result:
        messages.info(
            request,
            "Nəticə hələ yekunlaşmayıb. Müəllim üçün düzəliş pəncərəsi bitdikdən sonra görünəcək.",
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

    # Template-də istifadə üçün:
    questions = [a.question for a in answers_qs]
    answers_by_qid = {a.question_id: a for a in answers_qs}

    return render(
        request,
        "exams/student/exam_result.html",
        {
            "exam": exam,
            "attempt": attempt,
            "questions": questions,
            "answers_by_qid": answers_by_qid,
            "history_url": history_url,
            "back_url": return_to or history_url,
            "previous_attempts": previous_attempts,
            "previous_attempts_count": len(previous_attempts) + 1,
        },
    )


@login_required
def student_exam_history(request):
    active_tenant_exams = tenant_scoped_exams(request)
    return_to = current_return_to(request)
    exam_slug = (request.GET.get("exam") or "").strip()
    exam = None

    attempts = (
        ExamAttempt.objects.filter(
            user=request.user,
            exam__in=active_tenant_exams,
            status__in=["submitted", "graded", "expired"],
        )
        .select_related("exam")
        .order_by("-started_at")
    )

    if exam_slug:
        exam = get_object_or_404(active_tenant_exams, slug=exam_slug)
        attempts = attempts.filter(exam=exam)

    attempts = annotate_attempt_result_visibility(list(attempts))
    current_path = request.get_full_path()
    for attempt in attempts:
        attempt.result_url = build_exam_result_url(attempt, return_to=current_path)

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
            history_max_score = exam.questions.aggregate(total=Sum("points")).get("total") or 0

    context = {
        "attempts": attempts,
        "exam": exam,
        "back_url": back_url,
        "can_start_exam": bool(exam and exam.can_user_start(request.user, code=None)[0]),
        "history_title": exam.title if exam else "",
        "history_attempt_count": len(attempts),
        "history_attempts_left": exam.attempts_left_for(request.user) if exam else None,
        "history_max_score": history_max_score,
    }
    return render(request, "exams/student/student_exam_history.html", context)
