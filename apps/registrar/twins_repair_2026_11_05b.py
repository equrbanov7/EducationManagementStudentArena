"""Əkiz jurnallar 2026-11-05 (ikinci dəst) — sabit id-li düzəlişlər (sahib: «əkiz jurnalları birləşdir»).

``repair_applications_20261105``-dən qalan iki hal (YALNIZ id-lər, şəxsi məlumat yoxdur):

* **A — MR-190 · 235 İ ing** (Aydın Yusifov): köhnə fənn adındakı əkiz W (köhnə sistemin qayıb/seminar xanaları +
  onlayn imtahan 83-ün 18 Midterm balı, imtahan W-yə bağlı) → rəsmi jurnal T (yük, cədvəl, müəllimin yeni dərsləri).
  :class:`.twin_merge_scored.ScoredTwinMerge`: imtahan bağı + Midterm balları T-yə, sonra ``Merger`` (``keep``).
* **B — MR-161 · 234 M rus** (Ədilağa Məlikov): data jurnalı D (QKU-1817) düzgün fənnə QKU-2536 keçməlidir. Bu gün
  boş əkiz E (QKU-2536 — rəsmi baxılmış yük sətrinin jurnalı) D-yə birləşib ləğv olunub; ``fix_offering_subject``
  ``target_offering_exists`` ilə dayanır. Həll: E boş birləşmənin manifesti ilə bərpa olunur
  (:func:`.twin_merge_restore.restore_empty_merge`), data D → E köçür (``keep``), D ləğv olunur. Yük sətri dərs
  yükü tərəfindədir (``workload.services.twin_load_row``) — əmr onu bundan sonra çağırır.

B bütövlükdə bir savepoint-dədir: birləşmə olmasa bərpa da geri qaytarılır (``subject_twin_rolled_back``).
İdempotentdir: ikinci qaçışda A ``already_merged``, B ``restore_already_active`` + ``already_merged``.
"""

from __future__ import annotations

from django.db import transaction

from .twin_merge_restore import restore_empty_merge
from .twin_merge_scored import ScoredTwinMerge

PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"

# A · MR-190 · 235 İ ing — «Zərərverici proqram vasitələrinin təhlili» QKU-2422 → «… (Malware analysis)» QKU-2690.
MR190_SOURCE = "de38874f-45b4-4dbd-be9a-1df00e3e8730"
MR190_TARGET = "6c94d08d-f70f-441f-abad-bfbe8a842c33"

# B · MR-161 · 234 M rus — D «Təsərrüfatların intensiv idarə edilməsi» QKU-1817 → E «İntensiv təsərrüfatların
# yaradılması» QKU-2536 (fənn 44a71458-…); yük sətri 273e0215-… hələ QKU-1817-dədir.
MR161_DATA = "cd5c8ee3-304e-44a9-8d52-dd98c8ac756a"
MR161_TWIN = "47fd2c25-ecf0-4c61-b144-e121ee073e0c"
MR161_SUBJECT = "44a71458-77c8-4f1a-8b85-158848c79aaa"
MR161_ROW = "273e0215-5134-42c9-a83d-6d6222145624"


def run_mr190(*, organization, actor, counts) -> None:
    pair = {"source": MR190_SOURCE, "target": MR190_TARGET, "target_marks": "keep"}
    ScoredTwinMerge(organization=organization, actor=actor, counts=counts).run([pair])


def run_mr161(*, organization, actor, counts) -> bool:
    """``True`` — E aktiv jurnaldır (bu qaçışda və ya əvvəl birləşib), yük sətri addımına keçmək olar."""

    before = dict(counts)
    with transaction.atomic():
        if not restore_empty_merge(
            organization=organization, actor=actor, counts=counts, twin_id=MR161_TWIN, keep_id=MR161_DATA
        ):
            return False
        pair = {"source": MR161_DATA, "target": MR161_TWIN, "target_marks": "keep"}
        ScoredTwinMerge(organization=organization, actor=actor, counts=counts).run([pair])
        done = counts["pairs_merged_scored"] > before.get("pairs_merged_scored", 0) or counts[
            "already_merged"
        ] > before.get("already_merged", 0)
        if not done:
            transaction.set_rollback(True)
            # Bərpa geri qaytarıldı — onun sayları hesabatdan çıxır, birləşmənin dayanma səbəbi qalır.
            delta = {key: value - before.get(key, 0) for key, value in counts.items() if value != before.get(key, 0)}
            counts.clear()
            counts.update(before)
            for key, value in delta.items():
                if not key.startswith("restore_") and key != "offerings_restored":
                    counts[key] += value
            counts["subject_twin_rolled_back"] += 1
            return False
    return True


def run(*, organization, actor, counts) -> bool:
    run_mr190(organization=organization, actor=actor, counts=counts)
    return run_mr161(organization=organization, actor=actor, counts=counts)


__all__ = [
    "MR161_DATA",
    "MR161_ROW",
    "MR161_SUBJECT",
    "MR161_TWIN",
    "MR190_SOURCE",
    "MR190_TARGET",
    "PERIOD",
    "run",
    "run_mr161",
    "run_mr190",
]
