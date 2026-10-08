"""Sual göndərişi view-larının meta/forma köməkçiləri.

``submission_inbox.py``-dan çıxarılıb (modul ölçü qapısı): forma vəziyyəti,
müəllimin qrup/fənn mənbələri, məcburi meta yoxlaması və preview bayraqları.
View axını ``submission_inbox.py``-dadır.
"""

from django.utils.translation import pgettext

from apps.exams.constants import EXAM_LANGUAGE_VALUES, QUESTION_EXAM_KIND_VALUES
from apps.exams.services.question_submission import analyze_submission_text
from apps.exams.services.submission_sources import UNIT_PREFIX, resolve_unit_ids, teacher_submission_sources
from core.search_text import tolerant_match


def _normalize_language(raw_value):
    value = (raw_value or "").strip().lower()
    return value if value in EXAM_LANGUAGE_VALUES else "az"


def _valid_group_key(raw) -> bool:
    """Köhnə kohort id-si (rəqəm) və ya reyestr qrupu açarı (``u:<uuid>``)."""
    text = str(raw or "").strip()
    return text.isdigit() or (text.startswith(UNIT_PREFIX) and bool(resolve_unit_ids([text])))


def _form_state(request):
    raw_language = (request.POST.get("language") or "").strip().lower()
    raw_kind = (request.POST.get("exam_kind") or "").strip().lower()
    return {
        "title": (request.POST.get("title") or "").strip(),
        # Fənn seçimi registrar.Subject pk-sı ilə gəlir (2026-07 dəyişikliyi).
        "subject": (request.POST.get("subject") or "").strip(),
        # İmtahan növü (final/midterm/quiz) — view səviyyəsində məcburidir.
        "exam_kind": raw_kind if raw_kind in QUESTION_EXAM_KIND_VALUES else "",
        # Çox qrup seçimi: `group_ids` (getlist) — köhnə kohort «<id>» və ya reyestr
        # qrupu «u:<uuid>» (2026-10-08, S2). `group_id` geriyə-uyğunluq üçün.
        "group_ids": [str(g).strip() for g in request.POST.getlist("group_ids") if _valid_group_key(g)],
        "group_id": (request.POST.get("group_id") or "").strip(),
        "group_label": (request.POST.get("group_label") or "").strip(),
        "teacher_note": (request.POST.get("teacher_note") or "").strip(),
        # Xam dil (validasiya üçün) + normalizə olunmuş dəyər (saxlama üçün).
        "language_raw": raw_language,
        "language": _normalize_language(raw_language),
        "raw_text": request.POST.get("raw_text") or "",
    }


def _submission_sources(request, organization):
    """Müəllimin qrupları + fənləri — DƏRS YÜKÜ (açılışlar + təsdiqlənmiş bölgü) və
    köhnə kohortlar (2026-10-08, S2: əvvəl yalnız boş köhnə kohort cədvəli oxunurdu)."""
    return teacher_submission_sources(request.user, organization)


def _resolve_groups(form_state, groups):
    """Formadan seçilmiş qrupları həll edir (çox qrup). Yalnız müəllimə təyin
    olunmuş qruplar qəbul edilir. Qaytarır: (seçilmiş qruplar, birləşdirilmiş etiket)."""
    ids = {str(g) for g in form_state.get("group_ids", [])}
    if not ids and form_state.get("group_id"):  # geriyə-uyğunluq (tək seçim)
        ids = {form_state["group_id"]}
    chosen = [g for g in groups if str(g.id) in ids]
    return chosen, ", ".join(g.name for g in chosen)


def prefill_group_keys(submission, groups):
    """Redaktədə seçili qruplar: köhnə kohort FK-ları + adı ``group_label``-də olan
    reyestr qrupları (reyestr qrupu FK kimi saxlanmır — etiketdə qalır)."""
    keys = [str(g.id) for g in submission.student_groups.all()]
    if not keys and submission.student_group_id:
        keys = [str(submission.student_group_id)]
    names = {part.strip() for part in (submission.group_label or "").split(",") if part.strip()}
    keys += [g.key for g in groups if g.unit is not None and g.name in names]
    return keys


