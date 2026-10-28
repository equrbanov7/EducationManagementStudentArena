"""«Praktiki məşğələ» bayrağının ilkin planı — köhnə sistemin dərs kodu ``3`` (sahib 2026-10-28).

Köhnə sistemdə xananın ``sem_muh=3`` kodu «praktiki məşğələ» idi; köçürmə onu qəsdən ``seminar`` yazıb
(:mod:`.rehearsal_journal_lesson_kinds`). Hədəfdə bayraq açılışdadır (``CourseOffering.seminar_is_practical``,
YALNIZ görünüş) — bu modul onun ilkin dəyərlərini köhnə sistemdən çıxarır. LOKAL işləyir, heç nə YAZMIR; nəticə
YALNIZ açılış id-ləridir: ``{"format": "practical-offerings/1", "offerings": [uuid, …]}``.

Qayda (jurnal → açılış eşləməsi :class:`.twin_repair_plans.PlanBuilder` ilə EYNİ — delta-nın öz qaydası):

* «praktiki jurnal» — AKTİV, saxta olmayan, tam semestrin jurnalı, ən azı bir xanası ``lab=0, sem_muh=3``;
* onun bütün açılışları (jurnalın qrupları üzrə) plana düşür;
* eyni açılışa «adi seminar jurnalı» da düşürsə (``sem_muh=0`` xanası var, ``3`` yoxdur) — açılış ATLANIR və sayılır:
  orada həqiqi seminar var, etiket onu da «praktiki» edərdi. ``["3"]`` jurnalının özündəki ``0`` xanaları (köhnə
  UI-ın defoltu) praktiki sayılır — 2026/2027 payızında 13 belə jurnal var.
"""

from __future__ import annotations

from collections import defaultdict

from .delta.home_journal import journal_is_active

FORMAT = "practical-offerings/1"
PRACTICAL_CODE = 3
SEMINAR_CODE = 0


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def practical_plan(builder) -> dict:
    """``builder`` — :class:`.twin_repair_plans.PlanBuilder` (jurnal dilimləri + qalib xanalar hazırdır)."""

    counts = builder.counts
    codes: dict = defaultdict(set)
    for row in builder.cells:
        if _int(row.get("lab")) == 0:
            codes[row["journal_uniqid"]].add(_int(row.get("sem_muh")))
    practical, seminar = defaultdict(set), defaultdict(set)
    for uniqid, entry in builder.slices.items():
        found = codes.get(uniqid, set())
        if PRACTICAL_CODE in found:
            if not journal_is_active(entry.journal):
                counts["practical_journals_inactive"] += 1
                continue
            counts["practical_journals"] += 1
            for offering in entry.offerings:
                practical[offering.pk].add(uniqid)
        elif SEMINAR_CODE in found and journal_is_active(entry.journal):
            for offering in entry.offerings:
                seminar[offering.pk].add(uniqid)
    offerings = []
    for offering_id in practical:
        if seminar.get(offering_id):
            counts["offerings_skipped_shared_with_seminar_journal"] += 1
            continue
        offerings.append(str(offering_id))
    counts["practical_offerings"] = len(offerings)
    return {"format": FORMAT, "offerings": sorted(offerings)}


__all__ = ["FORMAT", "practical_plan"]
