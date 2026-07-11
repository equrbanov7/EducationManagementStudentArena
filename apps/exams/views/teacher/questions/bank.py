"""teacher questions paketi — bank."""

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.db.models.functions import Lower
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods

from apps.exams.constants import EXAM_LANGUAGE_CHOICES, EXAM_LANGUAGE_VALUES
from apps.exams.models import ExamQuestion
from apps.exams.services.access_policy import _ensure_teacher, ensure_can_manage_exam_questions
from apps.exams.services.bank_analysis import analyze_question_bank
from apps.exams.services.question_invariants import (
    active_exam_question_invariant_message,
    deactivate_exam_questions,
    delete_exam_questions,
)
from apps.exams.views.shared.tenant import get_teacher_exam_or_404

from ._shared import (
    _append_navigation_query,
    _resequence_exam_questions,
    _resolve_question_bank_navigation,
)
from .constants import (
    QUESTION_BANK_SEARCH_MAX_LENGTH,
)


@login_required
@require_http_methods(["GET", "POST"])
def teacher_questions_bank(request, slug):
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    navigation_return_to, navigation_from_section, navigation_query = _resolve_question_bank_navigation(request)

    allowed_statuses = {"all", "active", "inactive"}
    allowed_sorts = {"newest", "oldest", "az", "za"}
    allowed_flags = {"has-error", "has-warning", "has-dup", "has-structure", "has-balance", "is-clean"}

    if request.method == "POST":
        # Mutasiyalar (sil/aktivləşdir/deaktivləşdir) sual məzmunudur — final
        # imtahanda yalnız imtahan mərkəzi. GET (baxış) açıq qalır.
        ensure_can_manage_exam_questions(request.user, exam)
        action = (request.POST.get("bulk_action") or "").strip().lower()

        if action == "delete_all":
            question_ids = list(exam.questions.values_list("pk", flat=True))
            try:
                deleted = delete_exam_questions(exam, question_ids)
            except (ValidationError, IntegrityError):
                messages.error(request, active_exam_question_invariant_message())
            else:
                _resequence_exam_questions(exam)
                messages.success(
                    request,
                    pgettext("exams.view.questions_bank.message", "{count} sual silindi.").format(count=deleted),
                )
        elif action == "delete_language":
            lang = (request.POST.get("language") or "").strip().lower()
            if lang not in EXAM_LANGUAGE_VALUES:
                messages.error(request, pgettext("exams.view.questions_bank.message", "Düzgün dil seçin."))
            else:
                scoped_qs = exam.questions.filter(language=lang)
                question_ids = list(scoped_qs.values_list("pk", flat=True))
                try:
                    deleted = delete_exam_questions(exam, question_ids)
                except (ValidationError, IntegrityError):
                    messages.error(request, active_exam_question_invariant_message())
                else:
                    _resequence_exam_questions(exam)
                    messages.success(
                        request,
                        pgettext("exams.view.questions_bank.message", "{count} sual silindi.").format(count=deleted),
                    )
        else:
            selected_ids = [int(item) for item in request.POST.getlist("selected_question_ids") if item.isdigit()]
            selected_qs = ExamQuestion.objects.filter(exam=exam, id__in=selected_ids)
            selected_count = selected_qs.count()

            if selected_count == 0:
                messages.warning(request, pgettext("exams.view.questions_bank.message", "select_at_least_one"))
            elif action == "deactivate":
                try:
                    updated = deactivate_exam_questions(exam, selected_ids)
                except (ValidationError, IntegrityError):
                    messages.error(request, active_exam_question_invariant_message())
                else:
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
                try:
                    deleted = delete_exam_questions(exam, selected_ids)
                except (ValidationError, IntegrityError):
                    messages.error(request, active_exam_question_invariant_message())
                else:
                    _resequence_exam_questions(exam)
                    messages.success(
                        request,
                        pgettext("exams.view.questions_bank.message", "deleted_selected").format(count=deleted),
                    )
            else:
                messages.error(request, pgettext("exams.view.questions_bank.message", "invalid_bulk_action"))

        redirect_params = {}
        redirect_q = (request.POST.get("q") or "").strip()[:QUESTION_BANK_SEARCH_MAX_LENGTH]
        redirect_status = (request.POST.get("status") or "all").strip().lower()
        redirect_sort = (request.POST.get("sort") or "newest").strip().lower()
        redirect_flag = (request.POST.get("flag") or "").strip().lower()
        redirect_language = (request.POST.get("language") or "").strip().lower()
        redirect_page = (request.POST.get("page") or "").strip()

        if redirect_q:
            redirect_params["q"] = redirect_q
        if redirect_status in {"active", "inactive"}:
            redirect_params["status"] = redirect_status
        if redirect_sort in allowed_sorts:
            redirect_params["sort"] = redirect_sort
        if redirect_flag in allowed_flags:
            redirect_params["flag"] = redirect_flag
        if redirect_language in EXAM_LANGUAGE_VALUES:
            redirect_params["language"] = redirect_language
        if redirect_page.isdigit():
            redirect_params["page"] = redirect_page
        if navigation_from_section:
            redirect_params["from_section"] = navigation_from_section
        if navigation_return_to:
            redirect_params["return_to"] = navigation_return_to

        redirect_url = reverse("exams:teacher_questions_bank", kwargs={"slug": exam.slug})
        if redirect_params:
            redirect_url = f"{redirect_url}?{urlencode(redirect_params)}"
        return redirect(redirect_url)

    search_query = (request.GET.get("q") or "").strip()[:QUESTION_BANK_SEARCH_MAX_LENGTH]
    status_filter = (request.GET.get("status") or "all").strip().lower()
    sort_filter = (request.GET.get("sort") or "newest").strip().lower()
    language_filter = (request.GET.get("language") or "").strip().lower()
    flag_filter = (request.GET.get("flag") or "").strip().lower()
    if status_filter not in allowed_statuses:
        status_filter = "all"
    if sort_filter not in allowed_sorts:
        sort_filter = "newest"
    if language_filter not in EXAM_LANGUAGE_VALUES:
        language_filter = ""
    if flag_filter not in allowed_flags:
        flag_filter = ""

    # Bütün bank üzrə keyfiyyət analizi (yalnız test imtahanları üçün mənalıdır).
    # Stat kartları, filter çipləri və hesabat real ümumi rəqəmləri göstərsin deyə
    # analiz səhifələmədən asılı olmayaraq bütün suallar üzərində işləyir.
    analysis = analyze_question_bank(exam, language=language_filter or None)

    # Excel hesabatının yüklənməsi (mövcud import-report builder təkrar istifadə olunur).
    if analysis.enabled and request.GET.get("export") == "report":
        from apps.exams.views.teacher.question_bank import _build_question_bank_report_xlsx

        try:
            return _build_question_bank_report_xlsx(
                exam=exam,
                raw_text="",
                parsed=analysis.parsed_for_report,
                test_level_warnings=[],
                category_counts=analysis.category_counts,
                warning_count=analysis.warning_count,
                duplicate_count=analysis.duplicate_count,
                error_count=analysis.error_count,
            )
        except RuntimeError as exc:
            messages.error(request, str(exc))

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
    if language_filter:
        questions = questions.filter(language=language_filter)

    # Keyfiyyət çipi filtri (dublikat, xəbərdarlıq, balans və s.) — bütün bank üzrə
    # hesablanmış flag dəstlərinə əsasən server tərəfdə süzgəcləyir.
    active_flag = flag_filter if (flag_filter and analysis.enabled) else ""
    if active_flag:
        flagged = analysis.flagged_ids.get(active_flag, set())
        questions = questions.filter(id__in=flagged)

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

    # Cari səhifədəki suallara analiz nəticəsini (badge/warning üçün) bağlayırıq.
    if analysis.enabled:
        for question in page_obj.object_list:
            entry = analysis.analysis_by_id.get(question.id)
            if entry:
                question.analysis_meta = entry["meta"]
                question.analysis_warnings = entry["warnings"]
            else:
                question.analysis_meta = None
                question.analysis_warnings = []

    all_questions_total = exam.questions.count()
    scoped_questions = exam.questions.all()
    if language_filter:
        scoped_questions = scoped_questions.filter(language=language_filter)
    total_questions = scoped_questions.count()
    active_questions = scoped_questions.filter(is_active=True).count()
    inactive_questions = max(total_questions - active_questions, 0)

    base_query_params = {}
    if search_query:
        base_query_params["q"] = search_query
    if status_filter != "all":
        base_query_params["status"] = status_filter
    if sort_filter != "newest":
        base_query_params["sort"] = sort_filter
    if language_filter:
        base_query_params["language"] = language_filter
    if active_flag:
        base_query_params["flag"] = active_flag
    if navigation_from_section:
        base_query_params["from_section"] = navigation_from_section
    if navigation_return_to:
        base_query_params["return_to"] = navigation_return_to

    # Hesabat/çip linkləri üçün naviqasiya + axtarış kontekstini saxlayan query
    filters_query_params = {key: value for key, value in base_query_params.items() if key != "flag"}

    # Ortaq idarəetmə partial-ı üçün kontekst (imtahan sualları)
    if exam.exam_type == "test":
        qm_bulk_add_url = _append_navigation_query(
            reverse("exams:test_question_bank", kwargs={"slug": exam.slug}), navigation_query
        )
    else:
        qm_bulk_add_url = _append_navigation_query(
            reverse("exams:create_question_bank", kwargs={"slug": exam.slug}), navigation_query
        )
    qm_context = {
        "qm_context": "exam",
        "qm_title": exam.title,
        "qm_subtitle": pgettext("exams.template.teacher_questions_bank", "subtitle_questions_bank"),
        "qm_base_url": reverse("exams:teacher_questions_bank", kwargs={"slug": exam.slug}),
        "qm_back_url": _append_navigation_query(
            reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}), navigation_query
        ),
        "qm_back_label": pgettext("exams.template.teacher_questions_bank", "action_back_exam_detail"),
        "qm_bulk_add_url": qm_bulk_add_url,
        "qm_bulk_add_label": pgettext("exams.template.teacher_questions_bank", "action_bulk_add_blocks"),
        "qm_add_single_url": _append_navigation_query(
            reverse("exams:add_exam_question", kwargs={"slug": exam.slug}), navigation_query
        ),
        "qm_show_language_filter": True,
        "qm_can_delete_language": True,
        "qm_show_delete_all": True,
        "qm_show_report": True,
        "qm_is_owner": False,
        # Word export — imtahan suallarını import-uyğun .docx kimi endir.
        "qm_word_export_url": reverse("exams:exam_questions_word_export", kwargs={"slug": exam.slug}),
    }

    return render(
        request,
        "exams/teacher/teacher_questions_bank.html",
        {
            "exam": exam,
            **qm_context,
            "page_obj": page_obj,
            "search_query": search_query,
            "status_filter": status_filter,
            "sort_filter": sort_filter,
            "language_filter": language_filter,
            "active_flag": active_flag,
            "total_questions": total_questions,
            "all_questions_total": all_questions_total,
            "active_questions": active_questions,
            "inactive_questions": inactive_questions,
            "pagination_query": urlencode(base_query_params),
            "filters_query": urlencode(filters_query_params),
            "analysis_enabled": analysis.enabled,
            "category_counts": analysis.category_counts,
            "duplicate_count": analysis.duplicate_count,
            "error_count": analysis.error_count,
            "warning_count": analysis.warning_count,
            "clean_count": analysis.clean_count,
            "analyzed_total": analysis.total_analyzed,
            "question_bank_navigation_query": navigation_query,
            "navigation_from_section": navigation_from_section,
            "navigation_return_to": navigation_return_to,
            "question_bank_search_max_length": QUESTION_BANK_SEARCH_MAX_LENGTH,
            "language_choices": EXAM_LANGUAGE_CHOICES,
        },
    )
