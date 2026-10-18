"""«Mühasibatlıq» kabinet bölməsi (sahib 2026-10-18) — müəllimlərin aylıq keçirilmiş dərs saatı ↔ plan.

Modullar: ``policy`` (aktor qapısı), ``periods`` (semestr təqvimi + planın aylara bölgüsü), ``dataset``
(SQL aqreqatları), ``rows`` (plan ↔ fakt hesabı), ``panel`` / ``detail`` (şablon konteksti), ``export`` (XLSX).
"""

from .constants import PERM_ACCOUNTING_VIEW, SECTION
from .panel import build_panel, resolve
from .policy import AccountingActor, resolve_actor

__all__ = ["AccountingActor", "PERM_ACCOUNTING_VIEW", "SECTION", "build_panel", "resolve", "resolve_actor"]
