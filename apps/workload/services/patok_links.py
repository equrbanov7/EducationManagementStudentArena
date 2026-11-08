"""Patok tərəfdaşı → aparıcı sətir açıq bağının toplu qurulması (sahib 2026-11-08, ``link_patok_leads_20261108``).

* ilin bağsız hər tərəfdaş sətri (``lecture_plan > 0``, ``lecture_total = 0``) üçün eyni tapşırıq + fənn +
  mövsüm/dövr, ``lecture_total > 0`` və özü bağsız aparıcı namizədləri sayılır: TƏK namizəd → bağ yazılır,
  namizəd yoxdur → ``no_lead``, birdən çox → ``ambiguous`` (id-lər hesabatda; ad çap olunmur);
* ``pairs`` — əl ilə ``(tərəfdaş, aparıcı)`` cütləri: :func:`.patok.apply_patok_lead` qaydaları ilə yoxlanılır
  (yanlış cüt bütün işi dayandırır — ``WorkloadDenied``), evristikadan ƏVVƏL tətbiq olunur.

Yalnız ``patok_lead`` sütunu dəyişir: saat, bölgü, jurnal yazısı yoxdur (müəllim yükü eyni qalır).
"""

from __future__ import annotations

from collections import Counter, defaultdict

from core.audit import log_actions
from core.constants import AuditAction

from ..constants import RowKind
from ..models import TeachingTaskRow
from .patok import apply_patok_lead, partner_q
from .scoping import WorkloadDenied


def _key(row) -> tuple:
    return (row.task_id, row.subject_id, row.season, row.period_id)


def _audit(organization, actor, row, old, reason) -> dict:
    return {
        "action": AuditAction.UPDATE,
        "user": actor,
        "organization": organization,
        "obj": row,
        "old_values": {"patok_lead": str(old or "")},
        "new_values": {"patok_lead": str(row.patok_lead_id or "")},
        "reason": reason,
        "resource_type": "workload.TeachingTaskRow",
        "resource_id": str(row.pk),
        "resource_repr": row.subject_label,
    }


def _apply_pairs(organization, actor, pairs, counts, audits) -> set:
    done = set()
    for partner_id, lead_id in pairs:
        row = TeachingTaskRow.objects.select_for_update().filter(organization=organization, pk=partner_id).first()
        if row is None:
            raise WorkloadDenied("workload.patok_partner_not_found", "Tərəfdaş sətir tapılmadı.")
        old = row.patok_lead_id
        apply_patok_lead(row, {"patok_lead_id": str(lead_id)})
        done.add(row.pk)
        if row.patok_lead_id == old:
            counts["pair_unchanged"] += 1
            continue
        row.save(update_fields=["patok_lead", "updated_at"])
        audits.append(_audit(organization, actor, row, old, "workload.patok_lead_pair"))
        counts["pair_linked"] += 1
    return done


def link_patok_leads(*, organization, year: str, actor=None, pairs=()) -> tuple[Counter, list]:
    """``(saylar, [birmənalı olmayan tərəfdaş id-ləri])`` — çağıran tranzaksiyanı idarə edir (dry-run geri)."""
    counts, audits = Counter(), []
    done = _apply_pairs(organization, actor, pairs, counts, audits)
    partners = list(
        TeachingTaskRow.objects.select_for_update(of=("self",))
        .filter(organization=organization, task__academic_year=year, patok_lead__isnull=True)
        .filter(partner_q())
        .exclude(pk__in=done)
        .order_by("task_id", "order", "created_at", "pk")
    )
    counts["partners"] = len(partners)
    keys = {_key(row) for row in partners if row.subject_id}
    candidates = defaultdict(list)
    if keys:
        leads = TeachingTaskRow.objects.filter(
            organization=organization,
            task_id__in={key[0] for key in keys},
            subject_id__in={key[1] for key in keys},
            row_kind=RowKind.TEACHING,
            lecture_total__gt=0,
            patok_lead__isnull=True,
        ).order_by("order", "created_at", "pk")
        for lead in leads:
            if _key(lead) in keys:
                candidates[_key(lead)].append(lead)
    ambiguous = []
    for row in partners:
        found = candidates.get(_key(row), []) if row.subject_id else []
        if not found:
            counts["no_lead"] += 1
            continue
        if len(found) > 1:
            ambiguous.append(str(row.pk))
            continue
        row.patok_lead = found[0]
        row.save(update_fields=["patok_lead", "updated_at"])
        audits.append(_audit(organization, actor, row, None, "workload.patok_lead_single"))
        counts["linked"] += 1
    counts["ambiguous"] = len(ambiguous)
    if audits:
        log_actions(audits)
    return counts, ambiguous


__all__ = ["link_patok_leads"]
