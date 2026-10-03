"""Profil «system-settings» bölməsi — «Sistem tənzimləmələri» (sahib 2026-10-03, yalnız RİM rəhbəri).

CONTEXT MÜQAVİLƏSİ (``system_settings_section``):

    has_access  bool  — RİM rəhbəri / superadmin (view-as yox)
    groups      list  — ``runtime_settings_admin.describe()``: qrup → sahələr (cari, defolt, kim/nə vaxt)
    save_url    str   — POST (JSON) — dəyişiklikləri yazır
"""

from django.urls import reverse
from django.utils.translation import pgettext

SECTION = "system-settings"


def build_system_settings_section(request, section, *, allowed_sections, active_section):
    """``section`` dict-ini YERİNDƏ mutasiya edir."""
    if SECTION not in allowed_sections or active_section != SECTION:
        return
    from apps.accounts.services import runtime_settings_admin

    if not runtime_settings_admin.can_manage(request.user, request):
        section.update(
            has_access=False,
            access_denied_message=pgettext(
                "accounts.runtime_settings", "Sistem tənzimləmələri yalnız RİM rəhbəri üçündür."
            ),
        )
        return
    section.update(
        has_access=True,
        groups=runtime_settings_admin.describe(),
        save_url=reverse("accounts:system_settings_save"),
    )


__all__ = ["SECTION", "build_system_settings_section"]
