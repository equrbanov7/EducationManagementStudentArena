from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import pgettext, pgettext_lazy

from apps.exams.forms import ExamForm
from apps.exams.models import Exam
from apps.exams.services.attempts import _ensure_teacher
from apps.exams.views.shared.tenant import get_active_organization, get_teacher_exam_or_404, tenant_scoped_exams
from core.tenancy import get_organization_int_id


@login_required
def teacher_exam_list(request):
    """
    Müəllimin yaratdığı bütün imtahanların siyahısı.
    """
    _ensure_teacher(request.user)
    exams = tenant_scoped_exams(request, Exam.objects.filter(author=request.user)).order_by("-created_at")
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
    organization = get_active_organization(request)

    # Əgər slug varsa -> Edit mode
    if slug:
        exam = get_teacher_exam_or_404(request, slug=slug)
        is_editing = True
    else:
        exam = None
        is_editing = False
    is_modal_request = request.GET.get("modal") == "1" or request.POST.get("modal") == "1"

    if request.method == "POST":
        if is_editing:
            # Edit mode
            form = ExamForm(request.POST, instance=exam, user=request.user, organization=organization)
        else:
            # Create mode
            form = ExamForm(request.POST, user=request.user, organization=organization)

        if form.is_valid():
            exam_instance = form.save(commit=False)

            # Yeni imtahanda author-u set et
            if not is_editing:
                exam_instance.author = request.user
            exam_instance.organization_id = get_organization_int_id(organization)

            exam_instance.save()
            form.save_m2m()  # ManyToMany field-ləri saxla

            messages.success(
                request,
                (
                    pgettext_lazy("exams.view.exams.message", "exam_updated")
                    if is_editing
                    else pgettext_lazy("exams.view.exams.message", "exam_created")
                ),
            )
            if is_modal_request:
                return JsonResponse({"success": True, "slug": exam_instance.slug})
            return redirect("exams:teacher_exam_detail", slug=exam_instance.slug)
        if is_modal_request:
            html = render_to_string(
                "exams/teacher/partials/_create_exam_modal_form.html",
                {
                    "form": form,
                    "is_editing": is_editing,
                    "exam": exam,
                },
                request=request,
            )
            return JsonResponse({"success": False, "html": html}, status=400)
    else:
        # GET request
        if is_editing:
            form = ExamForm(instance=exam, user=request.user, organization=organization)
        else:
            form = ExamForm(user=request.user, organization=organization)

    if is_modal_request:
        return render(
            request,
            "exams/teacher/partials/_create_exam_modal_form.html",
            {
                "form": form,
                "exam": exam,
                "is_editing": is_editing,
            },
        )

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
    exam = get_teacher_exam_or_404(request, slug=slug)
    questions = exam.questions.all().order_by("order")
    requested_profile_section = (request.GET.get("from_section") or "").strip()
    valid_profile_sections = {"my-exams", "assigned-exams", "profile-info"}
    if requested_profile_section not in valid_profile_sections:
        requested_profile_section = "my-exams"
    profile_return_url = f"{reverse('accounts:profile')}?section={requested_profile_section}"

    return render(
        request,
        "exams/teacher/teacher_exam_detail.html",
        {
            "exam": exam,
            "questions": questions,
            "profile_return_url": profile_return_url,
        },
    )


@login_required
def toggle_exam_active(request, slug):
    """
    Müəllim imtahanı istənilən vaxt aktiv/deaktiv edə bilsin.
    """
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)

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
    exam = get_teacher_exam_or_404(request, slug=slug)

    if exam.attempts.exists():
        # sadə variant: hazırda cəhd varsa silməyə icazə vermirik
        # istəsən bunu sonradan dəyişərik
        raise PermissionDenied(
            pgettext("exams.view.exams.permission", "delete_blocked_due_to_attempts")
        )

    if request.method == "POST":
        exam.delete()
        return redirect("exams:teacher_exam_list")

    return render(request, "exams/teacher/confirm_delete_exam.html", {"exam": exam})
