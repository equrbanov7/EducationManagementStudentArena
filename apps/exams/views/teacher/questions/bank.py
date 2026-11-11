"""teacher questions paketi — bank."""

from dataclasses import replace
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods

from apps.exams.constants import EXAM_LANGUAGE_CHOICES, EXAM_LANGUAGE_VALUES
from apps.exams.models import ExamQuestion
from apps.exams.services.access_policy import (
    _ensure_teacher,
    can_manage_exam_questions,
    ensure_can_manage_exam_questions,
)
from apps.exams.services.bank_analysis import analyze_question_bank
from apps.exams.services.question_invariants import MODE_DEACTIVATE, MODE_DELETE, activate_exam_questions
from apps.exams.services.question_versioning import history_question_ids
from apps.exams.views.shared.breadcrumbs import exam_breadcrumbs
from apps.exams.views.shared.tenant import get_teacher_exam_or_404

from ._bank_scope import (
    ALLOWED_FLAGS,
    ALLOWED_SORTS,
    SCOPE_ALL_MATCHING,
    BankFilter,
    filtered_questions,
    ordered_questions,
    wants_all_matching,
)
from ._mutations import PARTIAL_HEADER, finish_mutation_request, run_question_mutation, wants_partial
from ._shared import (
    _append_navigation_query,
    _resolve_question_bank_navigation,
)
from .constants import (
    QUESTION_BANK_SEARCH_MAX_LENGTH,
)


def _bank_post_redirect_url(
    request, exam, *, allowed_sorts, allowed_flags, navigation_from_section, navigation_return_to
):
    """POST-dan sonra bank səhifəsinə qayıdış URL-i (süzgəc/səhifə/naviqasiya saxlanılır)."""
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
    return redirect_url


def _handle_bank_post(request, exam, *, navigation_from_section, navigation_return_to):
    """Sual bankının POST əməlləri (tək / seçilmiş / süzgəcə uyğun hamısı / bütün bank)."""
    # Mutasiyalar (sil/aktivləşdir/deaktivləşdir) sual məzmunudur — final
    # imtahanda yalnız imtahan mərkəzi. GET (baxış) açıq qalır.
    ensure_can_manage_exam_questions(request.user, exam)
    action = (request.POST.get("bulk_action") or "").strip().lower()
    redirect_url = _bank_post_redirect_url(
        request,
        exam,
        allowed_sorts=ALLOWED_SORTS,
        allowed_flags=ALLOWED_FLAGS,
        navigation_from_section=navigation_from_section,
        navigation_return_to=navigation_return_to,
    )
    ctx = "exams.view.questions_bank.message"
    deleted_message = pgettext(ctx, "{count} sual silindi.")

    def mutate(mode, question_ids, message, scope, **extra):
        # QB 2026-09-30: sil/deaktiv yolları «son aktiv suallar» təsdiq axını ilə (bax _mutations.py) —
        # cavab (təsdiq/imtina) qayıdırsa axın orada bitir. 2026-11-11: hər toplu əməl audit olunur.
        return run_question_mutation(
            request,
            exam,
            mode=mode,
            question_ids=question_ids,
            redirect_url=redirect_url,
            success_message=message,
            audit_extra={"scope": scope, **extra},
        )

    def activate(question_ids, scope, **extra):
        updated = activate_exam_questions(
            exam, question_ids, by_user=request.user, request=request, audit_extra={"scope": scope, **extra}
        )
        messages.success(request, pgettext(ctx, "activated_selected").format(count=updated))

    stop_response = None
    if action in {"delete_all", "deactivate_all", "activate_all"}:
        # Sahib 2026-11-11: «Bütün sualları deaktiv et / aktiv et» — silmədən (cavablar və nəticələr qalır).
        question_ids = list(exam.questions.values_list("pk", flat=True))
        if action == "activate_all":
            activate(question_ids, "all")
        elif action == "deactivate_all":
            stop_response = mutate(MODE_DEACTIVATE, question_ids, pgettext(ctx, "deactivated_selected"), "all")
        else:
            stop_response = mutate(MODE_DELETE, question_ids, deleted_message, "all")
    elif action == "delete_language":
        lang = (request.POST.get("language") or "").strip().lower()
        if lang not in EXAM_LANGUAGE_VALUES:
            messages.error(request, pgettext(ctx, "Düzgün dil seçin."))
        else:
            question_ids = list(exam.questions.filter(language=lang).values_list("pk", flat=True))
            stop_response = mutate(MODE_DELETE, question_ids, deleted_message, "language", language=lang)
    elif action in {"deactivate", "activate", "delete"}:
        if wants_all_matching(request.POST):
            # «Bütün N sualı seç»: klient ID göndərmir — süzgəci server özü tətbiq edir (imtahan daxilində).
            flt = BankFilter.from_params(request.POST)
            selected_ids = list(filtered_questions(exam, flt).values_list("pk", flat=True))
            scope, extra = SCOPE_ALL_MATCHING, {"filter": flt.as_audit()}
        else:
            posted = [int(item) for item in request.POST.getlist("selected_question_ids") if item.isdigit()]
            selected_ids = list(ExamQuestion.objects.filter(exam=exam, id__in=posted).values_list("pk", flat=True))
            scope, extra = "selected", {}
        if not selected_ids:
            messages.warning(request, pgettext(ctx, "select_at_least_one"))
        elif action == "deactivate":
            stop_response = mutate(MODE_DEACTIVATE, selected_ids, pgettext(ctx, "deactivated_selected"), scope, **extra)
        elif action == "activate":
            activate(selected_ids, scope, **extra)
        else:
            stop_response = mutate(MODE_DELETE, selected_ids, pgettext(ctx, "deleted_selected"), scope, **extra)
    else:
        messages.error(request, pgettext(ctx, "invalid_bulk_action"))

    if stop_response is not None:
        return stop_response
    return finish_mutation_request(request, redirect_url)


