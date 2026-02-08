
from datetime import timezone
from pyexpat.errors import messages
from exams.models import Exam

from django.shortcuts import  get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import JsonResponse
from django.urls import reverse
from datetime import timedelta
from exams.models import ExamAttempt, ExamAnswer, ExamQuestionOption, ExamAnswerFile
from exams.services.attempts import _start_or_resume_attempt, generate_random_questions_for_attempt, build_shuffled_options, _clear_paint_from_answer, _save_paint_png_to_answer

 

@login_required
def start_exam(request, slug):
    """
    İmtahan başlatma view-ı
    """
    exam = get_object_or_404(Exam, slug=slug, is_active=True)

    # İcazə yoxlaması
    can_start, reason = exam.can_user_start(request.user, code=None)
    if not can_start:
        messages.error(request, reason or "Bu imtahana başlaya bilmirsiniz.")
        return redirect("student_exam_list")

    return _start_or_resume_attempt(request, exam)


@login_required
def take_exam(request, slug, attempt_id):
    attempt = get_object_or_404(
        ExamAttempt,
        id=attempt_id,
        exam__slug=slug,
        user=request.user,
    )
    exam = attempt.exam

    if attempt.is_finished:
        return redirect("exam_result", slug=exam.slug, attempt_id=attempt.id)

    # Sualları Attempt-ə bağlanmış cavablardan götürürük
    answers_qs = (
        attempt.answers
        .select_related("question")
        .prefetch_related("question__options", "selected_options", "files")
        .order_by("id")
    )

    if not answers_qs.exists():
        generate_random_questions_for_attempt(attempt)
        answers_qs = (
            attempt.answers
            .select_related("question")
            .prefetch_related("question__options", "selected_options","files")
            .order_by("id")
        )

    if not answers_qs.exists():
        answers_qs = attempt.answers.select_related("question").prefetch_related("question__options", "selected_options","files").order_by("id")

    questions = [a.question for a in answers_qs]
    
    # ✅ Hər cavab üçün seçilmiş option ID-lərini set olaraq saxla
    answers_by_qid = {}
    for a in answers_qs:
        answers_by_qid[a.question_id] = {
            'answer': a,
            'selected_option_ids': set(a.selected_options.values_list('id', flat=True))
        }

    # q_payload yaradırıq
    q_payload = []
    for q in questions:
        opts = []
        if exam.exam_type == "test" and q.answer_mode in ("single", "multiple"):
            opts = build_shuffled_options(attempt.id, q)
        q_payload.append({"q": q, "opts": opts})

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

    
    if request.method == "POST":
        action = (request.POST.get("submit_action") or "").strip()
        is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

        # ✅ KRİTİK: Hər sual üçün cavabı yenilə
        for q in questions:
            ans, _ = ExamAnswer.objects.get_or_create(attempt=attempt, question=q)

            if exam.exam_type == "test" and q.answer_mode in ("single", "multiple"):
                # ✅ Əvvəlcə mövcud seçimləri təmizlə
                ans.selected_options.clear()

                if q.answer_mode == "single":
                    opt_id = request.POST.get(f"q_{q.id}")
                    if opt_id:
                        opt = ExamQuestionOption.objects.filter(id=opt_id, question=q).first()
                        if opt:
                            ans.selected_options.add(opt)

                else:  # multiple
                    opt_ids = request.POST.getlist(f"q_{q.id}")
                    if opt_ids:
                        opts = list(ExamQuestionOption.objects.filter(question=q, id__in=opt_ids))
                        if opts:
                            ans.selected_options.add(*opts)

                # ✅ Test cavabları üçün text_answer-ı boşalt
                ans.text_answer = ""
                ans.has_paint = False
                if getattr(ans, "paint_image", None):
                    _clear_paint_from_answer(ans)
                
                # ✅ Auto-evaluate et
                ans.auto_evaluate()
                ans.save()

            else:  # Yazılı sual
                text = request.POST.get(f"q_{q.id}", "").strip()
                ans.text_answer = text
                ans.is_correct = False
                ans.save()

                files = request.FILES.getlist(f"file_{q.id}[]")
                if files:
                    ans.files.all().delete()
                    for f in files:
                        ExamAnswerFile.objects.create(answer=ans, file=f)
                
                # Paint hissəsi
                paint_enabled = (request.POST.get(f"paint_enabled_{q.id}") == "1")
                paint_clear = (request.POST.get(f"paint_clear_{q.id}") == "1")
                paint_data_url = (request.POST.get(f"paint_data_{q.id}") or "").strip()

                if paint_clear:
                    _clear_paint_from_answer(ans)

                if paint_enabled and paint_data_url.startswith("data:image/png;base64,"):
                    _save_paint_png_to_answer(ans, paint_data_url)
                elif not paint_enabled:
                    pass
                
                ans.save()

        # ✅ Test imtahanı üçün score-u yenilə
        if exam.exam_type == "test":
            attempt.recalculate_score()

        # ✅ Finish və ya time up
        if action == "finish" or is_time_up:
            status = "expired" if is_time_up else "submitted"
            attempt.mark_finished(status=status)
            if is_ajax:
                return JsonResponse({
                    "success": True,
                    "finished": True,
                    "redirect_url": reverse("exam_result", kwargs={"slug": exam.slug, "attempt_id": attempt.id})
                })
            return redirect("exam_result", slug=exam.slug, attempt_id=attempt.id)

        # ✅ Draft olaraq saxla (autosave və ya manual save_draft)
        if action in ("autosave", "save_draft"):
            attempt.status = "draft"
            attempt.save(update_fields=["status"])
            
        if is_ajax:
            return JsonResponse({"success": True, "finished": False})
        
        # ✅ Normal POST (AJAX deyilsə) - səhifəni yenilə
        return redirect("take_exam", slug=exam.slug, attempt_id=attempt.id)

    # GET sorğusu
    context = {
        "exam": exam,
        "attempt": attempt,
        "questions": questions,
        "q_payload": q_payload,
        "answers_by_qid": answers_by_qid,
        "remaining_seconds": remaining_seconds,
    }
    return render(request, "blog/take_exam.html", context)

