"""question_bank paketi — şablon/word/test view-ları."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Max
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import pgettext

from apps.exams.models import ExamQuestion, ExamQuestionOption, QuestionBlock
from apps.exams.services.access_policy import _ensure_teacher, ensure_can_manage_exam_questions
from apps.exams.services.bulk_workbench import analyze_mcq_bulk, exam_question_fp_map
from apps.exams.services.import_media import (
    attach_import_media_batch,
    bind_import_manifest,
    clear_stash,
)
from apps.exams.services.language_variants import ensure_default_variant
from apps.exams.services.visual_import_upload import prepare_question_upload
from apps.exams.views.shared.tenant import get_teacher_exam_or_404

from ._helpers import (
    _append_navigation_query,
    _normalize_exam_language,
    _parse_points_payload,
    _parse_selected_question_indices,
    _question_bank_template_txt,
    _resolve_question_bank_navigation,
    _test_workbench_context,
)
from ._reports import (
    _build_question_bank_report_xlsx,
)


@login_required
def test_question_bank_template_download(request, slug):
    """
    Müəllimə hazır sual bankı şablonu endirir (yalnız TXT).
    DOCX importu söndürüldüyü üçün DOCX şablonu da verilmir.
    """
    _ensure_teacher(request.user)
    # Slug yoxlaması — tenant izolyasiyası
    get_teacher_exam_or_404(request, slug=slug)

    from django.http import HttpResponse

    response = HttpResponse(_question_bank_template_txt(), content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="sual_sablonu.txt"'
    return response


@login_required
def exam_questions_word_export(request, slug):
    """
    İmtahanın suallarını Word (.docx) faylı kimi export edir.

    Yalnız imtahanın müəllimi (tenant-scoped) yükləyə bilər; tələbələrə
    açıq deyil — düz cavablar faylda işarələnir. Format import parseri ilə
    uyğundur (round-trip). ?language=az parametri ilə dil filtri mümkündür.
    """
    from urllib.parse import quote

    from django.http import HttpResponse

    from apps.exams.services.question_word_export import build_questions_docx, exam_questions_payload

    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)

    language = (request.GET.get("language") or "").strip().lower() or None
    payload = exam_questions_payload(exam, language=language)
    if not payload:
        messages.warning(request, pgettext("exams.question_bank.message", "Export üçün sual tapılmadı."))
        return redirect("exams:test_question_bank", slug=exam.slug)

    subtitle_parts = [pgettext("exams.export", "Sual sayı: %(count)s") % {"count": len(payload)}]
    if language:
        subtitle_parts.append(pgettext("exams.export", "Dil: %(language)s") % {"language": language.upper()})

    buffer = build_questions_docx(
        title=pgettext("exams.export", "İmtahan sualları — %(title)s") % {"title": exam.title},
        subtitle=" · ".join(subtitle_parts),
        questions=payload,
    )
    response = HttpResponse(
        buffer.read(),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    safe_name = quote(f"{exam.title}_suallar.docx")
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{safe_name}"
    return response


@login_required
def test_question_bank(request, slug):
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    ensure_can_manage_exam_questions(request.user, exam)
    navigation_from_section, navigation_return_to, navigation_query = _resolve_question_bank_navigation(request)

    # yalnız test imtahanı üçün
    if exam.exam_type != "test":
        raise Http404()

    blocks = exam.question_blocks.all().order_by("order", "id")

    raw_text = ""
    parsed = []
    selected = set()
    math_token = ""

    warning_count = 0
    duplicate_count = 0
    error_count = 0
    test_level_warnings = []
    category_counts = {
        "errors": 0,
        "warnings": 0,
        "duplicates": 0,
        "structure": 0,
        "balance": 0,
        "clean": 0,
    }

    # >>> YENİ: UI dəyərləri (Preview klikində sıfırlanmasın deyə)
    # NOTE: 0 = hamısı; None/boş = default 10 göstər
    total_q = exam.questions.filter(is_active=True).count()
    exam_rq = getattr(exam, "random_question_count", None)
    rq_default = min(10, total_q) if exam_rq is None else exam_rq

    exam_dp = getattr(exam, "default_question_points", None) or 1
    dp_default = exam_dp

    # GET-də və POST-da input-ların value-ları buradan gedəcək
    rq_value = str(rq_default)
    dp_value = str(dp_default)

    # Seçilmiş dil — bu suallar həmin dil variantına bağlanacaq (çoxdilli imtahan).
    selected_language = _normalize_exam_language(request.POST.get("language") or request.GET.get("language"), exam)

    wb_ctx = _test_workbench_context(exam, navigation_query, selected_language=selected_language)

    # GET
    if request.method != "POST":
        return render(
            request,
            "exams/teacher/test_question_bank.html",
            {
                "exam": exam,
                "blocks": blocks,
                "raw_text": raw_text,
                "parsed": parsed,
                "selected": selected,
                "warning_count": warning_count,
                "duplicate_count": duplicate_count,
                "error_count": error_count,
                "test_level_warnings": test_level_warnings,
                "category_counts": category_counts,
                # >>> YENİ: input-ların value-ları
                "rq_value": rq_value,
                "dp_value": dp_value,
                "question_bank_navigation_query": navigation_query,
                "navigation_from_section": navigation_from_section,
                "navigation_return_to": navigation_return_to,
                **wb_ctx,
            },
        )

    # POST
    action = request.POST.get("action", "preview")

    # >>> YENİ: Preview-də də input dəyərlərini saxla (DB-yə yazmadan!)
    rq_post = (request.POST.get("random_question_count") or "").strip()
    dp_post = (request.POST.get("default_points") or "").strip()

    if rq_post != "":
        rq_value = rq_post  # typed dəyər geri qayıtsın
    if dp_post != "":
        dp_value = dp_post  # typed dəyər geri qayıtsın

    # 1) raw_text-i formdan al (save formunda hidden textarea olmalıdır!)
    raw_text = request.POST.get("raw_text", "")

    # 2) fayl varsa onu oxu (paste varsa fallback kimi qalır)
    math_token = (request.POST.get("math_token") or "").strip()
    uploaded = request.FILES.get("upload_file")
    upload_failed = False
    if uploaded:
        try:
            raw_text, math_token = prepare_question_upload(
                uploaded,
                previous_token=math_token,
                owner_id=request.user.pk,
                organization_id=exam.organization_id,
            )
        except Exception as e:
            upload_failed = True
            # burada fallback: textarea-dakı raw_text qalsın
            messages.error(
                request,
                pgettext("exams.view.question_bank.message", "file_read_failed").format(error=e),
            )

    # 3) preview/save üçün parse + tam validasiya — ortaq workbench mühərriki.
    #    (Dublikat aşkarlanması, struktur/balans xəbərdarlıqları, meta bayraqları
    #     və kateqoriya sayğacları artıq servis daxilində hesablanır.)
    if action in ("preview", "save", "download_report"):
        # Dublikat yoxlanışı yalnız EYNİ dildəki mövcud suallara qarşı aparılır —
        # eyni sual başqa dildə təkrar deyil.
        analysis = analyze_mcq_bulk(raw_text, existing_fp_map=exam_question_fp_map(exam, language=selected_language))
        parsed = analysis["parsed"]
        category_counts = analysis["category_counts"]
        warning_count = analysis["warning_count"]
        duplicate_count = analysis["duplicate_count"]
        error_count = analysis["error_count"]
        test_level_warnings = analysis["test_level_warnings"]

        if math_token:
            try:
                bind_import_manifest(
                    math_token,
                    parsed,
                    owner_id=request.user.pk,
                    organization_id=exam.organization_id,
                )
            except (OSError, ValueError) as exc:
                messages.error(request, str(exc))
                if action == "save":
                    action = "preview"

        if upload_failed and action == "save":
            action = "preview"

        # ---- Seçilən suallar ----
        selected_from_request = _parse_selected_question_indices(request.POST)
        if selected_from_request is None:
            selected = set(range(1, len(parsed) + 1))
        else:
            selected = selected_from_request

    # 4) REPORT DOWNLOAD
    if action == "download_report":
        try:
            return _build_question_bank_report_xlsx(
                exam=exam,
                raw_text=raw_text,
                parsed=parsed,
                test_level_warnings=test_level_warnings,
                category_counts=category_counts,
                warning_count=warning_count,
                duplicate_count=duplicate_count,
                error_count=error_count,
            )
        except RuntimeError as exc:
            messages.error(request, str(exc))

    # 5) SAVE
    if action == "save":
        # ---- Exam settings: random_question_count + default_points(+ optional default_question_points) ----
        rq_raw = (request.POST.get("random_question_count") or "").strip()
        dp_raw = (request.POST.get("default_points") or "").strip()

        update_fields = []

        # random_question_count: 0 = hamısı, 10 = 10, 1 = 1 və s.
        if rq_raw.isdigit():
            exam.random_question_count = int(rq_raw)
            update_fields.append("random_question_count")

        # default_points: formdan gəlmirsə, exam.default_question_points varsa onu götür, yoxdursa 1
        if dp_raw.isdigit() and int(dp_raw) > 0:
            default_points = int(dp_raw)
        else:
            default_points = getattr(exam, "default_question_points", None) or 1

        # Exam-də də saxla (əgər field varsa) – köhnə məntiqi pozmur
        if hasattr(exam, "default_question_points"):
            exam.default_question_points = default_points
            update_fields.append("default_question_points")

        created_count = 0
        skipped_count = 0
        points_payload = _parse_points_payload(request.POST)

        with transaction.atomic():
            if update_fields:
                exam.save(update_fields=update_fields)

            # ---- blok seçimi / yeni blok ----
            block_id = request.POST.get("block_id")
            new_block_name = (request.POST.get("new_block_name") or "").strip()
            block_obj = None

            if new_block_name:
                max_order = blocks.aggregate(m=Max("order")).get("m") or 0
                block_obj = QuestionBlock.objects.create(exam=exam, name=new_block_name, order=max_order + 1)
            elif block_id:
                block_obj = QuestionBlock.objects.filter(id=block_id, exam=exam).first()

            # ---- dil variantı: suallar seçilmiş dilə bağlanır ----
            # Köhnə tək-dilli imtahanlarda da `az` varyantı yaranır (geriyə uyğun,
            # student dil seçimi axını üçün lazımdır).
            language_variant = ensure_default_variant(exam, selected_language)

            # ---- order başlanğıcı ----
            start_order = (ExamQuestion.objects.filter(exam=exam).aggregate(m=Max("order")).get("m") or 0) + 1

            question_rows = []
            option_payloads = []
            source_indices = []

            for idx, q in enumerate(parsed, start=1):
                if idx not in selected:
                    continue

                # minimum şərt: A-D olsun
                if any(x not in q["options"] for x in ["A", "B", "C", "D"]):
                    skipped_count += 1
                    continue

                # per-question points: compact payload first, legacy input fallback second.
                p_value = points_payload.get(str(idx), request.POST.get(f"points_{idx}"))
                p_raw = str(p_value or "").strip()
                points = int(p_raw) if p_raw.isdigit() and int(p_raw) > 0 else default_points

                question_rows.append(
                    ExamQuestion(
                        exam=exam,
                        block=block_obj,
                        text=q["text"],
                        answer_mode=q["answer_mode"],
                        order=start_order,
                        points=points,
                        language=selected_language,
                        language_variant=language_variant,
                    )
                )
                option_payloads.append((q["options"], set(q["correct"])))
                source_indices.append(q.get("source_index"))
                start_order += 1

            created_questions = ExamQuestion.objects.bulk_create(question_rows, batch_size=100)
            created_count = len(created_questions)

            option_rows = []
            for eq, (options, correct) in zip(created_questions, option_payloads):
                for lab in "ABCDE":
                    if lab in options:
                        option_rows.append(
                            ExamQuestionOption(
                                question=eq,
                                label=lab,
                                text=options[lab],
                                is_correct=(lab in correct),
                            )
                        )

            if option_rows:
                ExamQuestionOption.objects.bulk_create(option_rows, batch_size=500)

            # Mənbə PDF-in canonical vizual segmentlərini bağla (varsa).
            if math_token:
                attach_import_media_batch(
                    math_token,
                    list(zip(source_indices, created_questions)),
                    owner_id=request.user.pk,
                    organization_id=exam.organization_id,
                )

        if math_token:
            clear_stash(math_token)

        messages.success(
            request,
            pgettext("exams.view.question_bank.message", "questions_added_summary").format(
                created_count=created_count,
                skipped_count=skipped_count,
            ),
        )
        from apps.exams.services.difficulty import schedule_ai_question_difficulty_warmup

        schedule_ai_question_difficulty_warmup(exam, force=True)
        return redirect(
            _append_navigation_query(
                reverse("exams:test_question_bank", kwargs={"slug": exam.slug}),
                navigation_query,
            )
        )

    # PREVIEW və ya parse sonrası eyni səhifəni göstər
    return render(
        request,
        "exams/teacher/test_question_bank.html",
        {
            "exam": exam,
            "blocks": blocks,
            "raw_text": raw_text,
            "parsed": parsed,
            "selected": selected,
            "math_token": math_token,
            "warning_count": warning_count,
            "duplicate_count": duplicate_count,
            "error_count": error_count,
            "test_level_warnings": test_level_warnings,
            "category_counts": category_counts,
            # >>> YENİ: Preview refresh olsa da input-lar dolu qalsın
            "rq_value": rq_value,
            "dp_value": dp_value,
            "question_bank_navigation_query": navigation_query,
            "navigation_from_section": navigation_from_section,
            "navigation_return_to": navigation_return_to,
            # Workbench konteksti (başlıq, düymələr, dil seçici) preview-də də qalmalıdır.
            **wb_ctx,
        },
    )
