"""
Müəllim — imtahanın dil variantlarının idarəsi.

Bir imtahan altında müxtəlif dillərdə (AZ/RU/EN/TR) sual dəstləri:
- dil variantı yarat / aktiv-deaktiv et,
- həmin dilə ortaq "workbench" ilə toplu (bulk) test sualları yüklə (tam
  preview/validasiya — test bankı ilə eyni komponent),
- hər dil üzrə sual sayını gör.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import pgettext

from apps.exams.constants import DEFAULT_EXAM_LANGUAGE, EXAM_LANGUAGE_CHOICES, EXAM_LANGUAGE_VALUES
from apps.exams.services.access_policy import _ensure_teacher, ensure_can_manage_exam_questions
from apps.exams.services.bulk_workbench import (
    analyze_mcq_bulk,
    exam_question_fp_map,
    parse_points_payload,
    parse_selected_indices,
)
from apps.exams.services.language_variants import (
    create_questions_for_variant,
    create_variant,
    language_label,
    set_variant_active,
)
from apps.exams.services.parsing import extract_text_from_upload
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


def _empty_analysis():
    return {
        "parsed": [],
        "category_counts": {"errors": 0, "warnings": 0, "duplicates": 0, "structure": 0, "balance": 0, "clean": 0},
        "warning_count": 0,
        "duplicate_count": 0,
        "error_count": 0,
        "test_level_warnings": [],
    }


def _variant_language_options(variant_rows):
    """Workbench dil seçicisi üçün yalnız mövcud variant dilləri (göstəriş adı ilə)."""
    return [(row["variant"].language, row["variant"].display_name or row["label"]) for row in variant_rows]


def _language_workbench_context(exam, variant_rows, selected_language):
    return {
        "wb_workbench_key": f"exam-lang-{exam.slug}",
        "wb_hide_header": True,
        "wb_section_title": pgettext("exams.template.language_manager", "Dilə toplu sual yüklə"),
        "wb_show_settings": False,
        "wb_ai_url": "",
        "wb_show_language": True,
        "wb_languages": _variant_language_options(variant_rows),
        "wb_selected_language": selected_language,
        "wb_show_format": False,
        "wb_format": "test",
        "wb_show_report": False,
        "wb_templates": [],
        "wb_save_label": pgettext("exams.template.language_manager", "Seçilmişləri bu dilə əlavə et"),
    }


@login_required
def exam_language_manager(request, slug):
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    ensure_can_manage_exam_questions(request.user, exam)
    is_test_exam = exam.exam_type == "test"

    # ── Workbench vəziyyəti ──
    raw_text = ""
    parsed = []
    selected = set()
    analysis = _empty_analysis()

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
            return redirect(_manager_url(exam))

        if action == "toggle_variant":
            variant = exam.language_variants.filter(id=request.POST.get("variant_id")).first()
            if variant is not None:
                set_variant_active(variant, not variant.is_active)
                messages.success(request, pgettext("exams.view.language.message", "Dil variantı yeniləndi."))
            return redirect(_manager_url(exam))

        if action in ("preview", "save") and is_test_exam:
            selected_language = (request.POST.get("language") or "").strip().lower()
            if selected_language not in EXAM_LANGUAGE_VALUES:
                messages.error(request, pgettext("exams.view.language.message", "Düzgün dil seçin."))
                return redirect(_manager_url(exam))

            raw_text = request.POST.get("raw_text", "")
            uploaded = request.FILES.get("upload_file")
            if uploaded:
                try:
                    raw_text = extract_text_from_upload(uploaded)
                except Exception as exc:  # noqa: BLE001 — fayl oxunmasa textarea mətni qalır
                    messages.error(
                        request, pgettext("exams.view.language.message", "Fayl oxunmadı: {error}").format(error=exc)
                    )

            analysis = analyze_mcq_bulk(
                raw_text, existing_fp_map=exam_question_fp_map(exam, language=selected_language)
            )
            parsed = analysis["parsed"]

            selected_from_request = parse_selected_indices(request.POST)
            selected = set(range(1, len(parsed) + 1)) if selected_from_request is None else selected_from_request

            if action == "save":
                points_payload = parse_points_payload(request.POST)
                default_points = getattr(exam, "default_question_points", None) or 1
                selected_parsed = []
                for index, question in enumerate(parsed, start=1):
                    if index not in selected:
                        continue
                    raw_points = str(points_payload.get(str(index)) or "").strip()
                    if raw_points.isdigit() and int(raw_points) > 0:
                        question["points"] = int(raw_points)
                    selected_parsed.append(question)

                created = create_questions_for_variant(
                    exam, selected_language, selected_parsed, default_points=default_points
                )
                messages.success(
                    request,
                    pgettext("exams.view.language.message", "{count} sual əlavə olundu.").format(count=len(created)),
                )
                return redirect(_manager_url(exam))

    variant_rows = _build_variant_rows(exam)
    existing_languages = {row["variant"].language for row in variant_rows}
    addable_languages = [(code, label) for code, label in EXAM_LANGUAGE_CHOICES if code not in existing_languages]

    selected_language = (request.POST.get("language") or "").strip().lower()
    if selected_language not in existing_languages:
        selected_language = next(iter(existing_languages), DEFAULT_EXAM_LANGUAGE)

    context = {
        "exam": exam,
        "variant_rows": variant_rows,
        "addable_languages": addable_languages,
        "language_choices": EXAM_LANGUAGE_CHOICES,
        "is_test_exam": is_test_exam,
        # Workbench preview konteksti
        "raw_text": raw_text,
        "parsed": parsed,
        "selected": selected,
        "category_counts": analysis["category_counts"],
        "warning_count": analysis["warning_count"],
        "duplicate_count": analysis["duplicate_count"],
        "error_count": analysis["error_count"],
        "test_level_warnings": analysis["test_level_warnings"],
        "rq_value": "",
        "dp_value": str(getattr(exam, "default_question_points", None) or 1),
        **_language_workbench_context(exam, variant_rows, selected_language),
    }
    return render(request, "exams/teacher/exam_language_manager.html", context)
