"""Profil "question-bank" bölməsi üçün context-fragment qurucusu."""

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import pgettext

from apps.accounts.views._helpers.formatting import _append_query_params, _query_string


def _inactive_defaults() -> dict:
    """Bölmə aktiv olmayanda main.py-dakı default dəyərlərlə eyni."""
    return {
        "question_bank_banks": [],
        "question_bank_page_obj": None,
        "question_bank_search_query": "",
        "question_bank_pagination_query": _query_string(section="question-bank"),
        "question_bank_back_url": _append_query_params(reverse("accounts:profile"), section="question-bank"),
        "question_bank_language_choices": [],
        "question_bank_default_type_choices": [],
        "question_bank_exam_kind_choices": [],
        "question_bank_kind_filter": "",
        "question_bank_kind_pills": [],
        "question_bank_can_create": False,
    }


def _kind_pills(search_query: str, kind_filter: str, choices) -> list:
    """İmtahan növü filtr pillləri (Hamısı / Final / Midterm / Quiz / Ümumi).

    Hər pill profil bölməsinə tam keçiddir — aktiv pillə təkrar klik filtri
    sıfırlamır (Hamısı bunun üçündür), axtarış sorğusu qorunur.
    """
    ctx = "accounts.profile.question_bank"
    pills = [("", pgettext(ctx, "Hamısı"))]
    pills.extend((value, label) for value, label in choices)
    pills.append(("general", pgettext(ctx, "Ümumi")))
    result = []
    for value, label in pills:
        params = [("section", "question-bank")]
        if search_query:
            params.append(("bank_search", search_query))
        if value:
            params.append(("bank_kind", value))
        result.append(
            {
                "value": value,
                "label": label,
                "is_active": kind_filter == value,
                "query": urlencode(params),
            }
        )
    return result


def build_question_bank_context(request, *, allowed_sections, active_section) -> dict:
    """Sual bankı bölməsi üçün ``context`` açarlarını qaytarır. Bölmə aktiv
    deyilsə main.py default-ları ilə eyni dəyərləri verir (davranış dəyişmir)."""
    if not (active_section == "question-bank" and "question-bank" in allowed_sections):
        return _inactive_defaults()

    from apps.exams.constants import QUESTION_EXAM_KIND_CHOICES, QUESTION_EXAM_KIND_VALUES
    from apps.exams.models import QuestionBank
    from apps.exams.public import EXAM_LANGUAGE_CHOICES, accessible_banks, can_create_question_bank
    from core.tenancy import get_request_organization

    organization = get_request_organization(request)
    search_query = (request.GET.get("bank_search") or "").strip()[:120]
    kind_filter = (request.GET.get("bank_kind") or "").strip().lower()
    if kind_filter not in QUESTION_EXAM_KIND_VALUES and kind_filter != "general":
        kind_filter = ""

    qs = (
        accessible_banks(request.user, organization)
        .select_related("subject_ref", "source_teacher")
        .annotate(lib_count=Count("library_questions", filter=Q(library_questions__is_active=True)))
    )
    if search_query:
        qs = qs.filter(
            Q(name__icontains=search_query)
            | Q(subject__icontains=search_query)
            | Q(subject_ref__name__icontains=search_query)
            | Q(subject_ref__code__icontains=search_query)
            | Q(source_teacher__first_name__icontains=search_query)
            | Q(source_teacher__last_name__icontains=search_query)
            | Q(source_teacher__username__icontains=search_query)
        )
    if kind_filter == "general":
        qs = qs.filter(exam_kind="")
    elif kind_filter:
        qs = qs.filter(exam_kind=kind_filter)
    qs = qs.order_by("-created_at")

    page_obj = Paginator(qs, 9).get_page(request.GET.get("bank_page"))
    return {
        "question_bank_banks": page_obj.object_list,
        "question_bank_page_obj": page_obj,
        "question_bank_search_query": search_query,
        "question_bank_pagination_query": _query_string(
            section="question-bank", bank_search=search_query, bank_kind=kind_filter
        ),
        "question_bank_back_url": _append_query_params(
            reverse("accounts:profile"),
            section="question-bank",
            bank_search=search_query,
            bank_kind=kind_filter,
            bank_page=request.GET.get("bank_page"),
        ),
        "question_bank_language_choices": EXAM_LANGUAGE_CHOICES,
        "question_bank_default_type_choices": QuestionBank.DEFAULT_QUESTION_TYPE_CHOICES,
        "question_bank_exam_kind_choices": QUESTION_EXAM_KIND_CHOICES,
        "question_bank_kind_filter": kind_filter,
        "question_bank_kind_pills": _kind_pills(search_query, kind_filter, QUESTION_EXAM_KIND_CHOICES),
        # Bank yaratma yalnız imtahan mərkəzinə açıqdır — düymə/forma buna görə gizlənir.
        "question_bank_can_create": can_create_question_bank(request.user),
    }
