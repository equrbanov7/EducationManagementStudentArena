"""«Yük bölgüsü» cavabında jurnalın taleyi (sahib 2026-11-11: «ekran köçürüldü deyir, jurnal köçmür»)."""

from __future__ import annotations

from django.utils.translation import pgettext


def journal_outcome(sync: dict) -> dict:
    """Sahib 2026-11-11: «ekran köçürüldü deyir, jurnal köçmür» — jurnalın taleyi cavabda AÇIQ deyilir."""
    if sync.get("transfer_blocked") or sync.get("instructor_blocked"):
        return {
            "warning": pgettext(
                "workload",
                "Bölgü saxlanıldı, amma jurnal yeni müəllimə köçmədi (bal yazma səlahiyyəti yoxdur və ya jurnal "
                "dəyişib). «Fənn təhvili» bölməsindən yoxlayın.",
            )
        }
    if sync.get("journal_transferred") or sync.get("instructor_replaced") or sync.get("instructor_set"):
        return {"message": pgettext("workload", "Bölgü saxlanıldı — jurnal bütün balları ilə yeni müəllimə keçdi.")}
    if sync.get("kind_transferred"):
        return {
            "message": pgettext(
                "workload", "Bölgü saxlanıldı — bu dərs növünün jurnal payı yeni müəllimə keçdi (bal itmir)."
            )
        }
    return {}


__all__ = ["journal_outcome"]
