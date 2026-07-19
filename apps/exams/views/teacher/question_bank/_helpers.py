"""question_bank paketi — daxili köməkçilər və sabitlər."""

import logging
import re
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext

from apps.exams.constants import DEFAULT_EXAM_LANGUAGE, EXAM_LANGUAGE_CHOICES, EXAM_LANGUAGE_VALUES, QUESTION_RE
from apps.exams.models import ExamQuestion
from apps.exams.services.bulk_workbench import parse_points_payload, parse_selected_indices
from apps.exams.services.language_variants import active_variants
from apps.exams.services.parsing import END_QUESTION_RE

WRITTEN_QUESTION_PREFIX_RE = re.compile(r"^\s*\d+\s*[\.\)]\s*", re.MULTILINE)


logger = logging.getLogger(__name__)


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


def _is_internal_exam_management_path(candidate_path):
    raw_path = (candidate_path or "").strip()
    if not raw_path:
        return False

    try:
        match = resolve(urlsplit(raw_path).path)
    except Resolver404:
        return False

    return match.namespace == "exams" and match.url_name in {
        "teacher_questions_bank",
        "test_question_bank",
        "create_question_bank",
        "add_exam_question",
        "edit_exam_question",
        "delete_exam_question",
        "teacher_exam_results",
        "teacher_view_attempt",
        "teacher_check_attempt",
    }


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
    if _is_internal_exam_management_path(return_to):
        return_to = ""

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


def _default_exam_language(exam):
    """İmtahanın ilkin dili: tək aktiv variant varsa onun dili, yoxsa default `az`.

    Bu, toplu sual yükləmə panelində dil seçicisinin başlanğıc dəyəridir — köhnə
    (tək-dilli) imtahanlarda davranış dəyişmir, çoxdilli imtahanda isə müəllimin
    son işlədiyi məntiqlə uyğun gəlir.
    """
    languages = list(active_variants(exam).values_list("language", flat=True))
    if len(languages) == 1:
        return languages[0]
    return DEFAULT_EXAM_LANGUAGE


def _normalize_exam_language(value, exam):
    """POST/GET-dən gələn dil kodunu təhlükəsiz normallaşdırır."""
    code = (value or "").strip().lower()
    if code in EXAM_LANGUAGE_VALUES:
        return code
    return _default_exam_language(exam)


def _test_workbench_context(exam, navigation_query, *, selected_language=None):
    """Ortaq ``_bulk_question_workbench`` partial-ı üçün imtahan test bankı konteksti."""
    download_base = reverse("exams:test_question_bank_template_download", kwargs={"slug": exam.slug})
    detail_url = _append_navigation_query(
        reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}), navigation_query
    )
    questions_url = _append_navigation_query(
        reverse("exams:teacher_questions_bank", kwargs={"slug": exam.slug}), navigation_query
    )
    picker_url = _append_navigation_query(
        reverse("exams:exam_bank_picker", kwargs={"slug": exam.slug}), navigation_query
    )
    return {
        "wb_workbench_key": f"exam-{exam.slug}",
        "wb_title": exam.title,
        "wb_subtitle": pgettext("exams.template.test_question_bank", "subtitle_management_panel"),
        "wb_back_url": detail_url,
        "wb_back_label": pgettext("exams.template.test_question_bank", "action_back"),
        # Köhnə "Suallar bankına bax" düyməsi artıq idarəetmə keçididir — adı dəyişdik
        # ki, kitabxana picker modalı ilə qarışmasın.
        "wb_secondary_url": questions_url,
        "wb_secondary_label": pgettext("exams.template.test_question_bank", "Sualları idarə et"),
        "wb_secondary_icon": "fa-sliders",
        # "Suallar bankına bax" → kitabxana picker MODALINI açır (Part B).
        "wb_picker_url": picker_url,
        "wb_picker_label": pgettext("exams.template.test_question_bank", "Suallar bankına bax"),
        "wb_show_settings": True,
        "wb_ai_url": reverse("exams:ai_generate_question_bank", kwargs={"slug": exam.slug}),
        "wb_ai_context": "test",
        # İmtahan test bankı yalnız test formatındadır — amma dil seçici bank
        # toplu yükləməsi ilə eyni olsun deyə həmişə göstərilir.
        "wb_show_language": True,
        "wb_languages": EXAM_LANGUAGE_CHOICES,
        "wb_selected_language": selected_language or _default_exam_language(exam),
        "wb_show_format": False,
        "wb_format": "test",
        "wb_show_report": True,
        "wb_templates": [
            {"url": f"{download_base}?format=txt", "label": "TXT", "kind": "txt"},
        ],
        "wb_save_label": pgettext("exams.template.test_question_bank", "action_save_selected"),
    }


def _parse_written_questions(content_text):
    text = (content_text or "").strip()
    if not text:
        return []

    matches = list(WRITTEN_QUESTION_PREFIX_RE.finditer(text))
    if not matches:
        return [text]

    questions = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        question_text = text[start:end].strip()
        if question_text:
            questions.append(question_text)

    return questions


