from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.exams.forms import ExamQuestionCreateForm
from apps.exams.models import ExamQuestion, QuestionBlock
from apps.exams.services.attempts import _ensure_teacher
from apps.exams.views.shared.tenant import get_teacher_exam_or_404


@login_required
def add_exam_question(request, slug):
    """
    Müəllim imtahana sual əlavə edir.
    Test imtahanı üçün variantlar da eyni formda daxil olunur.
    Yazılı imtahan üçün yalnız sual mətni + ideal cavab hissəsi istifadə edilir.
    """
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    blocks = QuestionBlock.objects.filter(exam=exam).order_by("order")

    if request.method == "POST":
        form = ExamQuestionCreateForm(request.POST, request.FILES, exam_type=exam.exam_type, subject_blocks=blocks)
        if form.is_valid():
            # Sualı yaradıq
            last_q = exam.questions.order_by("-order").first()
            next_order = (last_q.order + 1) if last_q else 1

            question = form.save(commit=False)
            question.exam = exam
            question.order = next_order

            # Yazılı imtahan üçün answer_mode-u zorla "single" edə bilərik
            if exam.exam_type == "written":
                question.answer_mode = "single"

            question.save()

            # Əgər exam tipi testdirsə → variantları yarat
            if exam.exam_type == "test":
                form.create_options(question)

            # hansı düyməyə basıldığını yoxlayaq
            if "save_and_continue" in request.POST:
                # eyni imtahan üçün yenidən boş formada aç
                return redirect("exams:add_exam_question", slug=exam.slug)
            else:
                # Sadəcə imtahan detalına qayıt
                return redirect("exams:teacher_exam_detail", slug=exam.slug)
    else:
        form = ExamQuestionCreateForm(exam_type=exam.exam_type, subject_blocks=blocks)

    return render(
        request,
        "exams/teacher/add_exam_question.html",
        {
            "exam": exam,
            "form": form,
        },
    )


@login_required
def edit_exam_question(request, slug, question_id):
    """
    Mövcud sualı redaktə etmək (text, blok, cavab rejimi, vaxt, variantlar və s.).
    """
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    question = get_object_or_404(ExamQuestion, id=question_id, exam=exam)

    # --- DÜZƏLİŞ: Dropdown-un dolması üçün blokları çağırırıq ---
    blocks = QuestionBlock.objects.filter(exam=exam).order_by("order")
    # ------------------------------------------------------------

    if request.method == "POST":
        form = ExamQuestionCreateForm(
            request.POST,
            request.FILES,
            instance=question,
            exam_type=exam.exam_type,
            subject_blocks=blocks,  # <--- Vacib: Blokları formaya ötürürük
        )
        if form.is_valid():
            q = form.save(commit=False)
            q.exam = exam

            if exam.exam_type == "written":
                q.answer_mode = "single"

            q.save()

            if exam.exam_type == "test":
                form.save_options(q)

            if "save_and_continue" in request.POST:
                return redirect("exams:add_exam_question", slug=exam.slug)

            return redirect("exams:teacher_exam_detail", slug=exam.slug)
    else:
        form = ExamQuestionCreateForm(
            instance=question,
            exam_type=exam.exam_type,
            subject_blocks=blocks,  # <--- Vacib: Blokları formaya ötürürük
        )

    return render(
        request,
        "exams/teacher/add_exam_question.html",
        {
            "exam": exam,
            "form": form,
            "editing": True,
            "question": question,
        },
    )


@login_required
def delete_exam_question(request, slug, question_id):
    """
    Sualı silmək – əvvəlcə təsdiq istənilir.
    """
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    question = get_object_or_404(ExamQuestion, id=question_id, exam=exam)

    if request.method == "POST":
        question.delete()
        return redirect("exams:teacher_exam_detail", slug=exam.slug)

    return render(
        request,
        "exams/teacher/confirm_delete_question.html",
        {
            "exam": exam,
            "question": question,
        },
    )
