"""
Müəllim — Sual Bankı kitabxanası (imtahandan asılı olmayan) + imtahana
"mövcud bankdan sual əlavə et" picker.

- ``question_bank_list``   — bankların siyahısı + yeni bank yaratma.
- ``question_bank_detail`` — bankın suallarına bax + toplu sual əlavə et.
- ``exam_bank_picker``     — imtahan üçün bankdan sual seçib snapshot kimi əlavə et.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import pgettext

from apps.exams.constants import DEFAULT_EXAM_LANGUAGE, EXAM_LANGUAGE_CHOICES
from apps.exams.models import QuestionBank
from apps.exams.services.access_policy import _ensure_teacher
from apps.exams.services.parsing import parse_bulk_mcq
from apps.exams.services.question_bank_attach import (
    accessible_banks,
    attach_bank_questions_to_exam,
    bank_questions_queryset,
    create_bank_questions_from_parsed,
)
from apps.exams.views.shared.tenant import get_teacher_exam_or_404
from core.tenancy import get_request_organization

_DIFFICULTY_CHOICES = (("easy", "Asan"), ("medium", "Orta"), ("hard", "Çətin"))


@login_required
def question_bank_list(request):
    _ensure_teacher(request.user)
    organization = get_request_organization(request)

    if request.method == "POST" and (request.POST.get("action") == "create_bank"):
        name = (request.POST.get("name") or "").strip()
        if not name:
            messages.error(request, pgettext("exams.view.bank.message", "Bank adı boş ola bilməz."))
        else:
            QuestionBank.objects.create(
                name=name,
                subject=(request.POST.get("subject") or "").strip(),
                description=(request.POST.get("description") or "").strip(),
                language=(request.POST.get("language") or DEFAULT_EXAM_LANGUAGE).strip().lower(),
                organization=organization,
                created_by=request.user,
                is_shared=bool(request.POST.get("is_shared")),
            )
            messages.success(request, pgettext("exams.view.bank.message", "Sual bankı yaradıldı."))
        return redirect("exams:question_bank_list")

    banks = (
        accessible_banks(request.user, organization)
        .annotate(lib_count=Count("library_questions", filter=Q(library_questions__is_active=True)))
        .order_by("-created_at")
    )

    context = {
        "banks": banks,
        "language_choices": EXAM_LANGUAGE_CHOICES,
    }
    return render(request, "exams/teacher/question_bank_list.html", context)


@login_required
def question_bank_detail(request, bank_id):
    _ensure_teacher(request.user)
    organization = get_request_organization(request)
    bank = get_object_or_404(accessible_banks(request.user, organization), id=bank_id)

    if request.method == "POST" and (request.POST.get("action") == "add_questions"):
        language = (request.POST.get("language") or bank.language or DEFAULT_EXAM_LANGUAGE).strip().lower()
        bulk_text = request.POST.get("bulk_text") or ""
        if not bulk_text.strip():
            messages.error(request, pgettext("exams.view.bank.message", "Sual mətni boşdur."))
        else:
            parsed = parse_bulk_mcq(bulk_text)
            created = create_bank_questions_from_parsed(bank, parsed, language=language, created_by=request.user)
            messages.success(
                request,
                pgettext("exams.view.bank.message", "{count} sual banka əlavə olundu.").format(count=len(created)),
            )
        return redirect("exams:question_bank_detail", bank_id=bank.id)

    questions = bank_questions_queryset(
        bank,
        language=(request.GET.get("language") or "").strip() or None,
        difficulty=(request.GET.get("difficulty") or "").strip() or None,
        search=(request.GET.get("q") or "").strip() or None,
    )
    paginator = Paginator(questions, 25)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    context = {
        "bank": bank,
        "page_obj": page_obj,
        "questions": page_obj.object_list,
        "language_choices": EXAM_LANGUAGE_CHOICES,
        "difficulty_choices": _DIFFICULTY_CHOICES,
        "search_query": (request.GET.get("q") or "").strip(),
        "language_filter": (request.GET.get("language") or "").strip(),
        "difficulty_filter": (request.GET.get("difficulty") or "").strip(),
    }
    return render(request, "exams/teacher/question_bank_detail.html", context)


@login_required
def exam_bank_picker(request, slug):
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    organization = get_request_organization(request)
    banks = accessible_banks(request.user, organization).order_by("-created_at")

    bank_id = (request.GET.get("bank") or request.POST.get("bank") or "").strip()
    selected_bank = banks.filter(id=bank_id).first() if bank_id else None

    if request.method == "POST" and (request.POST.get("action") == "attach"):
        if selected_bank is None:
            messages.error(request, pgettext("exams.view.bank.message", "Əvvəlcə bank seçin."))
        else:
            raw_ids = request.POST.getlist("question_ids")
            requested_ids = [int(value) for value in raw_ids if value.isdigit()]
            # Yalnız seçilmiş (əlçatan) bankın suallarını qəbul et — cross-tenant qoruması.
            valid_ids = list(
                bank_questions_queryset(selected_bank).filter(id__in=requested_ids).values_list("id", flat=True)
            )
            created = attach_bank_questions_to_exam(exam, valid_ids, created_by=request.user)
            messages.success(
                request,
                pgettext("exams.view.bank.message", "{count} sual imtahana əlavə olundu.").format(count=len(created)),
            )
            return redirect("exams:teacher_exam_detail", slug=exam.slug)

    questions = []
    total_count = 0
    if selected_bank is not None:
        question_qs = bank_questions_queryset(
            selected_bank,
            language=(request.GET.get("language") or "").strip() or None,
            difficulty=(request.GET.get("difficulty") or "").strip() or None,
            search=(request.GET.get("q") or "").strip() or None,
        )
        total_count = question_qs.count()
        questions = list(question_qs[:300])

    context = {
        "exam": exam,
        "banks": banks,
        "selected_bank": selected_bank,
        "questions": questions,
        "total_count": total_count,
        "language_choices": EXAM_LANGUAGE_CHOICES,
        "difficulty_choices": _DIFFICULTY_CHOICES,
        "search_query": (request.GET.get("q") or "").strip(),
        "language_filter": (request.GET.get("language") or "").strip(),
        "difficulty_filter": (request.GET.get("difficulty") or "").strip(),
    }
    return render(request, "exams/teacher/exam_bank_picker.html", context)