def _question_bank_title_context(exam):
    if exam.exam_type == "coding":
        return {
            "question_bank_page_title": pgettext("exams.template.create_question_bank", "Praktiki sual bankı"),
            "question_bank_heading": pgettext("exams.template.create_question_bank", "praktiki sual bankı"),
        }

    return {
        "question_bank_page_title": pgettext("exams.template.create_question_bank", "Yazılı sual bankı"),
        "question_bank_heading": pgettext("exams.template.create_question_bank", "yazılı sual bankı"),
    }


def _optional_non_negative_int(value):
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _parse_selected_question_indices(post_data):
    return parse_selected_indices(post_data)


def _parse_points_payload(post_data):
    return parse_points_payload(post_data)


def _sync_written_block_questions(block, question_texts, *, language=None, language_variant=None):
    existing_questions = list(block.questions.order_by("order", "id"))
    normalized_texts = [text for text in question_texts if text]
    effective_language = language or DEFAULT_EXAM_LANGUAGE

    for index, q_text in enumerate(normalized_texts, start=1):
        if index <= len(existing_questions):
            question = existing_questions[index - 1]
            update_fields = []

            if question.text != q_text:
                question.text = q_text
                update_fields.append("text")
            if question.order != index:
                question.order = index
                update_fields.append("order")
            if question.block_id != block.id:
                question.block = block
                update_fields.append("block")
            if question.exam_id != block.exam_id:
                question.exam = block.exam
                update_fields.append("exam")
            if question.answer_mode != "single":
                question.answer_mode = "single"
                update_fields.append("answer_mode")
            # Seçilmiş dili sualların hamısına tətbiq et (çoxdilli imtahan).
            if language is not None and question.language != effective_language:
                question.language = effective_language
                update_fields.append("language")
            if language_variant is not None and question.language_variant_id != language_variant.id:
                question.language_variant = language_variant
                update_fields.append("language_variant")

            if update_fields:
                question.save(update_fields=update_fields)
        else:
            ExamQuestion.objects.create(
                exam=block.exam,
                block=block,
                text=q_text,
                order=index,
                answer_mode="single",
                language=effective_language,
                language_variant=language_variant,
            )

    for stale_question in existing_questions[len(normalized_texts) :]:
        stale_question.delete()


_WARNING_TYPE_LABELS = {
    "duplicate_in_import": "Dublikat",
    "duplicate_in_bank": "Bankda dublikat",
    "already_in_exam": "Bankda dublikat",
    "duplicate_option_text": "Təkrar variant",
    "missing_option": "Variant çatışmır",
    "option_count_recommend_5": "Variant sayı",
    "option_count_too_low": "Variant sayı",
    "empty_option_text": "Boş variant",
    "correct_missing": "Düz cavab uyğunsuzluğu",
    "correct_too_long": "Uzunluq balansı",
    "correct_too_short": "Uzunluq balansı",
    "bulk_correct_too_long": "Test miqyaslı balans",
    "bulk_correct_too_short": "Test miqyaslı balans",
}


_WARNING_FEEDBACK = {
    "duplicate_in_import": (
        "Bu sual import faylında başqa sualla eynidir. Təkrarlanan suallardan birini silin "
        "və ya sual/variant mətnlərini fərqləndirin."
    ),
    "already_in_exam": (
        "Bu sual imtahan bankında artıq mövcuddur. Yeni sual kimi əlavə ediləcəksə mətni "
        "fərqləndirin, əks halda importdan çıxarın."
    ),
    "duplicate_in_bank": (
        "Bu sual bankda başqa bir sualla eynidir. Təkrarlanan suallardan birini silin "
        "və ya sual/variant mətnlərini fərqləndirin."
    ),
    "duplicate_option_text": "Eyni mətnli variantları dəyişin; hər variant ayrı məna daşımalıdır.",
    "missing_option": "A-D minimum variantlarını tamamlayın.",
    "option_count_recommend_5": "Mümkünsə E variantını əlavə edin ki, sual 5 variantlı standartla uyğun olsun.",
    "option_count_too_low": "Variant sayını ən azı 4-ə çatdırın.",
    "empty_option_text": "Boş variant mətnini doldurun və ya həmin variantı silib strukturu düzəldin.",
    "correct_missing": "Cavab sətrində göstərilən düzgün variant sualın variantları arasında olmalıdır.",
    "correct_too_long": (
        "Düzgün cavab digər variantlardan çox uzun görünür. Variantların uzunluğunu və "
        "detal səviyyəsini balanslaşdırın."
    ),
    "correct_too_short": (
        "Düzgün cavab digər variantlardan çox qısa görünür. Variantların uzunluğunu və "
        "detal səviyyəsini balanslaşdırın."
    ),
    "bulk_correct_too_long": "Test üzrə düzgün cavabların uzunluq patternini balanslaşdırın.",
    "bulk_correct_too_short": "Test üzrə düzgün cavabların qısalıq patternini balanslaşdırın.",
}


