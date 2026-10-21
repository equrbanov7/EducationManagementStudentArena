"""Profil «system-settings» bölməsi — «Sistem tənzimləmələri» (sahib 2026-10-03, yalnız RİM rəhbəri).

2026-10-21 (sahib): bölmə alt səhifələrə bölündü — ``?ss_group=<qrup>`` yalnız o qrupun açarlarını göstərir,
qrupsuz URL «Ümumi baxış»dır (kartlar). URL sxemi: ``apps/accounts/services/system_settings_pages.py``.

CONTEXT MÜQAVİLƏSİ (``system_settings_section``):

    has_access    bool  — RİM rəhbəri / superadmin (view-as yox)
    groups        list  — ``runtime_settings_admin.describe()``: BÜTÜN qruplar → sahələr (cari, defolt, kim/nə vaxt)
    save_url      str   — POST (JSON) — dəyişiklikləri yazır (müqavilə dəyişməyib)
    view          str   — «overview» | «group»
    active_key    str   — açıq qrupun kodu («» — ümumi baxış)
    active_group  dict  — açıq qrup (``groups``-un elementi) və ya None
    focus_key     str   — ``ss_key`` (açıq qrupdadırsa) — vurğulanan açar
    cards         list  — ümumi baxış kartları: açar sayı + dəyişdirilmiş açar sayı
    nav           list  — qrup çipləri (mobil keçid): key, label, url, current
    search_groups list  — səhifədaxili axtarışın indeksi (bütün qruplar)
    source_url    str   — panelin cari URL-i (saxlamadan sonra eyni alt səhifə yenilənir)
    overview_url  str
    crumbs        list  — qrup səhifəsində «Ümumi baxış / <qrup>»
"""

from django.urls import reverse
from django.utils.translation import pgettext

from apps.accounts.services import system_settings_pages as pages

SECTION = pages.SECTION


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
    groups = runtime_settings_admin.describe()
    active_key = pages.resolve_group(request.GET.get(pages.GROUP_PARAM), [group["key"] for group in groups])
    active_group = next((group for group in groups if group["key"] == active_key), None)
    focus_key = str(request.GET.get(pages.KEY_PARAM) or "").strip()
    if not active_group or focus_key not in {field["key"] for field in active_group["fields"]}:
        focus_key = ""
    overview_url = pages.page_url()
    section.update(
        has_access=True,
        groups=groups,
        save_url=reverse("accounts:system_settings_save"),
        view="group" if active_group else "overview",
        active_key=active_key,
        active_group=active_group,
        focus_key=focus_key,
        cards=pages.overview_cards(groups),
        nav=[
            {
                "key": group["key"],
                "label": group["label"],
                "url": pages.page_url(group["key"]),
                "current": group is active_group,
            }
            for group in groups
        ],
        search_groups=pages.search_groups(groups),
        source_url=pages.page_url(active_key),
        overview_url=overview_url,
        crumbs=(
            [
                {"label": pgettext("accounts.runtime_settings", "Ümumi baxış"), "url": overview_url},
                {"label": active_group["label"], "url": ""},
            ]
            if active_group
            else []
        ),
    )


__all__ = ["SECTION", "build_system_settings_section"]