@login_required
@require_http_methods(["GET", "POST"])
def teacher_questions_bank(request, slug):
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    navigation_return_to, navigation_from_section, navigation_query = _resolve_question_bank_navigation(request)

    if request.method == "POST":
        return _handle_bank_post(
            request,
            exam,
            navigation_from_section=navigation_from_section,
            navigation_return_to=navigation_return_to,
        )

    flt = BankFilter.from_params(request.GET)
    search_query, status_filter, sort_filter, language_filter = flt.q, flt.status, flt.sort, flt.language

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

    # Keyfiyyət çipi filtri yalnız analiz aktivdirsə (test imtahanı) tətbiq olunur.
    active_flag = flt.flag if analysis.enabled else ""
    flt = replace(flt, flag=active_flag)
    questions = ordered_questions(
        filtered_questions(exam, flt, analysis=analysis).select_related("block").prefetch_related("options"),
        sort_filter,
    )

    # Stat kartları: əvvəllər Paginator-un öz COUNT-undan ƏLAVƏ 3 ayrı ``.count()``
    # gedirdi (bütün bank, dil daxilində, dil daxilində aktiv) — indi tək
    # şərti aqreqat (audit P1-6, 2026-09-12).
    scope_condition = Q(language=language_filter) if language_filter else Q()
    question_stats = exam.questions.aggregate(
        all_total=Count("id"),
        scoped_total=Count("id", filter=scope_condition) if language_filter else Count("id"),
        scoped_active=Count("id", filter=scope_condition & Q(is_active=True)),
    )
    all_questions_total = question_stats["all_total"] or 0
    total_questions = question_stats["scoped_total"] or 0
    active_questions = question_stats["scoped_active"] or 0
    inactive_questions = max(total_questions - active_questions, 0)

    paginator = Paginator(questions, 12)
    # 2026-11-11: süzgəcsiz (yalnız dil) siyahının sayı elə stat aqreqatındakı rəqəmdir — ayrıca COUNT getmir.
    if not search_query and not active_flag:
        paginator.count = {"all": total_questions, "active": active_questions, "inactive": inactive_questions}[
            status_filter
        ]
    page_obj = paginator.get_page(request.GET.get("page"))
    page_questions = list(page_obj.object_list)
    page_obj.object_list = page_questions

    # Cari səhifədəki suallara analiz nəticəsini (badge/warning üçün) bağlayırıq.
    if analysis.enabled:
        for question in page_questions:
            entry = analysis.analysis_by_id.get(question.id)
            if entry:
                question.analysis_meta = entry["meta"]
                question.analysis_warnings = entry["warnings"]
            else:
                question.analysis_meta = None
                question.analysis_warnings = []

    # Sahib 2026-11-11: cavablanmış sual «Dəyiş (yeni versiya)» ilə dəyişir — səhifə üçün sabit sayda sorğu.
    used_ids = history_question_ids([question.id for question in page_questions]) if page_questions else set()
    versioned = exam.exam_type != "coding"
    for question in page_questions:
        question.has_history = question.id in used_ids
        question.edit_creates_version = versioned and question.has_history

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

    # 2026-11-11: süzgəc / səhifələmə / toplu əməldən sonra səhifə TAM yüklənmir — ``X-QB-Partial: 1``
    # sorğusuna yalnız canlı hissələr (``data-qb-live``) qaytarılır (bax teacher_questions_bank/live.js).
    partial = wants_partial(request)
    response = render(
        request,
        "exams/teacher/partials/qm/_live.html" if partial else "exams/teacher/teacher_questions_bank.html",
        {
            "exam": exam,
            "exam_crumbs": (
                []
                if partial
                else exam_breadcrumbs(
                    request,
                    exam,
                    navigation_query=navigation_query,
                    current=pgettext("exams.template.teacher_questions_bank", "title_questions_bank"),
                )
            ),
            **qm_context,
            "qm_show_bulk_all": True,
            "can_manage_exam_questions": can_manage_exam_questions(request.user, exam),
            "key_correction_url": reverse("appeals:manage_appeals"),
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
    if partial:
        response["Cache-Control"] = "no-store"
    patch_vary_headers(response, [PARTIAL_HEADER])
    return response
