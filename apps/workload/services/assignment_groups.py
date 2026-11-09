"""``groups_note`` → ``TeacherAssignment.group`` köçürməsi — AYRICA, dry-run-lı servis (sahib 2026-11-09).

Miqrasiya 0011 yalnız sxemadır: heç bir sətir yenidən yazılmır (sahib: «müəllimlərin yüklərini pozmayacaq ki?»).
Bu servis qeydi sətrin qruplarından DÜZ BİRİNƏ parse olunan bölgüyə (``offering_shares._assignment_group`` qaydası:
vergül / nöqtəli vergül / «+» hissələri, hamısı eyni qrup) struktur bağ yazır. Saat, müəllim, fəaliyyət, qeyd
DƏYİŞMİR; jurnal və pay nəticəsi də dəyişmir (parse eyni qrupu verirdi) — yalnız seçici bağı hazır görür.

Defolt dry-run (heç nə yazılmır, saylar qaytarılır); ``apply=True`` yazır. Prod-da prod-data-ops yolu ilə işlədilir.
"""

from __future__ import annotations

import re
from collections import Counter

from django.db import transaction

from ..models import TeacherAssignment, TeachingTaskRow


def _normalize(value) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def backfill_groups(*, organization=None, apply: bool = False) -> Counter:
    """``Counter(candidates, linked, multi_group, unparsed)`` — ``apply=False`` heç nə yazmır."""
    counts: Counter = Counter()
    pending = TeacherAssignment.objects.filter(group__isnull=True).exclude(groups_note="")
    if organization is not None:
        pending = pending.filter(organization=organization)
    pending = list(pending.values("id", "row_id", "groups_note"))
    counts["candidates"] = len(pending)
    if not pending:
        return counts
    groups_by_row: dict = {}
    links = TeachingTaskRow.groups.through.objects.filter(
        teachingtaskrow_id__in={item["row_id"] for item in pending}
    ).select_related("orgunit")
    for link in links:
        groups_by_row.setdefault(link.teachingtaskrow_id, []).append(link.orgunit)
    for item in pending:
        known: dict = {}
        for unit in groups_by_row.get(item["row_id"], ()):
            for label in (unit.name, getattr(unit, "code", "")):
                if label:
                    known.setdefault(_normalize(label), set()).add(unit.pk)
        parts = [_normalize(part) for part in re.split(r"[,;+\n]+", item["groups_note"]) if part.strip()]
        if not parts or any(part not in known or len(known[part]) != 1 for part in parts):
            counts["unparsed"] += 1
            continue
        found = {next(iter(known[part])) for part in parts}
        if len(found) != 1:
            counts["multi_group"] += 1
            continue
        counts["linked"] += 1
        if apply:
            with transaction.atomic():
                TeacherAssignment.objects.filter(pk=item["id"]).update(group_id=found.pop())
    return counts


__all__ = ["backfill_groups"]
