"""ExamForm — fənn dəyişikliyi təsdiq bloku üçün şablon məlumatı (sahib 2026-10-25).

Qərarı view verir (``services.exam_subject_change.decide`` — server avtoritetdir); bu mixin yalnız sehrbazın
«Əsaslar» addımında fənn sahəsinin altındakı təsdiq blokunu (``_exam_subject_change_guard.html``) qidalandırır:

* redaktə olunan midtermdə tələbə nəticəsi/cəhdi varsa blok gizli render olunur; fənn dəyişən kimi
  ``subject_select.js`` onu göstərir (köhnə → yeni fənn, tələbə sayı);
* server təsdiq tələb edib (409) — ``subject_change_state`` view tərəfindən doldurulur, blok açıq gəlir.

Orijinal fənn ``__init__``-də götürülür — ``is_valid()`` instansı (``instance.subject``) dəyişdirir.
"""

from __future__ import annotations


class SubjectChangeGuardMixin:
    #: View 409 cavabında doldurur: ``{"required", "error", "reason", "confirm", "students", "new_subject"}``.
    subject_change_state = None

    def _init_subject_change_guard(self):
        instance = getattr(self, "instance", None)
        self._guard_original = None
        if instance is not None and getattr(instance, "pk", None):
            from apps.exams.services import exam_subject_change

            self._guard_original = {
                "subject_id": instance.subject_id,
                "subject_label": exam_subject_change.subject_label(instance.subject if instance.subject_id else None),
                "category": str(instance.exam_type_extended or ""),
            }

    def subject_change_info(self):
        """Şablon üçün blok məlumatı və ya ``None`` (yaratma / nəticəsiz / midterm olmayan imtahan)."""
        cached = getattr(self, "_guard_info_cache", False)
        if cached is not False:
            return cached
        info = None
        original = getattr(self, "_guard_original", None)
        state = self.subject_change_state or {}
        if original is not None and (state.get("required") or original["category"] == "midterm"):
            from apps.exams.services import exam_subject_change

            students = state.get("students") or exam_subject_change.result_students(self.instance)
            if students:
                info = {
                    "students": students,
                    "old_subject_id": original["subject_id"] or "",
                    "old_subject": original["subject_label"],
                    "new_subject": state.get("new_subject") or "",
                    "required": bool(state.get("required")),
                    "error": state.get("error") or "",
                    "reason": state.get("reason") or "",
                    "confirm": bool(state.get("confirm")),
                    "min_length": exam_subject_change.REASON_MIN_LENGTH,
                    "max_length": exam_subject_change.REASON_MAX_LENGTH,
                }
        self._guard_info_cache = info
        return info


__all__ = ["SubjectChangeGuardMixin"]
