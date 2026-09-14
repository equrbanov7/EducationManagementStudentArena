"""
Toplu sual "workbench" analiz mühərriki — DESTİNASİYADAN ASILI DEYİL.

Bu modul ``test_question_bank`` view-də olan preview/validasiya məntiqini tək
mənbədə toplayır ki, eyni "premium" preview (dublikat aşkarlanması, struktur/
balans xəbərdarlıqları, kateqoriya sayğacları, meta bayraqları) həm imtahan test
bankında, həm müstəqil sual bankında, həm də dil variantı yükləməsində EYNİ cür
işləsin (DRY).

Performans qeydi: mühərrik tək keçiddə (single pass) işləyir, DB-ə YALNIZ
çağıran view-in əvvəlcədən hazırladığı "fingerprint map" ilə müraciət olunur —
yəni mövcud suallar bir dəfə (prefetch ilə) oxunur, analiz isə in-memory aparılır.
"""

from __future__ import annotations

import json

from django.utils.translation import pgettext

from apps.exams.services.bulk_confidence import finalize_analysis
from apps.exams.services.parsing import parse_bulk_mcq
from apps.exams.services.parsing.math_text import sanitize_math_text
from apps.exams.services.parsing.media_markers import extract_media_refs
from apps.exams.services.utils import _norm

_WARN_CTX = "exams.view.question_bank.warning"

_OPTION_LABELS = ("A", "B", "C", "D", "E")


# ---------------------------------------------------------------------------
# Fingerprint köməkçiləri (dublikat müqayisəsi üçün)
# ---------------------------------------------------------------------------
def fingerprint_parsed(question: dict) -> str:
    """Parse olunmuş sualdan (text + A..E variantları) fingerprint qurur."""
    options = question.get("options") or {}
    return _norm(question.get("text", "")) + "||" + "||".join(_norm(options.get(label, "")) for label in _OPTION_LABELS)


def fingerprint_from_texts(text: str, option_texts) -> str:
    """Mətn + sıralı variant mətnləri (A..E) siyahısından fingerprint qurur."""
    option_map = {}
    for index, opt_text in enumerate(list(option_texts)[:5]):
        option_map[_OPTION_LABELS[index]] = opt_text
    return _norm(text) + "||" + "||".join(_norm(option_map.get(label, "")) for label in _OPTION_LABELS)


