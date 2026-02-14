from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from apps.exams.models import Exam, ExamAttempt


@login_required
def exam_result(request, slug, attempt_id):
    """
    Student üçün konkret attempt-in nəticə səhifəsi.
    Yalnız həmin attempt üçün seçilmiş suallar göstərilir.
    """
    exam = get_object_or_404(Exam, slug=slug)
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, exam=exam, user=request.user)

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
        },
    )


@login_required
def student_exam_history(request):
    # Tələbənin bitirdiyi və ya vaxtı bitmiş bütün cəhdləri gətiririk
    attempts = ExamAttempt.objects.filter(user=request.user, status__in=["submitted", "graded", "expired"]).order_by(
        "-started_at"
    )

    context = {"attempts": attempts}
    return render(request, "exams/student/student_exam_history.html", context)