def _question_bank_warning_label(warning_type):
    return _WARNING_TYPE_LABELS.get(warning_type or "", warning_type or "Problem")


def _question_bank_feedback(warning_type):
    return _WARNING_FEEDBACK.get(
        warning_type or "",
        "Sual mətnini, variantları və düzgün cavab qeydini müəllim tərəfindən yenidən yoxlayın.",
    )


def _split_end_question_source_blocks(raw_text):
    blocks = []
    block = []

    for raw in (raw_text or "").splitlines():
        line = raw.strip()
        if END_QUESTION_RE.match(line):
            blocks.append(block)
            block = []
            continue
        if line:
            block.append(line)

    if block:
        blocks.append(block)

    return blocks


def _question_bank_source_diagnostics(raw_text, parsed):
    blocks = _split_end_question_source_blocks(raw_text)
    empty_blocks = [idx for idx, block in enumerate(blocks, start=1) if not block]
    nonempty_blocks = [block for block in blocks if block]

    declared = []
    no_visible_number_blocks = []
    for idx, block in enumerate(blocks, start=1):
        if not block:
            continue
        first_number = None
        for line in block:
            m_q = QUESTION_RE.match(line)
            if m_q:
                first_number = int(m_q.group(1))
                break
        if first_number is None:
            no_visible_number_blocks.append(idx)
        else:
            declared.append((idx, first_number))

    declared_numbers = [num for _, num in declared]
    duplicate_numbers = sorted({num for num in declared_numbers if declared_numbers.count(num) > 1})
    max_declared = max(declared_numbers) if declared_numbers else None
    missing_numbers = []
    if max_declared:
        visible_set = set(declared_numbers)
        missing_numbers = [num for num in range(1, max_declared + 1) if num not in visible_set]

    return {
        "source_block_count": len(blocks),
        "nonempty_block_count": len(nonempty_blocks),
        "empty_blocks": empty_blocks,
        "parsed_count": len(parsed or []),
        "dropped_nonempty_block_count": max(0, len(nonempty_blocks) - len(parsed or [])),
        "visible_number_count": len(declared_numbers),
        "max_declared_number": max_declared,
        "gap_from_max_declared": (max_declared - len(parsed or [])) if max_declared else None,
        "missing_numbers": missing_numbers,
        "duplicate_numbers": duplicate_numbers,
        "no_visible_number_blocks": no_visible_number_blocks,
    }


def _format_int_list(values, limit=40):
    values = list(values or [])
    if not values:
        return ""
    shown = ", ".join(str(v) for v in values[:limit])
    if len(values) > limit:
        shown += f" ... (+{len(values) - limit})"
    return shown


def _warning_reference_text(warning):
    warning_type = warning.get("type")
    if warning_type == "duplicate_in_import":
        refs = warning.get("all_refs") or []
        if not refs and warning.get("ref"):
            refs = [warning.get("ref")]
        return ", ".join(f"#{ref}" for ref in refs)
    if warning_type == "already_in_exam":
        parts = []
        if warning.get("ref_db_order"):
            parts.append(f"Bank sıra: {warning.get('ref_db_order')}")
        if warning.get("ref_db_id"):
            parts.append(f"ID: {warning.get('ref_db_id')}")
        return "; ".join(parts)
    return ""


def _question_bank_template_txt():
    brand = getattr(settings, "SITE_BRAND_NAME", "") or "Qərbi Kaspi Universiteti"
    return f"""\
# {brand} — Test sual bankı şablonu
# Hər sualın 4 və ya 5 variantı olmalıdır (A–E). Düz cavabı 3 üsuldan biri ilə qeyd edə bilərsiniz.
# 1) Cavabı sual sonunda yazın: "Cavab: B"
# 2) Düz variantın əvvəlinə * qoyun: "*B) Mətnim"
# 3) Heç bir işarə yoxdursa A standart olaraq düzgün sayılır.
# Çox cavablı suallarda virgül istifadə edin: "Cavab: A,C"
# Hər sualdan sonra boş sətir buraxın.
# Bu sətirlər (# ilə başlayanlar) və "END_QUESTION" işarəsi importda nəzərə alınmır.

1. Şəbəkədə məlumat hansı ölçü vahidi ilə ötürülür?
A) Bit
B) Bayt
C) Volt
D) Hertz
Cavab: A

2. Aşağıdakılardan hansı proqramlaşdırma dilidir?
A) Python
*B) JavaScript
*C) Java
D) Word
Cavab: A,B,C

3. HTML nədir?
A) Proqramlaşdırma dili
B) İşarələmə dili
C) Verilənlər bazası
D) Əməliyyat sistemi
*B)

4. OSI modelində ən aşağı səviyyə hansıdır?
A) Tətbiq səviyyəsi
B) Nəqliyyat səviyyəsi
*C) Fiziki səviyyə
D) Şəbəkə səviyyəsi
E) Heç biri
"""