def _short_preview(text: str, length: int = 60) -> str:
    """DB/dublikat referansı üçün qısa, tək sətirli preview."""
    clean = (text or "").strip().replace("\n", " ")
    if len(clean) <= length:
        return clean
    return clean[: length - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# POST parser köməkçiləri (save formundan seçim + bal) — ortaq istifadə üçün
# ---------------------------------------------------------------------------
def parse_selected_indices(post_data):
    """
    Save formundan seçilmiş sual indekslərini qaytarır.

    - ``None``  → "selected" ümumiyyətlə göndərilməyib (hamısı seçilmiş kimi say).
    - ``set()`` → açıq şəkildə heç nə seçilməyib.
    """
    if "selected_indices" in post_data:
        compact_value = (post_data.get("selected_indices") or "").strip()
        if compact_value:
            raw_values = compact_value.split(",")
        else:
            legacy_values = post_data.getlist("selected")
            if legacy_values:
                raw_values = legacy_values
            else:
                return set()
    else:
        raw_values = post_data.getlist("selected")
        if not raw_values:
            return None

    selected = set()
    for raw_value in raw_values:
        try:
            value = int(str(raw_value).strip())
        except (TypeError, ValueError):
            continue
        if value > 0:
            selected.add(value)
    return selected


def parse_points_payload(post_data):
    """``points_payload`` JSON sahəsini {index_str: points_str} dict-inə çevirir."""
    raw_payload = (post_data.get("points_payload") or "").strip()
    if not raw_payload:
        return {}
    try:
        payload = json.loads(raw_payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


# ---------------------------------------------------------------------------
# Mövcud sualların fingerprint xəritəsini qur (DB → in-memory)
# ---------------------------------------------------------------------------
def exam_question_fp_map(exam, *, language=None):
    """
    İmtahanın mövcud suallarının fingerprint xəritəsi.

    ``ExamQuestionOption`` etiket saxlamadığı üçün variantlar SIRA ilə (A..E)
    götürülür — bu, köhnə ``test_question_bank`` davranışı ilə eynidir.
    """
    queryset = exam.questions.all().prefetch_related("options")
    if language:
        queryset = queryset.filter(language=language)
    fp_map = {}
    for question in queryset.order_by("order", "id"):
        option_texts = [opt.text for opt in question.options.all()]
        fp = fingerprint_from_texts(question.text, option_texts)
        fp_map[fp] = {
            "order": question.order or question.pk,
            "db_id": question.pk,
            "preview": _short_preview(question.text),
        }
    return fp_map


def bank_question_fp_map(bank, *, language=None):
    """
    Müstəqil bankın test (MCQ) suallarının fingerprint xəritəsi.

    ``BankQuestionOption`` etiket (label) saxladığı üçün variantlar etiketə görə
    (A..E) düzülür.
    """
    queryset = bank.library_questions.filter(is_active=True, question_type="test").prefetch_related("options")
    if language:
        queryset = queryset.filter(language=language)
    fp_map = {}
    for index, question in enumerate(queryset.order_by("-created_at", "id"), start=1):
        label_to_text = {opt.label: opt.text for opt in question.options.all() if opt.label}
        ordered = [label_to_text.get(label, "") for label in _OPTION_LABELS]
        fp = fingerprint_from_texts(question.text, ordered)
        fp_map[fp] = {
            "order": index,
            "db_id": question.pk,
            "preview": _short_preview(question.text),
        }
    return fp_map


def bank_written_text_map(bank, *, language=None):
    """Müstəqil bankın yazılı suallarının mətn fingerprint xəritəsi (dublikat üçün)."""
    queryset = bank.library_questions.filter(is_active=True, question_type="written")
    if language:
        queryset = queryset.filter(language=language)
    text_map = {}
    for index, question in enumerate(queryset.order_by("-created_at", "id"), start=1):
        text_map[_norm(question.text)] = {
            "order": index,
            "db_id": question.pk,
            "preview": _short_preview(question.text),
        }
    return text_map


def exam_written_text_map(exam, *, language=None):
    """İmtahanın yazılı suallarının mətn fingerprint xəritəsi (dublikat üçün)."""
    queryset = exam.questions.all()
    if language:
        queryset = queryset.filter(language=language)
    text_map = {}
    for question in queryset.order_by("order", "id"):
        text_map[_norm(question.text)] = {
            "order": question.order or question.pk,
            "db_id": question.pk,
            "preview": _short_preview(question.text),
        }
    return text_map


# ---------------------------------------------------------------------------
# MCQ (test) analiz mühərriki
# ---------------------------------------------------------------------------
def analyze_mcq_bulk(raw_text, *, existing_fp_map=None, already_msg_key="already_in_exam"):
    """
    Toplu MCQ mətnini parse edib tam preview kontekstini qaytarır.

    Args:
        raw_text: müəllimin daxil etdiyi / fayldan oxunan xam mətn.
        existing_fp_map: {fingerprint: {"order", "db_id", "preview"}} — mövcud
            (artıq saxlanmış) sualların xəritəsi. Dublikat yoxlanışı bununla edilir.
        already_msg_key: "artıq mövcuddur" mesajının pgettext açarı
            ("already_in_exam" — mövcud tərcümələr təkrar istifadə olunur).

    Returns:
        dict(parsed, category_counts, warning_count, duplicate_count,
             error_count, test_level_warnings)
    """
    existing_fp_map = existing_fp_map or {}
    parsed = parse_bulk_mcq(raw_text) or []

    # Təhlükəsizlik: hər sualda warnings açarı olsun
    for question in parsed:
        question.setdefault("warnings", [])

    # ---- Dublikat: import daxilində ----
    fp_groups = {}
    for index, question in enumerate(parsed, start=1):
        fp_groups.setdefault(fingerprint_parsed(question), []).append(index)

    for indices in fp_groups.values():
        if len(indices) < 2:
            continue
        for position, index in enumerate(indices):
            others = [i for i in indices if i != index]
            primary_ref = others[0]
            primary_preview = _short_preview(parsed[primary_ref - 1].get("text", ""))
            if position == 0:
                msg = pgettext(_WARN_CTX, "duplicate_in_import_first").format(
                    index=index,
                    next_index=others[0],
                    count=len(others),
                    preview=_short_preview(parsed[others[0] - 1].get("text", "")),
                )
            else:
                msg = pgettext(_WARN_CTX, "duplicate_in_import").format(
                    index=index,
                    previous_index=primary_ref,
                    preview=primary_preview,
                )
            parsed[index - 1]["warnings"].append(
                {
                    "type": "duplicate_in_import",
                    "severity": "error",
                    "msg": msg,
                    "ref": primary_ref if position > 0 else others[0],
                    "all_refs": others,
                }
            )

    # ---- Dublikat: mövcud bazada artıq var? ----
    for index, question in enumerate(parsed, start=1):
        matched = existing_fp_map.get(fingerprint_parsed(question))
        if matched is not None:
            question["warnings"].append(
                {
                    "type": "already_in_exam",
                    "severity": "error",
                    "msg": pgettext(_WARN_CTX, already_msg_key).format(
                        index=index,
                        db_index=matched["order"],
                        preview=matched["preview"],
                    ),
                    "ref_db_id": matched["db_id"],
                    "ref_db_order": matched["order"],
                }
            )

    # ---- Test miqyasında "yalnız doğru cavab uzun/qısa" pattern-i ----
    test_level_warnings = _detect_length_bias(parsed)

    # ---- Meta + kateqoriya sayğacları (W3 2026-09-14: bulk_confidence, düstur/şəkil inamı) ----
    return finalize_analysis(parsed, test_level_warnings)


def _detect_length_bias(parsed):
    """Testin böyük hissəsində doğru cavabın uzun/qısa olması pattern-i."""
    if not parsed:
        return []

    long_correct = 0
    short_correct = 0
    applicable = 0
    for question in parsed:
        options = question.get("options", {}) or {}
        correct = [c for c in question.get("correct", []) if c in options]
        wrong = [label for label in options if label not in correct]
        if not correct or not wrong:
            continue
        applicable += 1
        lens_correct = [len((options.get(c) or "").strip()) for c in correct]
        lens_wrong = [len((options.get(w) or "").strip()) for w in wrong]
        if not lens_correct or not lens_wrong:
            continue
        max_c = max(lens_correct)
        avg_w = sum(lens_wrong) / max(1, len(lens_wrong))
        if max_c >= 15 and avg_w > 0 and max_c >= avg_w * 1.8:
            long_correct += 1
        if max(lens_wrong) >= 15 and max_c > 0 and max_c <= avg_w * 0.4:
            short_correct += 1

    threshold = max(3, int(applicable * 0.4))
    warnings = []
    if applicable >= 5 and long_correct >= threshold:
        warnings.append(
            {
                "type": "bulk_correct_too_long",
                "severity": "warning",
                "msg": pgettext(_WARN_CTX, "bulk_correct_too_long").format(
                    ratio=int((long_correct / applicable) * 100)
                ),
            }
        )
    if applicable >= 5 and short_correct >= threshold:
        warnings.append(
            {
                "type": "bulk_correct_too_short",
                "severity": "warning",
                "msg": pgettext(_WARN_CTX, "bulk_correct_too_short").format(
                    ratio=int((short_correct / applicable) * 100)
                ),
            }
        )
    return warnings


# ---------------------------------------------------------------------------
# Yazılı (free-text) analiz mühərriki
# ---------------------------------------------------------------------------
def parse_written_bulk(raw_text):
    """
    Toplu yazılı sual mətnini ayrı-ayrı suallara bölür.

    Format ``test_question_bank`` yazılı bankı ilə eynidir: hər sual ``1.``/``2)``
    kimi nömrə ilə başlayır. Nömrə yoxdursa bütün mətn tək sual sayılır.
    """
    text = (raw_text or "").strip()
    if not text:
        return []

    import re

    prefix_re = re.compile(r"^\s*\d+\s*[\.\)]\s*", re.MULTILINE)
    matches = list(prefix_re.finditer(text))
    if not matches:
        return [text]

    questions = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            questions.append(body)
    return questions


def analyze_written_bulk(raw_text, *, existing_text_map=None):
    """
    Yazılı sualları parse edib MCQ analizi ilə EYNİ formada preview kontekstini
    qaytarır (partial-ın eyni şablonu istifadə etməsi üçün).

    Hər element ``{"text", "options": {}, "correct": [], "warnings", "meta"}``
    formasındadır — ``options`` boşdur, ona görə partial variant gridini göstərmir.
    """
    existing_text_map = existing_text_map or {}
    raw_questions = parse_written_bulk(raw_text)

    parsed = []
    seen_fingerprints = {}
    for body in raw_questions:
        question = {
            "text": body,
            "options": {},
            "correct": [],
            "answer_mode": "single",
            "question_type": "written",
            "warnings": [],
        }
        # W3 2026-09-14: DOCX şəkil markerləri → media_refs; LaTeX sanitizasiya.
        extract_media_refs(question)
        question["text"], issues = sanitize_math_text(question["text"])
        for issue in issues:
            question["warnings"].append(
                {
                    "type": issue["type"],
                    "severity": "warning",
                    "msg": pgettext("exams.service.parsing.warning", issue["type"]).format(
                        command=issue.get("command") or "", preview=issue.get("preview") or ""
                    ),
                }
            )
        parsed.append(question)

    # Dublikat: import daxilində
    for index, question in enumerate(parsed, start=1):
        fp = _norm(question["text"])
        seen_fingerprints.setdefault(fp, []).append(index)

    for indices in seen_fingerprints.values():
        if len(indices) < 2:
            continue
        for position, index in enumerate(indices):
            others = [i for i in indices if i != index]
            primary_ref = others[0]
            if position == 0:
                msg = pgettext(_WARN_CTX, "duplicate_in_import_first").format(
                    index=index,
                    next_index=others[0],
                    count=len(others),
                    preview=_short_preview(parsed[others[0] - 1]["text"]),
                )
            else:
                msg = pgettext(_WARN_CTX, "duplicate_in_import").format(
                    index=index,
                    previous_index=primary_ref,
                    preview=_short_preview(parsed[primary_ref - 1]["text"]),
                )
            parsed[index - 1]["warnings"].append(
                {
                    "type": "duplicate_in_import",
                    "severity": "error",
                    "msg": msg,
                    "ref": primary_ref if position else others[0],
                }
            )

    # Dublikat: mövcud bazada
    for index, question in enumerate(parsed, start=1):
        matched = existing_text_map.get(_norm(question["text"]))
        if matched is not None:
            question["warnings"].append(
                {
                    "type": "already_in_exam",
                    "severity": "error",
                    "msg": pgettext(_WARN_CTX, "already_in_exam").format(
                        index=index, db_index=matched["order"], preview=matched["preview"]
                    ),
                    "ref_db_id": matched["db_id"],
                    "ref_db_order": matched["order"],
                }
            )

    # Struktur: çox qısa / boş mətn
    for question in parsed:
        stripped = (question["text"] or "").strip()
        if len(stripped) < 3:
            question["warnings"].append(
                {
                    "type": "empty_option_text",
                    "severity": "error",
                    "msg": pgettext("exams.service.parsing.warning", "empty_option_text").format(option="—"),
                }
            )

    return finalize_analysis(parsed, [])
