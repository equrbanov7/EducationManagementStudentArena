"""İmtahan redaktəsi — nəticəli midtermin fənn / jurnal dəyişikliyi qapısı (sahib 2026-10-25).

Qayda və audit: ``apps/exams/services/exam_subject_change.py``. Bu modul yalnız view yapışqanıdır: forma
təmizləndikdən SONRA (yeni fənn / müəllim / qruplar məlumdur), saxlamadan ƏVVƏL qərar verir; təsdiq + səbəb
yoxdursa formanı təsdiq bloku açıq halda 409 ilə qaytarmaq üçün ``form.subject_change_state`` doldurur.
"""

from __future__ import annotations

from apps.exams.services import exam_subject_change

from . import unit_assignment as _units

#: Təsdiq tələb olunanda sehrbazın fokuslayacağı addım / sahə («Əsaslar», fənnin altındakı səbəb).
ERROR_STEP = 0
ERROR_FIELD = exam_subject_change.REASON_FIELD


def check(request, organization, snapshot, form, units, *, permission):
    """→ ``(decision | None, reason, blocked)``.

    ``blocked`` — dəyişiklik təsdiq + səbəb tələb edir, amma POST-da yoxdur / yetərsizdir (saxlanmır)."""
    if snapshot is None:
        return None, "", False
    exam = form.instance
    unit_ids = _units.final_unit_ids(request, organization, exam, units, permission=permission)
    decision = exam_subject_change.decide(snapshot, exam, unit_ids=unit_ids)
    if decision is None:
        return None, "", False
    reason, error = exam_subject_change.validate_confirmation(request.POST)
    if reason:
        return decision, reason, False
    form.subject_change_state = {
        "required": True,
        "error": error,
        "reason": str(request.POST.get(exam_subject_change.REASON_FIELD) or "")[
            : exam_subject_change.REASON_MAX_LENGTH
        ],
        "confirm": bool(request.POST.get(exam_subject_change.CONFIRM_FIELD)),
        "students": decision.students,
        "new_subject": decision.new_subject_label,
    }
    return decision, "", True


__all__ = ["ERROR_FIELD", "ERROR_STEP", "check"]
