"""«Mühasibatlıq» — ödəniş dərəcələrinin GÖSTƏRİLİŞİ: dərəcə kartı (panel) və müəllimin məbləğ bloku (modal / drill-down).

Hesab qaydası və idarəetmə ``rates.py``-dadır; bu modul yalnız şablon kontekstini qurur (sorğusuz — dərəcə sətirləri
``Resolved.rate_rows``-dadır; yalnız ``can_manage`` aktorun açar əhatəsini oxuyur).
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext

from . import constants as C
from . import rates
from .formatting import fmt_money


def disclaimer() -> str:
    return pgettext(C.CTX, "İlkin hesablama — rəsmi əmək haqqı hesabı deyil.")


def _shape(row, position_labels: dict, kind_labels: dict, reason_labels: dict) -> dict:
    return {
        "id": str(row.pk),
        "position": row.position,
        "activity": row.activity,
        "position_label": position_labels.get(row.position, row.position),
        "kind_label": kind_labels.get(row.activity, row.activity),
        "rate_text": fmt_money(row.hourly_rate),
        "rate": row.hourly_rate,
        "rate_value": f"{row.hourly_rate:.2f}",
        "note": row.note,
        "created_by_name": row.created_by_name,
        "created_at": row.created_at,
        "archived_at": row.archived_at,
        "archived_by_name": row.archived_by_name,
        "reason_label": reason_labels.get(row.archive_reason, ""),
        "archive_url": reverse("accounts:accounting_rate_archive", args=[row.pk]) if row.archived_at is None else "",
    }


def rate_card(resolved, *, with_manage: bool = True) -> dict:
    """Panelin «Dərs saatının ödəniş dərəcələri» kartı — semestrin tədris ili üzrə aktiv sətirlər + tarixçə."""
    from ...models import PayRateArchiveReason

    actor = resolved.actor
    year = resolved.semester.year if resolved.semester else ""
    positions = rates.position_choices()
    kinds = rates.activity_choices()
    position_labels, kind_labels = dict(positions), dict(kinds)
    reason_labels = {key: str(label) for key, label in PayRateArchiveReason.choices}
    rows = resolved.rate_rows or []
    active = [_shape(row, position_labels, kind_labels, reason_labels) for row in rows if row.archived_at is None]
    history = sorted(
        (row for row in rows if row.archived_at is not None), key=lambda row: row.archived_at, reverse=True
    )[: rates.HISTORY_LIMIT]
    covered = {row["position"] for row in active}
    years = []
    for item in resolved.semesters:
        if item.year and item.year not in years:
            years.append(item.year)
    return {
        "year": year,
        "active": active,
        "history": [_shape(row, position_labels, kind_labels, reason_labels) for row in history],
        "can_manage": with_manage and not actor.view_as and rates.can_manage(actor.user, actor.organization),
        "positions": positions,
        "kinds": kinds,
        "years": years,
        "uncovered": [label for key, label in positions if key not in covered],
        "save_url": reverse("accounts:accounting_rate_save"),
        "disclaimer": disclaimer(),
    }


def pay_detail(row: dict) -> dict:
    """Müəllimin dövr məbləği — növlər üzrə dərəcə və məbləğ, cəm, saathesabı etiketi (modal və drill-down)."""
    pay = row["pay"]
    kinds = []
    for key, label in C.KINDS:
        cell = pay["kinds"][key]
        kinds.append(
            {
                "key": key,
                "label": str(label),
                "rate_text": fmt_money(cell["rate"]),
                "amount_text": fmt_money(cell["amount"]),
                "missing": cell["rate"] is None and cell["hours"] > 0,
            }
        )
    return {
        "status": pay["status"],
        "amount_text": fmt_money(pay["amount"]),
        "missing_text": "" if pay["amount"] is not None else rates.missing_text(pay),
        "kinds": kinds,
        "hourly_note": pay["hourly_note"],
        "disclaimer": disclaimer(),
    }


__all__ = ["disclaimer", "pay_detail", "rate_card"]
