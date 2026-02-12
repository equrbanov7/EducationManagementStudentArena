from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from apps.exams.forms import ExamForm
from apps.exams.models import Exam
from apps.exams.services.attempts import _ensure_teacher


@login_required
def teacher_exam_list(request):
    """
    Müəllimin yaratdığı bütün imtahanların siyahısı.
    """
    _ensure_teacher(request.user)
    exams = Exam.objects.filter(author=request.user).order_by("-created_at")
    return render(
        request,
        "exams/teacher/teacher_exam_list.html",
        {
            "exams": exams,
        },
    )


# ((sonra adını teacher_exam_create / teacher_exam_edit edərsən))


@login_required
def createAndEditExamView(request, slug=None):
    """
    Birləşdirilmiş view: Create və Edit
    slug=None -> Yeni imtahan
    slug=<value> -> Mövcud imtahanı redaktə
    """
    _ensure_teacher(request.user)

    # Əgər slug varsa -> Edit mode
    if slug:
        exam = get_object_or_404(Exam, slug=slug, author=request.user)
        is_editing = True
    else:
        exam = None
        is_editing = False

    if request.method == "POST":
        if is_editing:
            # Edit mode
            form = ExamForm(request.POST, instance=exam, user=request.user)
        else:
            # Create mode
            form = ExamForm(request.POST, user=request.user)

        if form.is_valid():
            exam_instance = form.save(commit=False)

            # Yeni imtahanda author-u set et
            if not is_editing:
                exam_instance.author = request.user

            exam_instance.save()
            form.save_m2m()  # ManyToMany field-ləri saxla

            messages.success(
                request,
                (
                    "İmtahan uğurla yeniləndi!"
                    if is_editing
                    else "İmtahan uğurla yaradıldı!"
                ),
            )
            return redirect("exams:teacher_exam_detail", slug=exam_instance.slug)
    else:
        # GET request
        if is_editing:
            form = ExamForm(instance=exam, user=request.user)
        else:
            form = ExamForm(user=request.user)

    return render(
        request,
        "exams/teacher/createAndEditExam.html",
        {
            "form": form,
            "exam": exam,
            "is_editing": is_editing,
        },
    )


@login_required
def teacher_exam_detail(request, slug):
    """
    Müəllim üçün konkret imtahanın detal səhifəsi:
    - məlumat
    - suallar
    - 'Sual əlavə et' düyməsi
    (sonra bura statistikalar, attempts və s. də əlavə ediləcək).
    """
    _ensure_teacher(request.user)
    exam = get_object_or_404(Exam, slug=slug, author=request.user)
    questions = exam.questions.all().order_by("order")

    return render(
        request,
        "exams/teacher/teacher_exam_detail.html",
        {
            "exam": exam,
            "questions": questions,
        },
    )


@login_required
def toggle_exam_active(request, slug):
    """
    Müəllim imtahanı istənilən vaxt aktiv/deaktiv edə bilsin.
    """
    _ensure_teacher(request.user)
    exam = get_object_or_404(Exam, slug=slug, author=request.user)

    if request.method == "POST":
        exam.is_active = not exam.is_active
        exam.save()
    return redirect("exams:teacher_exam_detail", slug=exam.slug)


@login_required
def delete_exam(request, slug):
    """
    İmtahanı silmək – amma əvvəlcə təsdiq istəyəciyik.
    Əgər imtahan üzrə cəhd (attempt) varsa, silməyə icazə vermirik.
    """
    _ensure_teacher(request.user)
    exam = get_object_or_404(Exam, slug=slug, author=request.user)

    if exam.attempts.exists():
        # sadə variant: hazırda cəhd varsa silməyə icazə vermirik
        # istəsən bunu sonradan dəyişərik
        raise PermissionDenied("Bu imtahan üzrə artıq cəhdlər var, silə bilməzsiniz.")

    if request.method == "POST":
        exam.delete()
        return redirect("exams:teacher_exam_list")

    return render(request, "exams/teacher/confirm_delete_exam.html", {"exam": exam})
