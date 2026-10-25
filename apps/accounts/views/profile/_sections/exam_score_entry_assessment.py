"""Profil «exam-score-entry» — İMTAHAN NÖVÜ (midterm / final) və «Yekun» / 15 dəqiqə vəziyyəti (2026-10-25).

Sahib: «İmtahan növü: midterm / final seçimi ekranın başında, AYDIN görünsün (böyük nişan «MİDTERM (maks 30)» /
«FİNAL (maks 50)»). Sistem özü semestr təqviminə görə defolt seçir … daxil edən dəyişə bilər» və «daxil edən
təsdiqdən sonra 15 dəqiqə ərzində dəyişə bilər (ekranda geri sayım/izah)».

Qaydalar ``apps/registrar/exam_score_assessment.py``-dadır (server avtoritetdir); bu modul yalnız səthin
kontekstini qurur:

* :func:`resolve_assessment` — ``?ese_assessment=`` (yalnız mövcud növ) və ya təqvim defoltu;
* :func:`fill_assessment` — böyük seçim düymələri (URL + tavan), sütun redaktoru, sətir-sətir «Yekun» /
  «N dəqiqə ərzində dəyişə bilərsiniz» vəziyyəti (``ChangeRules`` — BİR sorğu + RİM üzvlüyü BİR sorğu),
  qaralama API-si və tələbəyə görünmə gecikməsi.
"""

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from apps.accounts.views._helpers.formatting import _append_query_params

SECTION = "exam-score-entry"
_CTX = "registrar.exam_score_entry"
QUERY = "ese_assessment"


def resolve_assessment(request, *, offering, period, organization, service) -> tuple:
    """``(seçilmiş, defolt, mövcud növlər)`` — yad / mövcud olmayan dəyər defolta düşür."""
    rules = service.exam_score_assessment
    available = rules.available_assessments(offering)
    default = rules.default_assessment(period, organization=organization, midterm_ok=rules.MIDTERM in available)
    requested = (request.GET.get(QUERY) or "").strip()
    selected = requested if requested in available else default
    return selected, default, available


def _option_label(rules, value, cap) -> str:
    if value == rules.MIDTERM:
        return pgettext(_CTX, "MİDTERM (maks %(cap)s)") % {"cap": cap}
    return pgettext(_CTX, "FİNAL (maks %(cap)s)") % {"cap": cap}


def fill_assessment(request, section, *, offering, organization, service, selected, default, available, params):
    """``section``-a növ seçimi, sütun redaktoru və sətir vəziyyətlərini yaz (açılış seçilibsə)."""
    rules = service.exam_score_assessment
    caps = {rules.MIDTERM: rules.midterm_cap(), rules.FINAL: rules.cap_for(offering, rules.FINAL)}
    caps[selected] = int(section["exam_score_max"])
    section["assessment"] = selected
    section["is_midterm"] = selected == rules.MIDTERM
    section["assessment_label"] = _option_label(rules, selected, caps[selected])
    section["assessment_is_default"] = selected == default
    section["assessment_default_label"] = rules.label_for(default)
    section["midterm_unavailable"] = rules.MIDTERM not in available
    section["assessment_options"] = [
        {
            "value": value,
            "label": _option_label(rules, value, caps[value]),
            "cap": caps[value],
            "current": value == selected,
            "is_default": value == default,
            "available": value in available,
            "url": _append_query_params(reverse("accounts:profile"), section=SECTION, **params, **{QUERY: value}),
        }
        for value in (rules.MIDTERM, rules.FINAL)
    ]
    section["edit_window_label"] = rules.edit_window_label()
    section["edit_window_minutes"] = int(rules.edit_window().total_seconds() // 60)
    from core.runtime_settings_exam_scores import release_hours

    section["release_hours"] = release_hours()
    section["draft_url"] = reverse("accounts:exam_score_draft")
    section["today_iso"] = timezone.localdate().isoformat()
    section["today_label"] = timezone.localdate().strftime("%d.%m.%Y")
    section["entered_by_name"] = request.user.get_full_name() or request.user.username
    _fill_row_states(request, section, organization=organization, service=service, assessment=selected)


def _fill_row_states(request, section, *, organization, service, assessment) -> None:
    """Sətir: ``edit_until`` (bu aktorun açıq pəncərəsi, ISO) və ``final_locked`` («Yekun» — dəyişmək üçün rejim)."""
    rules = service.exam_score_assessment.ChangeRules.build(
        user=request.user,
        organization=organization,
        enrollment_ids=[row["enrollment"].pk for row in section.get("rows", [])],
        assessment=assessment,
    )
    section["can_rim_correct"] = rules.can_rim_correct
    correction_mode = bool(section.get("correction_mode"))
    final_count = 0
    for row in section.get("rows", []):
        deadline = rules.deadline(row["enrollment"].pk)
        open_window = deadline is not None and rules.now <= deadline
        row["edit_until"] = deadline.isoformat() if open_window else ""
        row["edit_until_label"] = timezone.localtime(deadline).strftime("%H:%M") if open_window else ""
        confirmed = row["enrollment"].pk in rules.initial
        row["confirmed"] = confirmed
        row["final_locked"] = bool(
            row.get("has_score") and not open_window and not correction_mode and not row.get("teacher_written")
        )
        final_count += 1 if row["final_locked"] else 0
    section["final_count"] = final_count


__all__ = ["QUERY", "fill_assessment", "resolve_assessment"]
