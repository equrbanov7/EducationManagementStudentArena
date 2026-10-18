"""question_library paketi — picker."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import pgettext

from apps.exams.constants import EXAM_LANGUAGE_CHOICES
from apps.exams.services.access_policy import _ensure_teacher, ensure_can_manage_exam_questions
from apps.exams.services.question_bank_attach import (
    accessible_banks,
    attach_bank_questions_to_exam,
    bank_questions_queryset,
)
from apps.exams.views.shared.breadcrumbs import exam_breadcrumbs
from apps.exams.views.shared.tenant import get_teacher_exam_or_404
from core.tenancy import get_request_organization

from ._shared import (
    _DIFFICULTY_CHOICES,
    _PICKER_PAGE_SIZE,
    _bank_language_stats,
    _exam_compatible_question_type,
    _first_or_default_block,
    _is_modal_request,
)


def _attached_source_ids(exam, bank_question_ids):
    """İmtahanda artıq snapshot-u olan bank sualı id-ləri (təkrar əlavənin qarşısı)."""
    ids = [qid for qid in bank_question_ids if qid]
    if not ids:
        return set()
    return set(exam.questions.filter(source_bank_question_id__in=ids).values_list("source_bank_question_id", flat=True))


@login_required
def exam_bank_picker(request, slug):
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    ensure_can_manage_exam_questions(request.user, exam)
    organization = get_request_organization(request)
    is_modal = _is_modal_request(request)
    compatible_type = _exam_compatible_question_type(exam)
    # Yalnız imtahan tipinə uyğun banklar görünsün (test→test bankı, yazılı→yazılı).
    banks = (
        accessible_banks(request.user, organization)
        .filter(default_question_type=compatible_type)
        .order_by("-created_at")
    )

    # 2026-10-19: rəqəm olmayan `bank` (məs. ?bank=abc) əvvəl ValueError → 500 verirdi.
    bank_id = (request.GET.get("bank") or request.POST.get("bank") or "").strip()
    selected_bank = banks.filter(id=int(bank_id)).first() if bank_id.isdigit() else None
    is_attach = request.method == "POST" and request.POST.get("action") == "attach"
    if is_attach and bank_id and selected_bank is None:
        # Əhatədən kənar (başqa təşkilat/müəllim, deaktiv və ya tipə uyğunsuz) bank — 404.
        raise Http404

    if is_attach:
        if selected_bank is None:
            if is_modal:
                return JsonResponse(
                    {"success": False, "error": str(pgettext("exams.view.bank.message", "Əvvəlcə bank seçin."))},
                    status=400,
                )
            messages.error(request, pgettext("exams.view.bank.message", "Əvvəlcə bank seçin."))
        else:
            # "Hamısını seç" rejimi: cari filtrlərə uyğun BÜTÜN sualları əlavə et
            # (yalnız görünən 300-ü deyil), istisna edilənləri çıxmaqla.
            if request.POST.get("select_all") == "1":
                excluded = {int(v) for v in request.POST.getlist("excluded_ids") if v.isdigit()}
                matching_qs = bank_questions_queryset(
                    selected_bank,
                    question_type=compatible_type,
                    language=(request.POST.get("language") or "").strip() or None,
                    difficulty=(request.POST.get("difficulty") or "").strip() or None,
                    search=(request.POST.get("q") or "").strip() or None,
                )
                valid_ids = [qid for qid in matching_qs.values_list("id", flat=True) if qid not in excluded]
            else:
                raw_ids = request.POST.getlist("question_ids")
                requested_ids = [int(value) for value in raw_ids if value.isdigit()]
                # Yalnız imtahanla uyğun tipdə (test/yazılı) sualları əlavə et.
                valid_ids = list(
                    bank_questions_queryset(selected_bank, question_type=compatible_type)
                    .filter(id__in=requested_ids)
                    .values_list("id", flat=True)
                )
            # 2026-10-19: artıq imtahanda olan bank sualı (source_bank_question) təkrar əlavə olunmur —
            # əvvəl eyni sual iki dəfə snapshot olunurdu. Picker onları «artıq əlavə olunub» göstərir.
            already = _attached_source_ids(exam, valid_ids)
            skipped = sum(1 for qid in valid_ids if qid in already)
            valid_ids = [qid for qid in valid_ids if qid not in already]
            # Yazılı/praktiki imtahanda suallar birinci bloka düşür (sonradan müəllim
            # özü bloklara bölə bilər). Test imtahanında blok məcburi deyil.
            attach_block = None if exam.exam_type == "test" else _first_or_default_block(exam)
            created = attach_bank_questions_to_exam(exam, valid_ids, block=attach_block, created_by=request.user)
            success_msg = pgettext("exams.view.bank.message", "{count} sual imtahana əlavə olundu.").format(
                count=len(created)
            )
            # Yönləndirmə: test → test bankı; yazılı/praktiki → blok redaktoru.
            if exam.exam_type == "test":
                redirect_url = reverse("exams:test_question_bank", kwargs={"slug": exam.slug})
            else:
                redirect_url = reverse("exams:create_question_bank", kwargs={"slug": exam.slug})
                # Müəllimə bloklara bölmə imkanı barədə məlumat ver (redaktorda görünür).
                if created and attach_block is not None:
                    messages.info(
                        request,
                        pgettext(
                            "exams.view.bank.message",
                            "{count} sual “{block}” blokuna əlavə olundu. İstəsəniz redaktorda onları "
                            "ayrı bölmələrə bölə bilərsiniz.",
                        ).format(count=len(created), block=attach_block.name),
                    )
            if skipped and not created:
                success_msg = pgettext(
                    "exams.view.bank.message", "Seçilmiş suallar artıq imtahanda var — yeni sual əlavə olunmadı."
                )
            elif skipped:
                skipped_msg = pgettext("exams.view.bank.message", "{count} sual artıq imtahanda idi — ötürüldü.")
                success_msg = f"{success_msg} {skipped_msg.format(count=skipped)}"
            if is_modal:
                # Modal səhifəni yeniləyəcəksə (yazılı redaktor: blok mətni serverdən gəlir) mesaj
                # növbəti səhifədə toast kimi görünsün; qalmırsa JS özü toast göstərir (təkrar olmasın).
                if request.POST.get("after") == "reload":
                    (messages.success if created else messages.warning)(request, success_msg)
                return JsonResponse(
                    {
                        "success": True,
                        "count": len(created),
                        "skipped": skipped,
                        "message": success_msg,
                        "redirect_url": redirect_url,
                    }
                )
            (messages.success if created or not skipped else messages.warning)(request, success_msg)
            return redirect(redirect_url)

    try:
        page = max(1, int(request.GET.get("page") or 1))
    except (TypeError, ValueError):
        page = 1

    items_mode = request.GET.get("items") == "1"

    questions = []
    total_count = 0
    bank_language_stats = []
    bank_total_questions = 0
    bank_language_count = 0
    has_more = False
    attached_count = 0
    if selected_bank is not None:
        # Variantlar (akkordeon) üçün prefetch — N+1 sorğunun qarşısını alır.
        question_qs = bank_questions_queryset(
            selected_bank,
            question_type=compatible_type,
            language=(request.GET.get("language") or "").strip() or None,
            difficulty=(request.GET.get("difficulty") or "").strip() or None,
            search=(request.GET.get("q") or "").strip() or None,
        ).prefetch_related("options")
        offset = (page - 1) * _PICKER_PAGE_SIZE
        if not items_mode:
            attached_count = question_qs.filter(
                id__in=exam.questions.filter(source_bank_question__isnull=False).values("source_bank_question_id")
            ).count()
        if items_mode:
            # Scroll əlavəsi: stats/count sorğusu YOX — bir əlavə element çəkib
            # növbəti səhifə olub-olmadığını bilirik (daha sürətli).
            window = list(question_qs[offset : offset + _PICKER_PAGE_SIZE + 1])
            questions = window[:_PICKER_PAGE_SIZE]
            has_more = len(window) > _PICKER_PAGE_SIZE
        else:
            bank_language_stats, bank_total_questions, bank_language_count = _bank_language_stats(
                selected_bank, question_type=compatible_type
            )
            total_count = question_qs.count()
            questions = list(question_qs[offset : offset + _PICKER_PAGE_SIZE])
            has_more = total_count > offset + len(questions)

    # Bu səhifənin artıq imtahanda olan sualları — BİR sorğu (N+1 yox).
    attached_ids = _attached_source_ids(exam, [q.id for q in questions])
    page_start = (page - 1) * _PICKER_PAGE_SIZE + 1 if questions else 0
    context = {
        "exam": exam,
        # 2026-10-10 redizayn (müstəqil səhifə): ortaq başlıq + səhifələmə aralığı «1–40 / 120».
        "exam_crumbs": exam_breadcrumbs(
            request, exam, current=pgettext("exams.template.bank_picker", "Bankdan sual əlavə et")
        ),
        "page_start": page_start,
        "page_end": page_start + len(questions) - 1 if questions else 0,
        "prev_page": page - 1 if page > 1 else None,
        "picker_page_size": _PICKER_PAGE_SIZE,
        "banks": banks,
        "selected_bank": selected_bank,
        "questions": questions,
        "total_count": total_count,
        "attached_ids": attached_ids,
        "attached_count": attached_count,
        "selectable_count": max(0, total_count - attached_count),
        "bank_language_stats": bank_language_stats,
        "bank_total_questions": bank_total_questions,
        "bank_language_count": bank_language_count,
        "compatible_type": compatible_type,
        "language_choices": EXAM_LANGUAGE_CHOICES,
        "difficulty_choices": _DIFFICULTY_CHOICES,
        "search_query": (request.GET.get("q") or "").strip(),
        "language_filter": (request.GET.get("language") or "").strip(),
        "difficulty_filter": (request.GET.get("difficulty") or "").strip(),
        "picker_url": reverse("exams:exam_bank_picker", kwargs={"slug": exam.slug}),
        "page": page,
        "next_page": page + 1,
        "has_more": has_more,
    }
    # AJAX rejimləri: yalnız sual elementləri (scroll əlavəsi) və ya tam content (filtr).
    if request.GET.get("items") == "1":
        return render(request, "exams/teacher/partials/_exam_bank_picker_items.html", context)
    if request.GET.get("content") == "1":
        return render(request, "exams/teacher/partials/_exam_bank_picker_content.html", context)
    if is_modal:
        return render(request, "exams/teacher/partials/_exam_bank_picker_modal.html", context)
    return render(request, "exams/teacher/exam_bank_picker.html", context)
