"""«Sistem tənzimləmələri» alt səhifələri (sahib 2026-10-21): naviqasiya, ümumi baxış və axtarış indeksi.

Sahib: «hər şey eyni səhifədədir — alt səhifələrini yarat; sidebarda ayrı başlığı olsun və alt hissələri,
bir şeyi axtararkən rahatlıqla tapmaq üçün».

URL SXEMİ (kabinet qabığının içində, AJAX swap və tam GET eynidir)::

    ?section=system-settings                         → «Ümumi baxış» (qrup kartları + axtarış)
    ?section=system-settings&ss_group=<qrup>         → yalnız o qrupun açarları (redaktə forması)
    ?section=system-settings&ss_group=<qrup>&ss_key=<açar>  → həmin açar vurğulanır və görünən sahəyə gəlir

Hər şey ``core.runtime_settings.GROUPS`` / ``SPECS``-dən qurulur — ``runtime_settings_extensions``-a yeni modul
(qrup və ya açar) əlavə olunanda sidebar bəndi, kart və axtarış nəticəsi ÖZÜ yaranır. Bu modul bazaya getmir
(sidebar renderi sorğu büdcəsinə təsir etmir); dəyər/«dəyişdirilib» məlumatı ``runtime_settings_admin.describe()``-dən
gəlir. Saxlama müqaviləsi dəyişmir: forma yalnız açıq qrupun sahələrini göndərir, ``save_values`` göndərilməyən
açarlara toxunmur.
"""

from __future__ import annotations

from collections import Counter

from django.urls import reverse
from django.utils.http import urlencode

from core import runtime_settings as rs
from core.search_text import tolerant_match

SECTION = "system-settings"
GROUP_PARAM = "ss_group"
KEY_PARAM = "ss_key"
#: Sidebar-da «Ümumi baxış» bəndinin və paneldəki ``data-profile-section-sub`` atributunun dəyəri.
OVERVIEW = "overview"

#: Qrup ikonları — YALNIZ ``static/vendor/lucide/ems-nav.svg``-də olan adlar (``test_sidebar_icons.py``).
#: Yeni qrupun ikonu yoxdursa ümumi «sliders-horizontal» işlənir — heç nə sınmır.
GROUP_ICONS = {
    "academic": "graduation-cap",
    "credits": "layers",
    "workload": "clock",
    "login": "key-round",
    "otp": "send",
    "session": "hourglass",
    "journal": "notebook-text",
    "ai": "cpu",
    "exam": "clipboard-check",
    "profile": "user-pen",
    "retake": "rotate-ccw",
    "accounting": "calculator",
    "hr_contracts": "signature",
    "site": "monitor",
    "monitoring": "activity",
    "syllabus": "file-check",
}
DEFAULT_ICON = "sliders-horizontal"
OVERVIEW_ICON = "layout-dashboard"


def _visible_specs():
    return [spec for spec in rs.SPECS.values() if not spec.hidden]


def page_url(group: str = "", key: str = "") -> str:
    """Alt səhifənin kanonik kabinet URL-i (boş ``group`` → ümumi baxış)."""
    params = {"section": SECTION}
    if group:
        params[GROUP_PARAM] = group
        if key:
            params[KEY_PARAM] = key
    return f"{reverse('accounts:profile')}?{urlencode(params)}"


def nav_groups() -> list[dict]:
    """Sidebar / qrup çipləri üçün: GROUPS sırası ilə, yalnız görünən açarı olan qruplar (saf, DB-siz)."""
    counts = Counter(spec.group for spec in _visible_specs())
    return [
        {
            "key": key,
            "label": str(label),
            "icon": GROUP_ICONS.get(key, DEFAULT_ICON),
            "count": counts[key],
            "url": page_url(key),
        }
        for key, label in rs.GROUPS
        if counts.get(key)
    ]


def resolve_group(raw, codes) -> str:
    """``ss_group`` dəyərini yoxlayır: bilinən qrup → kod, əks halda ``""`` (ümumi baxış)."""
    value = str(raw or "").strip()
    return value if value and value in set(codes) else ""


def overview_cards(groups: list) -> list[dict]:
    """``describe()`` nəticəsindən kartlar: açar sayı və dəyişdirilmiş (override) açar sayı."""
    return [
        {
            "key": group["key"],
            "label": group["label"],
            "icon": GROUP_ICONS.get(group["key"], DEFAULT_ICON),
            "count": len(group["fields"]),
            "changed": sum(1 for field in group["fields"] if field.get("overridden")),
            "url": page_url(group["key"]),
        }
        for group in groups
    ]


def search_groups(groups: list) -> list[dict]:
    """Səhifədaxili axtarışın indeksi: qrup → açarlar (ad, izah, açar, keçid). Süzgəc brauzerdədir."""
    return [
        {
            "key": group["key"],
            "label": group["label"],
            "items": [
                {
                    "key": field["key"],
                    "label": field["label"],
                    "help": field["help"],
                    "overridden": bool(field.get("overridden")),
                    "url": page_url(group["key"], field["key"]),
                }
                for field in group["fields"]
            ],
        }
        for group in groups
    ]


def search(query: str, limit: int | None = None) -> list[dict]:
    """Açarlar üzrə az/ing dözümlü, tokenli axtarış (ad + izah + açar + qrup adı) — qlobal axtarış üçün."""
    if not str(query or "").strip():
        return []
    labels = {key: str(label) for key, label in rs.GROUPS}
    order = {key: index for index, (key, _label) in enumerate(rs.GROUPS)}
    hits = []
    for spec in sorted(_visible_specs(), key=lambda item: order.get(item.group, len(order))):
        group_label = labels.get(spec.group)
        if group_label is None:
            continue
        label, help_text = str(spec.label), str(spec.help or "")
        if tolerant_match(query, label, help_text, spec.key, group_label):
            hits.append(
                {
                    "key": spec.key,
                    "label": label,
                    "help": help_text,
                    "group": spec.group,
                    "group_label": group_label,
                    "url": page_url(spec.group, spec.key),
                }
            )
            if limit and len(hits) >= limit:
                break
    return hits


__all__ = [
    "DEFAULT_ICON",
    "GROUP_ICONS",
    "GROUP_PARAM",
    "KEY_PARAM",
    "OVERVIEW",
    "OVERVIEW_ICON",
    "SECTION",
    "nav_groups",
    "overview_cards",
    "page_url",
    "resolve_group",
    "search",
    "search_groups",
]
