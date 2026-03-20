from urllib.parse import urlencode, urlsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models.functions import Lower
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods

from apps.exams.forms import ExamQuestionCreateForm
from apps.exams.models import ExamQuestion, QuestionBlock
from apps.exams.services.attempts import _ensure_teacher
from apps.exams.views.shared.tenant import get_teacher_exam_or_404


def _is_question_modal_request(request):
    return request.GET.get("modal") == "1" or request.POST.get("modal") == "1"


def _safe_same_origin_redirect_path(request, candidate_url):
    raw_url = (candidate_url or "").strip()
    if not raw_url:
        return ""

    if not url_has_allowed_host_and_scheme(
        raw_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return ""

    parsed = urlsplit(raw_url)
    if parsed.netloc and parsed.netloc != request.get_host():
        return ""

    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    return f"{path}{query}{fragment}"


def _resolve_question_bank_navigation(request):
    requested_profile_section = (request.GET.get("from_section") or request.POST.get("from_section") or "").strip()
    valid_profile_sections = {
        "my-exams",
        "assigned-exams",
        "profile-info",
        "my-courses",
        "assigned-courses",
        "courses",
        "pending-review",
        "review-results",
    }
    if requested_profile_section not in valid_profile_sections:
        requested_profile_section = ""

    return_to = _safe_same_origin_redirect_path(
        request,
        request.GET.get("return_to") or request.POST.get("return_to"),
    )

    nav_params = {}
    if requested_profile_section:
        nav_params["from_section"] = requested_profile_section
    if return_to:
        nav_params["return_to"] = return_to

    return return_to, requested_profile_section, urlencode(nav_params)


def _append_navigation_query(path, navigation_query):
    if not navigation_query:
        return path
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{navigation_query}"


def _render_question_form_html(request, *, exam, form, editing=False, question=None, navigation_query=""):
    return render_to_string(
        "exams/teacher/partials/_question_form.html",
        {
            "exam": exam,
            "form": form,
            "editing": editing,
            "question": question,
            "is_modal": True,
            "question_navigation_query": navigation_query,
        },
        request=request,
    )


@login_required
@require_http_methods(["GET", "POST"])
def teacher_questions_bank(request, slug):
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    _, _, navigation_query = _resolve_question_bank_navigation(request)

    allowed_statuses = {"all", "active", "inactive"}
    allowed_sorts = {"newest", "oldest", "az", "za"}

    if request.method == "POST":
        action = (request.POST.get("bulk_action") or "").strip().lower()
        selected_ids = [int(item) for item in request.POST.getlist("selected_question_ids") if item.isdigit()]
        selected_qs = ExamQuestion.objects.filter(exam=exam, id__in=selected_ids)
        selected_count = selected_qs.count()

        if selected_count == 0:
            messages.warning(request, pgettext("exams.view.questions_bank.message", "select_at_least_one"))
        elif action == "deactivate":
            updated = selected_qs.update(is_active=False)
            messages.success(
                request,
                pgettext("exams.view.questions_bank.message", "deactivated_selected").format(count=updated),
            )
        elif action == "activate":
            updated = selected_qs.update(is_active=True)
            messages.success(
                request,
                pgettext("exams.view.questions_bank.message", "activated_selected").format(count=updated),
            )
        elif action == "delete":
            deleted = selected_count
            selected_qs.delete()
            messages.success(
                request,
                pgettext("exams.view.questions_bank.message", "deleted_selected").format(count=deleted),
            )
        else:
            messages.error(request, pgettext("exams.view.questions_bank.message", "invalid_bulk_action"))

        redirect_params = {}
        redirect_q = (request.POST.get("q") or "").strip()
        redirect_status = (request.POST.get("status") or "all").strip().lower()
        redirect_sort = (request.POST.get("sort") or "newest").strip().lower()
        redirect_page = (request.POST.get("page") or "").strip()

        if redirect_q:
            redirect_params["q"] = redirect_q
        if redirect_status in {"active", "inactive"}:
            redirect_params["status"] = redirect_status
        if redirect_sort in allowed_sorts:
            redirect_params["sort"] = redirect_sort
        if redirect_page.isdigit():
            redirect_params["page"] = redirect_page
        if request.POST.get("from_section"):
            redirect_params["from_section"] = request.POST.get("from_section")
        safe_return_to = _safe_same_origin_redirect_path(request, request.POST.get("return_to"))
        if safe_return_to:
            redirect_params["return_to"] = safe_return_to

        redirect_url = reverse("exams:teacher_questions_bank", kwargs={"slug": exam.slug})
        if redirect_params:
            redirect_url = f"{redirect_url}?{urlencode(redirect_params)}"
        return redirect(redirect_url)

    search_query = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or "all").strip().lower()
    sort_filter = (request.GET.get("sort") or "newest").strip().lower()
    if status_filter not in allowed_statuses:
        status_filter = "all"
    if sort_filter not in allowed_sorts:
        sort_filter = "newest"

    questions = exam.questions.select_related("block").prefetch_related("options")

    if search_query:
        matched_ids = (
            exam.questions.filter(
                Q(text__icontains=search_query)
                | Q(block__name__icontains=search_query)
                | Q(options__text__icontains=search_query)
            )
            .values_list("id", flat=True)
            .distinct()
        )
        questions = questions.filter(id__in=matched_ids)

    if status_filter == "active":
        questions = questions.filter(is_active=True)
    elif status_filter == "inactive":
        questions = questions.filter(is_active=False)

    if sort_filter == "oldest":
        questions = questions.order_by("created_at", "id")
    elif sort_filter == "az":
        questions = questions.order_by(Lower("text"), "id")
    elif sort_filter == "za":
        questions = questions.order_by(Lower("text").desc(), "id")
    else:
        questions = questions.order_by("-created_at", "-id")

    paginator = Paginator(questions, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    total_questions = exam.questions.count()
    active_questions = exam.questions.filter(is_active=True).count()
    inactive_questions = max(total_questions - active_questions, 0)

    base_query_params = {}
    if search_query:
        base_query_params["q"] = search_query
    if status_filter != "all":
        base_query_params["status"] = status_filter
    if sort_filter != "newest":
        base_query_params["sort"] = sort_filter
    if request.GET.get("from_section"):
        base_query_params["from_section"] = request.GET.get("from_section")
    safe_return_to = _safe_same_origin_redirect_path(request, request.GET.get("return_to"))
    if safe_return_to:
        base_query_params["return_to"] = safe_return_to

    return render(
        request,
        "exams/teacher/teacher_questions_bank.html",
        {
            "exam": exam,
            "page_obj": page_obj,
            "search_query": search_query,
            "status_filter": status_filter,
            "sort_filter": sort_filter,
            "total_questions": total_questions,
            "active_questions": active_questions,
            "inactive_questions": inactive_questions,
            "pagination_query": urlencode(base_query_params),
            "question_bank_navigation_query": navigation_query,
        },
    )


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
    is_modal_request = _is_question_modal_request(request)
    _, _, navigation_query = _resolve_question_bank_navigation(request)

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

            if is_modal_request:
                return JsonResponse({"success": True, "question_id": question.id})

            # hansı düyməyə basıldığını yoxlayaq
            if "save_and_continue" in request.POST:
                # eyni imtahan üçün yenidən boş formada aç
                return redirect(
                    _append_navigation_query(
                        reverse("exams:add_exam_question", kwargs={"slug": exam.slug}), navigation_query
                    )
                )
            else:
                # Sadəcə imtahan detalına qayıt
                return redirect(
                    _append_navigation_query(
                        reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}),
                        navigation_query,
                    )
                )
        if is_modal_request:
            return JsonResponse(
                {
                    "success": False,
                    "html": _render_question_form_html(
                        request,
                        exam=exam,
                        form=form,
                        editing=False,
                        navigation_query=navigation_query,
                    ),
                },
                status=400,
            )
    else:
        form = ExamQuestionCreateForm(exam_type=exam.exam_type, subject_blocks=blocks)

    if is_modal_request:
        return render(
            request,
            "exams/teacher/partials/_question_form.html",
            {
                "exam": exam,
                "form": form,
                "editing": False,
                "is_modal": True,
                "question_navigation_query": navigation_query,
            },
        )

    return render(
        request,
        "exams/teacher/add_exam_question.html",
        {
            "exam": exam,
            "form": form,
            "editing": False,
            "is_modal": False,
            "question_navigation_query": navigation_query,
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
    is_modal_request = _is_question_modal_request(request)
    _, _, navigation_query = _resolve_question_bank_navigation(request)

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

            if is_modal_request:
                return JsonResponse({"success": True, "question_id": q.id})

            if "save_and_continue" in request.POST:
                return redirect(
                    _append_navigation_query(
                        reverse("exams:add_exam_question", kwargs={"slug": exam.slug}), navigation_query
                    )
                )

            return redirect(
                _append_navigation_query(
                    reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}),
                    navigation_query,
                )
            )
        if is_modal_request:
            return JsonResponse(
                {
                    "success": False,
                    "html": _render_question_form_html(
                        request,
                        exam=exam,
                        form=form,
                        editing=True,
                        question=question,
                        navigation_query=navigation_query,
                    ),
                },
                status=400,
            )
    else:
        form = ExamQuestionCreateForm(
            instance=question,
            exam_type=exam.exam_type,
            subject_blocks=blocks,  # <--- Vacib: Blokları formaya ötürürük
        )

    if is_modal_request:
        return render(
            request,
            "exams/teacher/partials/_question_form.html",
            {
                "exam": exam,
                "form": form,
                "editing": True,
                "question": question,
                "is_modal": True,
                "question_navigation_query": navigation_query,
            },
        )

    return render(
        request,
        "exams/teacher/add_exam_question.html",
        {
            "exam": exam,
            "form": form,
            "editing": True,
            "question": question,
            "is_modal": False,
            "question_navigation_query": navigation_query,
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
    _, _, navigation_query = _resolve_question_bank_navigation(request)

    if request.method == "POST":
        question.delete()
        return redirect(
            _append_navigation_query(
                reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}),
                navigation_query,
            )
        )

    return render(
        request,
        "exams/teacher/confirm_delete_question.html",
        {
            "exam": exam,
            "question": question,
        },
    )
