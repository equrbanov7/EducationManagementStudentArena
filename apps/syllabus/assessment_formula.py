"""Qiymətləndirmə strukturu — UNİVERSİTET STANDARTI (sahib qərarı 2026-09-20).

«Balı müəllim tənzimləmir, standartdır» (sahib 2026-10-10): davamiyyət 10 · midterm (aralıq
imtahan) 30 · seminar/laboratoriya ədədi ortası 10 → semestr 50; yekun imtahan 50; cəmi 100.
Müəllim heç nə seçmir — YALNIZ fəaliyyət növü (seminar, laboratoriya və ya hər ikisi) tədris
yükündən (TAPŞIRIQ sətri) gəlir və düsturda göstərilir:

* yalnız seminar  → «Seminar (ədədi orta) 10»
* yalnız lab      → «Laboratoriya (ədədi orta) 10»
* hər ikisi       → «Seminar + laboratoriya (birgə ədədi orta — cəm 2n-ə bölünür) 10»

Sərbəst iş ləğv olunub — onun 10 balı midterm-ə keçib (20 + 10 = 30). RİM «Sistem tənzimləmələri»
``academic.selfwork_enabled`` açarını yandıranda əvvəlki bölgü (midterm 20 + sərbəst iş 10) geri
qayıdır; ``academic.activity_split`` seminar + laboratoriya olan fəndə fəallığı 5 + 5 edir —
«Seminar ballarının ortası 5 + Laboratoriya ballarının ortası 5». Sahib 2026-10-11: qayda
semestrdən asılı DEYİL — köhnə (2025/2026) semestrin sillabusu da cari düsturu göstərir; çağıran
:mod:`apps.syllabus.rules`-dan aldığı qaydanı ötürür, ötürməsə CARİ qayda işlənir.

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

from core import academic_rules

from .policy import assessment_weights

_CTX = "syllabus.assessment"

SEMINAR = "seminar"
LAB = "lab"

LABELS = {
    "attendance": pgettext_lazy(_CTX, "Davamiyyət"),
    # Sahib 2026-09-25: 3 kollokvium → TƏK midterm (20 bal) — ad hər yerdə «Midterm».
    "midterm": pgettext_lazy(_CTX, "Midterm (aralıq imtahan)"),
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
#: Sahib 2026-10-10 — 5 + 5 qaydası (seminar və laboratoriya AYRICA ortalanır).
SPLIT_LABELS = {
    (SEMINAR,): pgettext_lazy(_CTX, "Seminar ballarının ədədi ortası"),
    (LAB,): pgettext_lazy(_CTX, "Laboratoriya ballarının ədədi ortası"),
    (SEMINAR, LAB): pgettext_lazy(
        _CTX, "Seminar və laboratoriya: seminar ballarının ortası 5 + laboratoriya ballarının ortası 5"
    ),
}
SPLIT_NOTES = {
    (SEMINAR,): pgettext_lazy(
        _CTX, "Seminar ballarının ədədi ortası (10): semestr ərzində yazılmış bütün seminar ballarının ortası."
    ),
    (LAB,): pgettext_lazy(
        _CTX,
        "Laboratoriya ballarının ədədi ortası (10): semestr ərzində yazılmış bütün laboratoriya ballarının ortası.",
    ),
    (SEMINAR, LAB): pgettext_lazy(
        _CTX, "Seminar və laboratoriya: seminar ballarının ortası 5 + laboratoriya ballarının ortası 5 (cəmi 10)."
    ),
}
#: 5 + 5 düsturunun İKİ sətri (seminar + laboratoriya olan fəndə).
SPLIT_PART_LABELS = {
    SEMINAR: pgettext_lazy(_CTX, "Seminar ballarının ortası"),
    LAB: pgettext_lazy(_CTX, "Laboratoriya ballarının ortası"),
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


def _split(split) -> bool:
    return academic_rules.activity_split() if split is None else bool(split)


def activity_label(kinds, *, split=None) -> str:
    """Fəallıq sətrinin adı; ``split`` — 5 + 5 qaydası (``None`` → CARİ RİM tənzimləməsi)."""
    labels = SPLIT_LABELS if _split(split) else ACTIVITY_LABELS
    return str(labels[normalize_kinds(kinds)])


def activity_note(kinds, *, split=None) -> str:
    notes = SPLIT_NOTES if _split(split) else ACTIVITY_NOTES
    return str(notes[normalize_kinds(kinds)])


def _activity_rows(kinds, score: int, split: bool) -> list[dict]:
    kinds = normalize_kinds(kinds)
    if split and kinds == (SEMINAR, LAB):
        half = score // 2
        return [
            {"key": "activity_seminar", "label": str(SPLIT_PART_LABELS[SEMINAR]), "score": half},
            {"key": "activity_lab", "label": str(SPLIT_PART_LABELS[LAB]), "score": score - half},
        ]
    return [{"key": "activity", "label": activity_label(kinds, split=split), "score": score}]


def formula_rows(kinds, organization=None, *, selfwork=None, split=None) -> list[dict]:
    """Redaktor/sənəd üçün sətirlər: ``[{key, label, score}]`` — semestr + yekun.

    ``selfwork`` / ``split`` — tətbiq olunan qayda (``SyllabusRule``); ``None`` → CARİ qayda.
    Standart (sərbəst işsiz) qaydada sərbəst iş sətri yoxdur və midterm 30-dur (cəm yenə 50 + 50)."""
    if selfwork is None:
        selfwork = academic_rules.selfwork_enabled()
    weights = assessment_weights(organization, selfwork=selfwork)
    rows = [
        {"key": key, "label": str(LABELS[key]), "score": int(weights.get(key, 0))} for key in ("attendance", "midterm")
    ]
    if selfwork:
        rows.append({"key": "selfwork", "label": str(LABELS["selfwork"]), "score": int(weights.get("selfwork", 0))})
    rows.extend(_activity_rows(kinds, int(weights.get("activity", 0)), _split(split)))
    rows.append({"key": "final", "label": str(LABELS["final"]), "score": int(weights.get("final", 0))})
    return rows


def formula_text(kinds, organization=None, *, selfwork=None, split=None) -> str:
    """«Davamiyyət 10 + … + Yekun imtahan 50 = 100 bal» — tək sətir."""
    rows = formula_rows(kinds, organization, selfwork=selfwork, split=split)
    total = sum(row["score"] for row in rows)
    semester = sum(row["score"] for row in rows if row["key"] != "final")
    parts = " + ".join(f"{row['label']} {row['score']}" for row in rows)
    return f"{parts} = {total} {pgettext_lazy(_CTX, 'bal')} ({pgettext_lazy(_CTX, 'semestr')} {semester} + {pgettext_lazy(_CTX, 'imtahan')} {total - semester})"


__all__ = [
    "LAB",
    "SEMINAR",
    "SEMESTER_KEYS",
    "SPLIT_LABELS",
    "SPLIT_NOTES",
    "SPLIT_PART_LABELS",
    "activity_kinds_for_offering",
    "activity_kinds_for_syllabus",
    "activity_label",
    "activity_note",
    "formula_rows",
    "formula_text",
    "normalize_kinds",
]
