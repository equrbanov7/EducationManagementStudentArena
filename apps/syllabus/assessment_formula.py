"""Qiymətləndirmə strukturu — UNİVERSİTET STANDARTI (sahib qərarı 2026-09-20).

«Balı müəllim tənzimləmir, standartdır»: davamiyyət 10 · kollokvium (aralıq)
20 · sərbəst iş 10 · seminar/laboratoriya ədədi ortası 10 → semestr 50; yekun
imtahan 50; cəmi 100.  Müəllim heç nə seçmir — YALNIZ fəaliyyət növü (seminar,
laboratoriya və ya hər ikisi) tədris yükündən (TAPŞIRIQ sətri) gəlir və
düsturda göstərilir:

* yalnız seminar  → «Seminar (ədədi orta) 10»
* yalnız lab      → «Laboratoriya (ədədi orta) 10»
* hər ikisi       → «Seminar + laboratoriya (birgə ədədi orta — cəm 2n-ə bölünür) 10»

Fəaliyyət növü ``CourseOffering`` üzərindən tapılır: əvvəl dərs yükü sətri
(``workload.TeachingTaskRow``: eyni fənn + dövr + qrup, ``seminar_*``/``lab_*``
saatları), tapılmasa dərs cədvəli slotları (``registrar.ScheduleSlot`` növləri),
o da yoxdursa defolt «seminar».  Modellər ``django.apps.get_model`` ilə həll
olunur — sillabus paketi workload/registrar-ı Python səviyyəsində import ETMİR
(modul sərhədi qapısı).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.utils.translation import pgettext_lazy

from .policy import assessment_weights

_CTX = "syllabus.assessment"

SEMINAR = "seminar"
LAB = "lab"

LABELS = {
    "attendance": pgettext_lazy(_CTX, "Davamiyyət"),
    "midterm": pgettext_lazy(_CTX, "Kollokvium (aralıq qiymətləndirmə)"),
    "selfwork": pgettext_lazy(_CTX, "Sərbəst iş"),
    "final": pgettext_lazy(_CTX, "Yekun imtahan"),
}
ACTIVITY_LABELS = {
    (SEMINAR,): pgettext_lazy(_CTX, "Seminar (ədədi orta)"),
    (LAB,): pgettext_lazy(_CTX, "Laboratoriya (ədədi orta)"),
    (SEMINAR, LAB): pgettext_lazy(_CTX, "Seminar + laboratoriya (birgə ədədi orta — cəm 2n-ə bölünür)"),
}
ACTIVITY_NOTES = {
    (SEMINAR,): pgettext_lazy(
        _CTX, "Seminar balı: semestr ərzindəki bütün seminar qiymətlərinin ədədi ortası (maksimum 10)."
    ),
    (LAB,): pgettext_lazy(
        _CTX, "Laboratoriya balı: semestr ərzindəki bütün laboratoriya qiymətlərinin ədədi ortası (maksimum 10)."
    ),
    (SEMINAR, LAB): pgettext_lazy(
        _CTX,
        "Fənndə həm seminar, həm laboratoriya var: bütün seminar və laboratoriya qiymətləri toplanıb "
        "ümumi sayına (2n) bölünür — birgə ədədi orta, maksimum 10.",
    ),
}
SEMESTER_KEYS = ("attendance", "midterm", "selfwork", "activity")


def normalize_kinds(kinds) -> tuple[str, ...]:
    """Fəaliyyət növləri sabit sıra ilə: ``(seminar,)``, ``(lab,)`` və ya ``(seminar, lab)``.
    Boş/naməlum → ``(seminar,)`` (defolt)."""
    present = {k for k in (kinds or ()) if k in (SEMINAR, LAB)}
    if not present:
        return (SEMINAR,)
    return tuple(k for k in (SEMINAR, LAB) if k in present)


def activity_kinds_for_offering(offering) -> tuple[str, ...]:
    """Açılışın fəaliyyət növləri — dərs yükü sətri → cədvəl slotu → defolt."""
    if offering is None:
        return (SEMINAR,)
    kinds: set[str] = set()
    try:
        TaskRow = django_apps.get_model("workload", "TeachingTaskRow")
        rows = TaskRow.objects.filter(
            organization_id=offering.organization_id,
            subject_id=offering.subject_id,
            period_id=offering.period_id,
        )
        if offering.group_id:
            rows = rows.filter(groups=offering.group_id)
        for row in rows.values("seminar_plan", "seminar_total", "lab_plan", "lab_total"):
            if row["seminar_plan"] or row["seminar_total"]:
                kinds.add(SEMINAR)
            if row["lab_plan"] or row["lab_total"]:
                kinds.add(LAB)
    except LookupError:  # workload tətbiqi yoxdur
        pass
    if not kinds:
        try:
            Slot = django_apps.get_model("registrar", "ScheduleSlot")
            for kind in Slot.objects.filter(offering=offering).values_list("kind", flat=True).distinct():
                if kind in (SEMINAR, LAB):
                    kinds.add(kind)
        except LookupError:
            pass
    return normalize_kinds(kinds)


def activity_kinds_for_syllabus(syllabus) -> tuple[str, ...]:
    return activity_kinds_for_offering(getattr(syllabus, "offering", None))


def activity_label(kinds) -> str:
    return str(ACTIVITY_LABELS[normalize_kinds(kinds)])


def activity_note(kinds) -> str:
    return str(ACTIVITY_NOTES[normalize_kinds(kinds)])


def formula_rows(kinds, organization=None) -> list[dict]:
    """Redaktor/sənəd üçün sətirlər: ``[{key, label, score}]`` — semestr + yekun."""
    weights = assessment_weights(organization)
    rows = []
    for key in SEMESTER_KEYS:
        label = activity_label(kinds) if key == "activity" else str(LABELS[key])
        rows.append({"key": key, "label": label, "score": int(weights.get(key, 0))})
    rows.append({"key": "final", "label": str(LABELS["final"]), "score": int(weights.get("final", 0))})
    return rows


def formula_text(kinds, organization=None) -> str:
    """«Davamiyyət 10 + … + Yekun imtahan 50 = 100 bal» — tək sətir."""
    rows = formula_rows(kinds, organization)
    total = sum(row["score"] for row in rows)
    semester = sum(row["score"] for row in rows if row["key"] != "final")
    parts = " + ".join(f"{row['label']} {row['score']}" for row in rows)
    return f"{parts} = {total} {pgettext_lazy(_CTX, 'bal')} ({pgettext_lazy(_CTX, 'semestr')} {semester} + {pgettext_lazy(_CTX, 'imtahan')} {total - semester})"


__all__ = [
    "LAB",
    "SEMINAR",
    "SEMESTER_KEYS",
    "activity_kinds_for_offering",
    "activity_kinds_for_syllabus",
    "activity_label",
    "activity_note",
    "formula_rows",
    "formula_text",
    "normalize_kinds",
]
