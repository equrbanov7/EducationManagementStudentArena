import re
from urllib.parse import urlencode, urlsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext, pgettext_lazy

from apps.exams.models import ExamQuestion, ExamQuestionOption, QuestionBlock
from apps.exams.services.access_policy import _ensure_teacher
from apps.exams.services.parsing import extract_text_from_upload, parse_bulk_mcq
from apps.exams.services.utils import _norm
from apps.exams.views.shared.tenant import get_teacher_exam_or_404


def _safe_same_origin_redirect_path(request, candidate_url):
    raw_url = (candidate_url or "").strip()
    if not raw_url:
        return ""

    if not url_has_allowed_host_and_scheme(
        raw_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return ""

    parsed = urlsplit(raw_url)
    if parsed.netloc and parsed.netloc != request.get_host():
        return ""

    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    return f"{path}{query}{fragment}"


def _resolve_question_bank_navigation(request):
    requested_profile_section = (request.GET.get("from_section") or request.POST.get("from_section") or "").strip()
    valid_profile_sections = {
        "my-exams",
        "assigned-exams",
        "profile-info",
        "my-courses",
        "assigned-courses",
        "courses",
        "pending-review",
        "review-results",
    }
    if requested_profile_section not in valid_profile_sections:
        requested_profile_section = ""

    return_to = _safe_same_origin_redirect_path(
        request,
        request.GET.get("return_to") or request.POST.get("return_to"),
    )

    nav_params = {}
    if requested_profile_section:
        nav_params["from_section"] = requested_profile_section
    if return_to:
        nav_params["return_to"] = return_to

    return requested_profile_section, return_to, urlencode(nav_params)


def _append_navigation_query(path, navigation_query):
    if not navigation_query:
        return path
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{navigation_query}"


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

        blocks_data.append({"obj": block, "text_content": text_content})

    return render(
        request,
        "exams/teacher/create_question_bank.html",
        {
            "exam": exam,
            "blocks_data": blocks_data,
            "question_bank_navigation_query": navigation_query,
            "navigation_from_section": navigation_from_section,
            "navigation_return_to": navigation_return_to,
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
        random_count = request.POST.get("random_question_count")
        if random_count:
            exam.random_question_count = int(random_count)
            exam.save()

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
                time_val = request.POST.get(time_key)
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
                        block_qs = QuestionBlock.objects.filter(id=db_id)
                        if block_qs.exists():
                            block = block_qs.first()
                            block.name = block_name
                            block.time_limit_minutes = int(time_val) if time_val else None
                            block.order = current_order  # ✅ Düzgün order
                            block.save()
                            # Sualları yeniləyirik
                            block.questions.all().delete()
                        else:
                            continue  # Blok tapılmadısa keçirik
                    else:
                        block = QuestionBlock.objects.create(
                            exam=exam,
                            name=block_name,
                            time_limit_minutes=int(time_val) if time_val else None,
                            order=current_order,  # ✅ Düzgün order (ui_id deyil)
                        )

                    # ✅ Növbəti blok üçün order artır
                    current_order += 1

                    # Sualların Parse edilməsi
                    if content_text.strip():
                        pattern = r"(?:\n|^)\s*\d+[\.\)]\s+"
                        questions = re.split(pattern, content_text)
                        questions = [q.strip() for q in questions if q.strip()]

                        for index, q_text in enumerate(questions, start=1):
                            ExamQuestion.objects.create(
                                exam=exam,
                                block=block,
                                text=q_text,
                                order=index,
                                answer_mode="single",
                            )

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


@login_required
def test_question_bank(request, slug):
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    navigation_from_section, navigation_return_to, navigation_query = _resolve_question_bank_navigation(request)

    # yalnız test imtahanı üçün
    if exam.exam_type != "test":
        raise Http404()

    blocks = exam.question_blocks.all().order_by("order", "id")

    raw_text = ""
    parsed = []
    selected = set()

    warning_count = 0
    duplicate_count = 0

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

    def build_fp_from_parsed(q):
        return _norm(q["text"]) + "||" + "||".join([_norm(q["options"].get(x, "")) for x in "ABCDE"])

    def build_fp_from_db(eq):
        # DB-də option-lar label saxlamadığı üçün sıra ilə götürürük (A..E)
        opt_map = {}
        opts = list(eq.options.all())
        labels = list("ABCDE")
        for i, opt in enumerate(opts[:5]):
            opt_map[labels[i]] = opt.text
        return _norm(eq.text) + "||" + "||".join([_norm(opt_map.get(x, "")) for x in "ABCDE"])

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
                # >>> YENİ: input-ların value-ları
                "rq_value": rq_value,
                "dp_value": dp_value,
                "question_bank_navigation_query": navigation_query,
                "navigation_from_section": navigation_from_section,
                "navigation_return_to": navigation_return_to,
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
    uploaded = request.FILES.get("upload_file")
    if uploaded:
        try:
            raw_text = extract_text_from_upload(uploaded)
        except Exception as e:
            # burada fallback: textarea-dakı raw_text qalsın
            messages.error(
                request,
                pgettext("exams.view.question_bank.message", "file_read_failed").format(error=e),
            )

    # 3) preview/save üçün parse et
    if action in ("preview", "save"):
        parsed = parse_bulk_mcq(raw_text) or []

        # təhlükəsizlik: warnings açarı hər sualda olsun
        for q in parsed:
            q.setdefault("warnings", [])

        # ---- Duplicate check: import daxilində ----
        fp_first = {}
        for idx, q in enumerate(parsed, start=1):
            fp = build_fp_from_parsed(q)
            if fp in fp_first:
                q["warnings"].append(
                    {
                        "type": "duplicate_in_import",
                        "msg": pgettext("exams.view.question_bank.warning", "duplicate_in_import").format(
                            index=idx,
                            previous_index=fp_first[fp],
                        ),
                        "ref": fp_first[fp],
                    }
                )
            else:
                fp_first[fp] = idx

        # ---- Duplicate check: DB-də artıq var? ----
        existing = ExamQuestion.objects.filter(exam=exam).prefetch_related("options")
        existing_fp = {build_fp_from_db(eq) for eq in existing}

        for idx, q in enumerate(parsed, start=1):
            fp = build_fp_from_parsed(q)
            if fp in existing_fp:
                q["warnings"].append(
                    {
                        "type": "already_in_exam",
                        "msg": pgettext("exams.view.question_bank.warning", "already_in_exam").format(index=idx),
                    }
                )

        # ---- Seçilən suallar ----
        selected_list = request.POST.getlist("selected")
        if selected_list:
            selected = set(int(x) for x in selected_list)
        else:
            selected = set(range(1, len(parsed) + 1))

        # ---- warning sayları (üst panel üçün) ----
        warning_count = sum(len(q.get("warnings", [])) for q in parsed)
        duplicate_count = sum(
            1
            for q in parsed
            for w in q.get("warnings", [])
            if w.get("type") in ("duplicate_in_import", "already_in_exam")
        )

    # 4) SAVE
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

        # ---- order başlanğıcı ----
        start_order = (ExamQuestion.objects.filter(exam=exam).aggregate(m=Max("order")).get("m") or 0) + 1

        created_count = 0
        skipped_count = 0

        for idx, q in enumerate(parsed, start=1):
            if idx not in selected:
                continue

            # minimum şərt: A-D olsun
            if any(x not in q["options"] for x in ["A", "B", "C", "D"]):
                skipped_count += 1
                continue

            # per-question points (opsional input: points_1, points_2, ...)
            p_raw = (request.POST.get(f"points_{idx}") or "").strip()
            points = int(p_raw) if p_raw.isdigit() and int(p_raw) > 0 else default_points

            eq = ExamQuestion.objects.create(
                exam=exam,
                block=block_obj,
                text=q["text"],
                answer_mode=q["answer_mode"],
                order=start_order,
                points=points,
            )
            start_order += 1

            # options create (A–E varsa)
            for lab in "ABCDE":
                if lab in q["options"]:
                    ExamQuestionOption.objects.create(
                        question=eq,
                        text=q["options"][lab],
                        is_correct=(lab in q["correct"]),
                    )

            created_count += 1

        messages.success(
            request,
            pgettext("exams.view.question_bank.message", "questions_added_summary").format(
                created_count=created_count,
                skipped_count=skipped_count,
            ),
        )
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
            "warning_count": warning_count,
            "duplicate_count": duplicate_count,
            # >>> YENİ: Preview refresh olsa da input-lar dolu qalsın
            "rq_value": rq_value,
            "dp_value": dp_value,
            "question_bank_navigation_query": navigation_query,
            "navigation_from_section": navigation_from_section,
            "navigation_return_to": navigation_return_to,
        },
    )
