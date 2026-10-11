"""«Jurnal təmizliyi» panelinin ÇƏRÇİVƏSİ — `{% journal_hygiene_panel %}` template tag-ı bunu çağırır.

Profil context qurucusuna (``context_builder/_stage*``) əlavə olunmur — ``account_password_reset`` naxışı:
panel öz çərçivəsini tag-dan alır, sətirlər JSON-la gəlir. Burada AĞIR SORĞU YOXDUR (yalnız süzgəc
seçimləri: dövrlər, fakültələr, qruplar).
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext

from apps.registrar.public import journal_hygiene as hygiene
from apps.registrar.public import journal_hygiene_actions as hygiene_write
from apps.registrar.public import journal_hygiene_rows as hygiene_rows

from .i18n import panel_strings
from .policy import resolve_actor


def build_panel_context(request) -> dict:
    actor = resolve_actor(request)
    panel = {
        "has_access": actor.has_access,
        "access_denied_message": pgettext(
            "accounts.journal_hygiene", "Jurnal təmizliyi yalnız RİM rəhbəri və superadmin üçündür."
        ),
    }
    if not actor.has_access:
        return panel
    organization = actor.organization
    panel.update(
        can_apply=actor.can_apply,
        view_as=actor.view_as,
        rows_url=reverse("accounts:journal_hygiene_rows"),
        action_url=reverse("accounts:journal_hygiene_action"),
        periods=hygiene_rows.period_options(organization),
        faculties=hygiene_rows.unit_options(organization, "faculty"),
        groups=hygiene_rows.unit_options(organization, "group"),
        left_categories=hygiene.category_options(hygiene.LEFT),
        empty_categories=hygiene.category_options(hygiene.EMPTY),
        not_held_categories=hygiene.category_options(hygiene.NOT_HELD),
        min_reason=hygiene_write.HYGIENE_REASON_MIN_LENGTH,
        max_batch=hygiene_rows.MAX_BATCH,
        page_size=hygiene_rows.PAGE_SIZE,
        i18n=panel_strings(),
    )
    return panel


__all__ = ["build_panel_context"]
