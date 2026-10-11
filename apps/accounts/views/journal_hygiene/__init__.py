"""«Jurnal təmizliyi» view paketi (sahib 2026-10-10; RİM rəhbəri / superadmin).

Bölgü ``legacy_review`` paketi ilə eynidir: ``policy`` (aktor qapısı), ``api`` (OXU, GET), ``actions``
(YAZMA, POST), ``panel`` (bölmə çərçivəsi, template tag üçün). Domen məntiqi registrar-dadır
(``journal_hygiene`` aşkarlama, ``journal_hygiene_rows`` təqdimat, ``journal_hygiene_actions`` qərar).
"""

from .actions import journal_hygiene_action
from .api import journal_hygiene_rows
from .panel import build_panel_context
from .policy import resolve_actor

__all__ = ["build_panel_context", "journal_hygiene_action", "journal_hygiene_rows", "resolve_actor"]
