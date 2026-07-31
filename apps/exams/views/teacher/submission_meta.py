"""Sual göndərişi view-larının meta/forma köməkçiləri.

``submission_inbox.py``-dan çıxarılıb (modul ölçü qapısı): forma vəziyyəti,
müəllimin qrup/fənn mənbələri, məcburi meta yoxlaması və preview bayraqları.
View axını ``submission_inbox.py``-dadır.
"""

from django.utils.translation import pgettext

from apps.exams.constants import EXAM_LANGUAGE_VALUES, QUESTION_EXAM_KIND_VALUES
from apps.exams.models import StudentGroup
from apps.exams.services.question_submission import analyze_submission_text


def _normalize_language(raw_value):
    value = (raw_value or "").strip().lower()
    return value if value in EXAM_LANGUAGE_VALUES else "az"


def _form_state(request):
    raw_language = (request.POST.get("language") or "").strip().lower()
    raw_kind = (request.POST.get("exam_kind") or "").strip().lower()
    return {
        "title": (request.POST.get("title") or "").strip(),
        # Fənn seçimi registrar.Subject pk-sı ilə gəlir (2026-07 dəyişikliyi).
        "subject": (request.POST.get("subject") or "").strip(),
        # İmtahan növü (final/midterm/quiz) — view səviyyəsində məcburidir.
        "exam_kind": raw_kind if raw_kind in QUESTION_EXAM_KIND_VALUES else "",
        # Çox qrup seçimi: `group_ids` (getlist). `group_id` geriyə-uyğunluq üçün.
        "group_ids": [g for g in request.POST.getlist("group_ids") if str(g).strip().isdigit()],
        "group_id": (request.POST.get("group_id") or "").strip(),
        "group_label": (request.POST.get("group_label") or "").strip(),
        "teacher_note": (request.POST.get("teacher_note") or "").strip(),
        # Xam dil (validasiya üçün) + normalizə olunmuş dəyər (saxlama üçün).
        "language_raw": raw_language,
        "language": _normalize_language(raw_language),
        "raw_text": request.POST.get("raw_text") or "",
    }


def _teacher_groups(request, organization):
    """Müəllimin bu təşkilatdakı qrupları (dropdown üçün) — fənlərlə birlikdə."""
    from django.db.models import Q

    return (
        StudentGroup.objects.filter(organization=organization)
        .filter(Q(teacher=request.user) | Q(teachers=request.user))
        .prefetch_related("subjects")
        .distinct()
        .order_by("name")
    )


def _teacher_subjects(request, organization, *, groups=None):
    """Müəllimin ÖZ fənləri — təyin olunduğu qrupların fənlərinin birləşməsi
    (registrar.Subject). Sual göndərişində fənn seçimi bu siyahıdan gəlir
    (qrupdan asılı deyil — 2026-07 dəyişikliyi)."""
    from apps.registrar.models import Subject

    group_ids = [g.id for g in (groups if groups is not None else _teacher_groups(request, organization))]
    if not group_ids:
        return Subject.objects.none()
    return (
        Subject.objects.filter(organization=organization, student_groups__in=group_ids)
        .distinct()
        .order_by("code", "name")
    )


def _resolve_groups(form_state, groups):
    """Formadan seçilmiş qrupları həll edir (çox qrup). Yalnız müəllimə təyin
    olunmuş qruplar qəbul edilir. Qaytarır: (seçilmiş qruplar, birləşdirilmiş etiket)."""
    ids = {str(g) for g in form_state.get("group_ids", [])}
    if not ids and form_state.get("group_id"):  # geriyə-uyğunluq (tək seçim)
        ids = {form_state["group_id"]}
    chosen = [g for g in groups if str(g.id) in ids]
    return chosen, ", ".join(g.name for g in chosen)


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
    süz. Axtarış sual mətnində və variantlarda böyük/kiçik hərfsiz işləyir."""
    query = (query or "").strip().lower()
    result = []
    for question in questions or []:
        if flag == "error" and not question.get("has_error"):
            continue
        if flag == "warning" and not question.get("has_warning"):
            continue
        if flag == "clean" and (question.get("has_error") or question.get("has_warning")):
            continue
        if query:
            haystack = str(question.get("text") or "").lower()
            options = question.get("options") or {}
            if isinstance(options, dict):
                haystack += " " + " ".join(str(value).lower() for value in options.values())
            if query not in haystack:
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
    "_teacher_groups",
    "_teacher_subjects",
    "_validate_submission_meta",
    "annotate_display_numbers",
    "annotate_preview_flags",
    "filter_snapshot_questions",
    "snapshot_flag_counts",
]