def _validate_submission_meta(form_state, *, groups, subjects):
    """Məcburi meta sahələrin ortaq yoxlaması (yeni göndəriş + yenidən göndərmə).

    Qaytarır: (error_message_or_None, chosen_groups, group_label, subject_obj).
    Fənn seçimi registrar.Subject pk-sı ilə gəlir; müəllimin öz fənləri
    siyahısında olmalıdır (siyahı boşdursa seçim mümkün deyil → xəta).
    """
    chosen_groups, group_label = _resolve_groups(form_state, groups)
    subject_by_pk = {str(s.pk): s for s in subjects}
    subject_obj = subject_by_pk.get(form_state["subject"])
    if not form_state["language_raw"]:
        return (
            pgettext("exams.view.question_submission.error", "İmtahan dilini seçin (məcburidir)."),
            chosen_groups,
            group_label,
            None,
        )
    if not form_state["subject"] or subject_obj is None:
        return (
            pgettext("exams.view.question_submission.error", "Fənni öz fənləriniz arasından seçin (məcburidir)."),
            chosen_groups,
            group_label,
            None,
        )
    if not form_state["exam_kind"]:
        return (
            pgettext("exams.view.question_submission.error", "İmtahan növünü seçin (məcburidir)."),
            chosen_groups,
            group_label,
            subject_obj,
        )
    if not chosen_groups:
        return (
            pgettext("exams.view.question_submission.error", "Ən azı bir qrup seçin (məcburidir)."),
            chosen_groups,
            group_label,
            subject_obj,
        )
    return None, chosen_groups, group_label, subject_obj


def annotate_preview_flags(questions):
    """Önizləmə partialı üçün hər suala has_error/has_warning bayraqları qoyur."""
    for question in questions or []:
        severities = {(w.get("severity") or "warning") for w in (question.get("warnings") or [])}
        question["has_error"] = "error" in severities
        question["has_warning"] = bool(severities - {"error"})
        question["has_visual_source"] = isinstance(question.get("source_index"), int)
    return questions


def _preview_context(raw_text):
    """Preview üçün parse nəticəsi + say xülasəsi (müəllim və mərkəz eyni şeyi görür)."""
    parsed, counts = analyze_submission_text(raw_text)
    return {"preview_parsed": annotate_preview_flags(parsed), "preview_counts": counts}


# ---------------------------------------------------------------------------
# Sual siyahısı — lazy load + filtr + axtarış (review səhifəsi)
# ---------------------------------------------------------------------------
QUESTION_FLAG_VALUES = ("error", "warning", "clean")

# Review sual siyahısının səhifə ölçüsü (ilkin render + lazy fraqmentlər).
QUESTIONS_PAGE_SIZE = 20


def annotate_display_numbers(questions):
    """Hər suala TAM siyahıdakı 1-əsaslı nömrəsini yazır — dilimlə (slice)
    render olunanda nömrələr sabit qalsın deyə (forloop.counter yaramır)."""
    for index, question in enumerate(questions or [], start=1):
        question["display_no"] = index
    return questions


def snapshot_flag_counts(questions):
    """Filtr pilləri üçün saylar. Bir sualda həm xəta, həm xəbərdarlıq ola
    bilər — saylar müstəqildir (başlıq kartları ilə eyni semantika)."""
    counts = {"all": len(questions or []), "error": 0, "warning": 0, "clean": 0}
    for question in questions or []:
        if question.get("has_error"):
            counts["error"] += 1
        if question.get("has_warning"):
            counts["warning"] += 1
        if not question.get("has_error") and not question.get("has_warning"):
            counts["clean"] += 1
    return counts


def filter_snapshot_questions(questions, *, flag="", query=""):
    """Snapshot suallarını bayraq (error/warning/clean) və mətn axtarışı ilə
    süz. Axtarış sual mətnində və variantlarda böyük/kiçik hərfsiz, az/ing hərfə
    dözümlü və tokenli işləyir (``tolerant_match``, sahib 2026-09-26)."""
    query = (query or "").strip()
    result = []
    for question in questions or []:
        if flag == "error" and not question.get("has_error"):
            continue
        if flag == "warning" and not question.get("has_warning"):
            continue
        if flag == "clean" and (question.get("has_error") or question.get("has_warning")):
            continue
        if query:
            options = question.get("options") or {}
            option_texts = [str(value) for value in options.values()] if isinstance(options, dict) else []
            if not tolerant_match(query, str(question.get("text") or ""), *option_texts):
                continue
        result.append(question)
    return result


__all__ = [
    "QUESTION_FLAG_VALUES",
    "QUESTIONS_PAGE_SIZE",
    "_form_state",
    "_normalize_language",
    "_preview_context",
    "_resolve_groups",
    "_submission_sources",
    "_validate_submission_meta",
    "annotate_display_numbers",
    "annotate_preview_flags",
    "filter_snapshot_questions",
    "prefill_group_keys",
    "snapshot_flag_counts",
]
