"""question_bank paketi — yaratma/emal/AI view-ları."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import pgettext, pgettext_lazy
from django.views.decorators.http import require_POST

from apps.exams.constants import EXAM_LANGUAGE_CHOICES
from apps.exams.models import QuestionBlock
from apps.exams.services.access_policy import _ensure_teacher
from apps.exams.services.coding_definition import sync_coding_questions_for_exam
from apps.exams.services.language_variants import ensure_default_variant
from apps.exams.views.shared.tenant import get_teacher_exam_or_404

from ._helpers import (
    _append_navigation_query,
    _default_exam_language,
    _normalize_exam_language,
    _optional_non_negative_int,
    _parse_written_questions,
    _question_bank_title_context,
    _resolve_question_bank_navigation,
    _sync_written_block_questions,
)


@login_required
@require_POST
def ai_generate_question_bank(request, slug):
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)

    if exam.exam_type not in {"test", "written", "coding"}:
        return JsonResponse(
            {
                "ok": False,
                "error": pgettext(
                    "exams.view.question_bank.ai.error",
                    "Bu imtahan tipi üçün AI sual yaratma dəstəklənmir.",
                ),
            },
            status=400,
        )

    # P4 (2026-07-02): generasiya worker-də icra olunur (fayl-çıxarma daxil);
    # eager/sinxron halda cavab köhnə forma ilə birə-birdir.
    from apps.exams.views.teacher.extract_jobs import start_ai_generation_job

    ai_exam_type = "written" if exam.exam_type == "coding" else exam.exam_type
    payload = {
        "exam_title": exam.title,
        "exam_type": ai_exam_type,
        "prompt_text": request.POST.get("prompt", ""),
        "source_text": (request.POST.get("source_text") or "").strip(),
        "question_count": request.POST.get("question_count") or 5,
        "difficulty": request.POST.get("difficulty") or "medium",
        "block_name": request.POST.get("block_name") or "",
        "language_code": request.LANGUAGE_CODE,
        "user_id": request.user.pk,
    }
    return start_ai_generation_job(
        request,
        payload=payload,
        uploaded=request.FILES.get("source_file") or request.FILES.get("ai_source_file"),
        service_error_message=pgettext(
            "exams.view.question_bank.ai.error",
            "AI sual yaratma alınmadı. Bir az sonra yenidən yoxlayın.",
        ),
    )


@login_required
def create_question_bank(request, slug):
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    navigation_from_section, navigation_return_to, navigation_query = _resolve_question_bank_navigation(request)

    # Mövcud blokları gətiririk ki, ekranda görsənsin
    blocks = exam.question_blocks.all().order_by("order")

    # Hər blok üçün sualları mətn formatına çeviririk (Textarea üçün)
    # Məsələn: [ {block_obj: block, text_content: "1. Salam\n2. Necəsən"}, ... ]
    blocks_data = []
    for block in blocks:
        questions = block.questions.all().order_by("order")
        # Sualları "1. Sual mətni" formatında birləşdiririk
        text_content = "\n".join([f"{q.order}. {q.text}" for q in questions])

        blocks_data.append(
            {
                "obj": block,
                "text_content": text_content,
                "paint_enabled": block.enable_paint if block.enable_paint is not None else exam.enable_paint,
            }
        )

    return render(
        request,
        "exams/teacher/create_question_bank.html",
        {
            "exam": exam,
            "blocks_data": blocks_data,
            "question_bank_navigation_query": navigation_query,
            "navigation_from_section": navigation_from_section,
            "navigation_return_to": navigation_return_to,
            # Sualların dili seçicisi (test bankı ilə eyni davranış).
            "language_choices": EXAM_LANGUAGE_CHOICES,
            "selected_language": _default_exam_language(exam),
            **_question_bank_title_context(exam),
        },
    )


@login_required
def process_question_bank(request, slug):
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    _, _, navigation_query = _resolve_question_bank_navigation(request)

    if request.method == "POST":
        # 1. Silinməli olan blokları silirik
        deleted_ids = request.POST.get("deleted_block_ids", "").split(",")
        for d_id in deleted_ids:
            if d_id.strip():
                QuestionBlock.objects.filter(id=d_id, exam=exam).delete()

        # 2. Ümumi sual sayını yenilə
        random_count = _optional_non_negative_int(request.POST.get("random_question_count"))
        if random_count is not None:
            exam.random_question_count = random_count
            exam.save()

        # Seçilmiş dil — bütün yazılı suallar bu dil variantına bağlanacaq.
        selected_language = _normalize_exam_language(request.POST.get("language"), exam)
        selected_variant = ensure_default_variant(exam, selected_language)

        # Adların təkrar olub-olmadığını yoxlamaq üçün set
        used_names = set()

        # ✅ Order hesablamaq üçün counter
        current_order = 1

        # 3. Blokları emal edirik
        for key, value in request.POST.items():
            if key.startswith("block_name_"):
                ui_id = key.split("_")[-1]
                block_name = value.strip()

                # Validation: Eyni sorğuda dublikat ad varmı?
                if block_name.lower() in used_names:
                    messages.error(
                        request,
                        pgettext("exams.view.question_bank.message", "duplicate_block_name_request").format(
                            block_name=block_name
                        ),
                    )
                    return redirect(
                        _append_navigation_query(
                            reverse("exams:create_question_bank", kwargs={"slug": exam.slug}),
                            navigation_query,
                        )
                    )
                used_names.add(block_name.lower())

                content_key = f"block_content_{ui_id}"
                content_text = request.POST.get(content_key, "")
                time_key = f"block_time_{ui_id}"
                time_val = _optional_non_negative_int(request.POST.get(time_key))
                block_paint_enabled = request.POST.get(f"block_enable_paint_{ui_id}") == "on"
                db_id_key = f"block_db_id_{ui_id}"
                db_id = request.POST.get(db_id_key)

                # Validation: Bazada başqa blok eyni adda varmı? (özü xaric)
                existing_check = QuestionBlock.objects.filter(exam=exam, name__iexact=block_name)
                if db_id:
                    existing_check = existing_check.exclude(id=db_id)

                if existing_check.exists():
                    messages.error(
                        request,
                        pgettext("exams.view.question_bank.message", "block_name_exists_db").format(
                            block_name=block_name
                        ),
                    )
                    return redirect(
                        _append_navigation_query(
                            reverse("exams:create_question_bank", kwargs={"slug": exam.slug}),
                            navigation_query,
                        )
                    )

                if block_name:
                    # Blok Yaradılması/Yenilənməsi
                    if db_id:
                        # Bazada yoxlayırıq ki, silinməyibsə (concurrency üçün)
                        block_qs = QuestionBlock.objects.filter(id=db_id, exam=exam)
                        if block_qs.exists():
                            block = block_qs.first()
                            block.name = block_name
                            block.time_limit_minutes = time_val
                            block.enable_paint = block_paint_enabled
                            block.order = current_order  # ✅ Düzgün order
                            block.save()
                        else:
                            continue  # Blok tapılmadısa keçirik
                    else:
                        block = QuestionBlock.objects.create(
                            exam=exam,
                            name=block_name,
                            time_limit_minutes=time_val,
                            enable_paint=block_paint_enabled,
                            order=current_order,  # ✅ Düzgün order (ui_id deyil)
                        )

                    # ✅ Növbəti blok üçün order artır
                    current_order += 1

                    # Sualların Parse edilməsi
                    questions = _parse_written_questions(content_text) if content_text.strip() else []
                    _sync_written_block_questions(
                        block, questions, language=selected_language, language_variant=selected_variant
                    )

        if exam.exam_type == "coding":
            sync_coding_questions_for_exam(exam)

        from apps.exams.services.difficulty import schedule_ai_question_difficulty_warmup

        schedule_ai_question_difficulty_warmup(exam, force=True)

        messages.success(request, pgettext_lazy("exams.view.question_bank.message", "bank_saved"))
        return redirect(
            _append_navigation_query(
                reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}),
                navigation_query,
            )
        )

    return redirect(
        _append_navigation_query(
            reverse("exams:create_question_bank", kwargs={"slug": exam.slug}),
            navigation_query,
        )
    )
