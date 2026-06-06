"""
Müəllim — imtahanın dil variantlarının idarəsi.

Bir imtahan altında müxtəlif dillərdə (AZ/RU/EN/TR) sual dəstləri:
- dil variantı yarat / aktiv-deaktiv et,
- həmin dilə toplu (bulk) test sualları yüklə (mövcud parser yenidən istifadə),
- hər dil üzrə sual sayını gör.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import pgettext

from apps.exams.constants import EXAM_LANGUAGE_CHOICES, EXAM_LANGUAGE_VALUES
from apps.exams.services.access_policy import _ensure_teacher
from apps.exams.services.language_variants import (
    create_questions_for_variant,
    create_variant,
    language_label,
    set_variant_active,
)
from apps.exams.services.parsing import parse_bulk_mcq
from apps.exams.views.shared.tenant import get_teacher_exam_or_404


def _manager_url(exam):
    return reverse("exams:exam_language_manager", kwargs={"slug": exam.slug})


def _build_variant_rows(exam):
    rows = []
    for variant in exam.language_variants.order_by("language"):
        rows.append(
            {
                "variant": variant,
                "label": language_label(variant.language),
                "count": exam.questions.filter(language=variant.language, is_active=True).count(),
            }
        )
    return rows


@login_required
def exam_language_manager(request, slug):
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()

        if action == "add_variant":
            language = (request.POST.get("language") or "").strip().lower()
            display_name = (request.POST.get("display_name") or "").strip()
            try:
                create_variant(exam, language, display_name=display_name)
                messages.success(request, pgettext("exams.view.language.message", "Dil variantı əlavə olundu."))
            except ValidationError as exc:
                messages.error(request, exc.messages[0])

        elif action == "toggle_variant":
            variant = exam.language_variants.filter(id=request.POST.get("variant_id")).first()
            if variant is not None:
                set_variant_active(variant, not variant.is_active)
                messages.success(request, pgettext("exams.view.language.message", "Dil variantı yeniləndi."))

        elif action == "upload_questions":
            language = (request.POST.get("language") or "").strip().lower()
            bulk_text = request.POST.get("bulk_text") or ""
            if language not in EXAM_LANGUAGE_VALUES:
                messages.error(request, pgettext("exams.view.language.message", "Düzgün dil seçin."))
            elif not bulk_text.strip():
                messages.error(request, pgettext("exams.view.language.message", "Sual mətni boşdur."))
            else:
                parsed = parse_bulk_mcq(bulk_text)
                created = create_questions_for_variant(
                    exam, language, parsed, default_points=exam.default_question_points or 1
                )
                messages.success(
                    request,
                    pgettext("exams.view.language.message", "{count} sual əlavə olundu.").format(count=len(created)),
                )

        return redirect(_manager_url(exam))

    variant_rows = _build_variant_rows(exam)
    existing_languages = {row["variant"].language for row in variant_rows}
    addable_languages = [(code, label) for code, label in EXAM_LANGUAGE_CHOICES if code not in existing_languages]

    context = {
        "exam": exam,
        "variant_rows": variant_rows,
        "addable_languages": addable_languages,
        "language_choices": EXAM_LANGUAGE_CHOICES,
        "is_test_exam": exam.exam_type == "test",
    }
    return render(request, "exams/teacher/exam_language_manager.html", context)
