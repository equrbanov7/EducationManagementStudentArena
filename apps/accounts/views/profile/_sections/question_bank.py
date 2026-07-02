"""Profil "question-bank" bölməsi üçün context-fragment qurucusu."""

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.urls import reverse

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
    }


def build_question_bank_context(request, *, allowed_sections, active_section) -> dict:
    """Sual bankı bölməsi üçün ``context`` açarlarını qaytarır. Bölmə aktiv
    deyilsə main.py default-ları ilə eyni dəyərləri verir (davranış dəyişmir)."""
    if not (active_section == "question-bank" and "question-bank" in allowed_sections):
        return _inactive_defaults()

    from apps.exams.models import QuestionBank
    from apps.exams.public import EXAM_LANGUAGE_CHOICES, accessible_banks
    from core.tenancy import get_request_organization

    organization = get_request_organization(request)
    search_query = (request.GET.get("bank_q") or "").strip()[:120]
    qs = accessible_banks(request.user, organization).annotate(
        lib_count=Count("library_questions", filter=Q(library_questions__is_active=True))
    )
    if search_query:
        qs = qs.filter(Q(name__icontains=search_query) | Q(subject__icontains=search_query))
    qs = qs.order_by("-created_at")

    page_obj = Paginator(qs, 9).get_page(request.GET.get("bank_page"))
    return {
        "question_bank_banks": page_obj.object_list,
        "question_bank_page_obj": page_obj,
        "question_bank_search_query": search_query,
        "question_bank_pagination_query": _query_string(section="question-bank", bank_q=search_query),
        "question_bank_back_url": _append_query_params(
            reverse("accounts:profile"),
            section="question-bank",
            bank_q=search_query,
            bank_page=request.GET.get("bank_page"),
        ),
        "question_bank_language_choices": EXAM_LANGUAGE_CHOICES,
        "question_bank_default_type_choices": QuestionBank.DEFAULT_QUESTION_TYPE_CHOICES,
    }
