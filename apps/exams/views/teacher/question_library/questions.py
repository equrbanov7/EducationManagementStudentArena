"""question_library paketi — questions."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import pgettext

from apps.exams.constants import DEFAULT_EXAM_LANGUAGE, EXAM_LANGUAGE_CHOICES
from apps.exams.forms import BankQuestionCreateForm
from apps.exams.services.access_policy import _ensure_teacher
from apps.exams.services.bulk_workbench import (
    analyze_mcq_bulk,
    analyze_written_bulk,
    bank_question_fp_map,
    bank_written_text_map,
    parse_points_payload,
    parse_selected_indices,
)
from apps.exams.services.import_media import clear_stash, stash_math_images
from apps.exams.services.parsing import extract_text_from_upload
from apps.exams.services.question_bank_attach import _question_fingerprint, accessible_banks
from core.tenancy import get_request_organization

from ._shared import (
    _empty_analysis,
    _is_modal_request,
    _normalize_format,
    _render_bank_question_form_html,
    _save_bank_questions,
)


@login_required
def question_bank_bulk_add(request, bank_id):
    _ensure_teacher(request.user)
    organization = get_request_organization(request)
    bank = get_object_or_404(accessible_banks(request.user, organization), id=bank_id)

    raw_text = ""
    parsed = []
    selected = set()
    analysis = _empty_analysis()
    q_format = _normalize_format(
        request.POST.get("q_format") or request.GET.get("format") or bank.default_question_type
    )
    selected_language = (request.POST.get("language") or bank.language or DEFAULT_EXAM_LANGUAGE).strip().lower()

    math_token = (request.POST.get("math_token") or "").strip()
    if request.method == "POST":
        action = (request.POST.get("action") or "preview").strip()
        if action in ("preview", "save"):
            raw_text = request.POST.get("raw_text", "")
            uploaded = request.FILES.get("upload_file")
            if uploaded:
                try:
                    raw_text = extract_text_from_upload(uploaded)
                    # Düstur/şəkil regionlarını müvəqqəti yığ (save addımında bağlanacaq).
                    new_token = stash_math_images(uploaded)
                    if new_token:
                        clear_stash(math_token)  # köhnə yığını təmizlə
                        math_token = new_token
                except Exception as exc:  # noqa: BLE001
                    messages.error(
                        request, pgettext("exams.view.bank.message", "Fayl oxunmadı: {error}").format(error=exc)
                    )

            if q_format == "written":
                analysis = analyze_written_bulk(
                    raw_text, existing_text_map=bank_written_text_map(bank, language=selected_language)
                )
            else:
                analysis = analyze_mcq_bulk(
                    raw_text, existing_fp_map=bank_question_fp_map(bank, language=selected_language)
                )
            parsed = analysis["parsed"]

            selected_from_request = parse_selected_indices(request.POST)
            selected = set(range(1, len(parsed) + 1)) if selected_from_request is None else selected_from_request

            if action == "save":
                created_count = _save_bank_questions(
                    bank=bank,
                    parsed=parsed,
                    selected=selected,
                    language=selected_language,
                    q_format=q_format,
                    points_payload=parse_points_payload(request.POST),
                    created_by=request.user,
                    math_token=math_token,
                )
                clear_stash(math_token)
                messages.success(
                    request,
                    pgettext("exams.view.bank.message", "{count} sual banka əlavə olundu.").format(count=created_count),
                )
                return redirect("exams:question_bank_detail", bank_id=bank.id)

    context = {
        "exam": None,
        "bank": bank,
        "raw_text": raw_text,
        "parsed": parsed,
        "selected": selected,
        "category_counts": analysis["category_counts"],
        "warning_count": analysis["warning_count"],
        "duplicate_count": analysis["duplicate_count"],
        "error_count": analysis["error_count"],
        "test_level_warnings": analysis["test_level_warnings"],
        "rq_value": "",
        "dp_value": "1",
        # workbench konteksti
        "wb_workbench_key": f"bank-{bank.id}",
        "wb_title": bank.name,
        "wb_subtitle": pgettext(
            "exams.template.question_bank_detail", "Sualları yazın və ya fayl yükləyin, önizləyin, yadda saxlayın."
        ),
        "wb_back_url": reverse("exams:question_bank_detail", kwargs={"bank_id": bank.id}),
        "wb_back_label": pgettext("exams.template.question_bank_detail", "Banka qayıt"),
        "wb_show_settings": False,
        # AI bloku imtahan səhifəsi ilə eyni olsun deyə bankda da göstərilir.
        "wb_ai_url": reverse("exams:ai_generate_bank_questions", kwargs={"bank_id": bank.id}),
        "wb_ai_context": q_format,
        "wb_show_language": True,
        "wb_languages": EXAM_LANGUAGE_CHOICES,
        "wb_selected_language": selected_language,
        # Format toggle YOXDUR — bank yaradılarkən seçilmiş tipə (test/yazılı) görə
        # avtomatik açılır, beləcə imtahan test-bankı ilə eyni görünür.
        "wb_show_format": False,
        "wb_format": q_format,
        "wb_show_report": False,
        "wb_templates": [
            {
                "url": reverse("exams:question_bank_template_download", kwargs={"bank_id": bank.id}) + "?format=txt",
                "label": "TXT",
                "kind": "txt",
            },
        ],
        "wb_save_label": pgettext("exams.template.question_bank_detail", "Seçilmişləri banka əlavə et"),
        # Düstur/şəkil yığını üçün token — gizli sahə kimi save addımına ötürülür.
        "math_token": math_token,
    }
    return render(request, "exams/teacher/question_bank_bulk_add.html", context)


@login_required
def ai_generate_bank_questions(request, bank_id):
    _ensure_teacher(request.user)
    organization = get_request_organization(request)
    bank = get_object_or_404(accessible_banks(request.user, organization), id=bank_id)

    # Format: AI kartından (q_format) gəlir, yoxsa bankın default tipi.
    q_format = _normalize_format(request.POST.get("q_format") or bank.default_question_type)

    # P4 (2026-07-02): generasiya worker-də (fayl-çıxarma daxil); eager halda
    # cavab köhnə forma ilə birə-birdir.
    from apps.exams.views.teacher.extract_jobs import start_ai_generation_job

    payload = {
        "exam_title": bank.name,
        "exam_type": q_format,
        "prompt_text": request.POST.get("prompt", ""),
        "source_text": (request.POST.get("source_text") or "").strip(),
        "question_count": request.POST.get("question_count") or 5,
        "difficulty": request.POST.get("difficulty") or "medium",
        "block_name": "",
        "language_code": request.LANGUAGE_CODE,
        "user_id": request.user.pk,
    }
    return start_ai_generation_job(
        request,
        payload=payload,
        uploaded=request.FILES.get("source_file") or request.FILES.get("ai_source_file"),
        service_error_message=pgettext(
            "exams.view.bank.ai.error", "AI sual yaratma alınmadı. Bir az sonra yenidən yoxlayın."
        ),
    )


@login_required
def bank_question_add(request, bank_id):
    _ensure_teacher(request.user)
    organization = get_request_organization(request)
    bank = get_object_or_404(accessible_banks(request.user, organization), id=bank_id)
    is_modal = _is_modal_request(request)
    q_format = _normalize_format(
        request.POST.get("q_format") or request.GET.get("format") or bank.default_question_type
    )

    if request.method == "POST":
        form = BankQuestionCreateForm(
            request.POST, request.FILES, question_type=q_format, default_language=bank.language
        )
        if form.is_valid():
            question = form.save(commit=False)
            question.bank = bank
            question.question_type = q_format
            question.created_by = request.user
            question.fingerprint = _question_fingerprint(question.text)
            if q_format == "test":
                question.answer_mode = form.cleaned_data.get("answer_mode", "single")
            question.save()
            if q_format == "test":
                form.create_options(question)
            if is_modal:
                return JsonResponse({"success": True, "question_id": question.id})
            return redirect("exams:question_bank_detail", bank_id=bank.id)
        if is_modal:
            return JsonResponse(
                {
                    "success": False,
                    "html": _render_bank_question_form_html(request, bank=bank, form=form, editing=False),
                },
                status=400,
            )
    else:
        form = BankQuestionCreateForm(question_type=q_format, default_language=bank.language)

    return render(
        request,
        "exams/teacher/partials/_question_form.html",
        {"bank": bank, "form": form, "editing": False, "is_modal": True, "q_format": q_format},
    )


@login_required
def bank_question_edit(request, bank_id, question_id):
    _ensure_teacher(request.user)
    organization = get_request_organization(request)
    bank = get_object_or_404(accessible_banks(request.user, organization), id=bank_id)
    question = get_object_or_404(bank.library_questions, id=question_id)
    is_modal = _is_modal_request(request)
    q_format = question.question_type if question.question_type in ("test", "written") else "test"

    if request.method == "POST":
        form = BankQuestionCreateForm(request.POST, request.FILES, instance=question, question_type=q_format)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.bank = bank
            updated.question_type = q_format
            updated.fingerprint = _question_fingerprint(updated.text)
            if q_format == "test":
                updated.answer_mode = form.cleaned_data.get("answer_mode", "single")
            updated.save()
            if q_format == "test":
                form.save_options(updated)
            if is_modal:
                return JsonResponse({"success": True, "question_id": updated.id})
            return redirect("exams:question_bank_detail", bank_id=bank.id)
        if is_modal:
            return JsonResponse(
                {
                    "success": False,
                    "html": _render_bank_question_form_html(
                        request, bank=bank, form=form, editing=True, question=question
                    ),
                },
                status=400,
            )
    else:
        form = BankQuestionCreateForm(instance=question, question_type=q_format)

    return render(
        request,
        "exams/teacher/partials/_question_form.html",
        {"bank": bank, "form": form, "editing": True, "question": question, "is_modal": True, "q_format": q_format},
    )
