"""«Təşkilat rolları» — rol KATALOQUNUN `ems_ui` görünüş modeli.

Niyə yenidən quruldu (sahib, 2026-09-09: «qaydasına sal yenidən»)
------------------------------------------------------------------
Əvvəlki ekran rolları kart torunda göstərirdi və hər kartın içinə XAM icazə
açarlarını (`journal.correct`, `unit.assign_head` …) çip kimi tökürdü. Nəticədə:

* rolun NƏ ETDİYİ oxunmurdu — açar adları texniki idi, kateqoriya yox idi;
* rolun KİMDƏ olduğu heç görünmürdü (üzv sayı yox idi);
* axtarış/süzgəc yox idi — 21+ rolda lazımlı rolu tapmaq gözlə skan idi;
* «icazəsi olmayan» və ya «heç kimə verilməyən» rol gözə dəymirdi.

İndi ekran REYESTRDİR: KPI → süzgəc → cədvəl → çekmecə. Rol sətri rolun
səviyyəsini, əhatəsini, neçə nəfərdə olduğunu və icazələrin KATEQORİYA
paylanmasını göstərir; çekmecə isə icazələri kateqoriya-kateqoriya insan
dilində açır.

⚠️ Bu modul YALNIZ `organizations` modellərinə baxır (`Role`, `Membership`) —
`apps.accounts`-a idxal YOXDUR, çünki modul-sərhəd qapısı (`scripts/module_deps.py`)
organizations → accounts istiqamətini qadağan edir.

Səviyyə haqqında: burada göstərilən rəqəm rol KATALOQUNUN öz `Role.level`-idir.
Bu, konkret üzvün RBAC səviyyəsi ilə eyni olmaya bilər (bax
`apps/accounts/services/role_catalog.py::effective_level`) — ona görə sütun
«Kataloq səviyyəsi» adlanır və çekmecədə bu fərq açıq yazılır.
"""

from __future__ import annotations

from django.db.models import Count
from django.utils.translation import pgettext

from ...models import Membership
from ...permissions import (
    PERMISSION_CATEGORIES,
    PERMISSION_CATEGORY_LABELS,
    get_permission_label,
)

CTX = "organizations.roles_registry"

#: Süzgəc parametrlərinin ad fəzası (`?orl_q=…`). Digər bölmələrlə toqquşmasın.
PREFIX = "orl_"

SCOPE_LABELS = {
    "organization": "Bütün təşkilat",
    "unit": "Struktur bölməsi",
    "course": "Dərs",
}


def _t(text: str) -> str:
    return pgettext(CTX, text)


def _scope_label(scope_type: str) -> str:
    return _t(SCOPE_LABELS.get(scope_type, scope_type or "—"))


def _category_of(permission: str) -> str:
    """İcazə açarının kateqoriyası; kataloqda yoxdursa boş sətir."""
    for category, keys in PERMISSION_CATEGORIES.items():
        if permission in keys:
            return category
    return ""


def _category_label(category: str) -> str:
    return _t(PERMISSION_CATEGORY_LABELS.get(category, category))


def _permission_groups(permissions):
    """İcazələri kateqoriyalara böl və insan-oxunaqlı etiket ver.

    Kataloqda olmayan açar itmir — «Digər» qrupunda xam adı ilə qalır ki, yeni
    açar əlavə edən adam onu ekranda dərhal görsün.
    """
    buckets: dict[str, list[dict]] = {}
    wildcard = False
    for key in permissions or []:
        if key == "*":
            wildcard = True
            continue
        category = _category_of(key)
        bucket = buckets.setdefault(category or "other", [])
        bucket.append({"key": key, "label": get_permission_label(key) or key})
    groups = []
    for category in list(PERMISSION_CATEGORIES) + ["other"]:
        items = buckets.get(category)
        if not items:
            continue
        groups.append(
            {
                "key": category,
                "label": _category_label(category) if category != "other" else _t("Digər"),
                "items": sorted(items, key=lambda item: item["label"]),
                "count": len(items),
            }
        )
    return groups, wildcard


def _member_counts(organization):
    """Rol → aktiv üzvlük sayı (bir sorğu)."""
    rows = (
        Membership.objects.filter(organization=organization, is_active=True)
        .values("role_id")
        .annotate(total=Count("id"))
    )
    return {row["role_id"]: row["total"] for row in rows}


def _matches(role, entry, query, scope, kind, category):
    if scope and role.scope_type != scope:
        return False
    if kind == "system" and not role.is_system:
        return False
    if kind == "custom" and role.is_system:
        return False
    if kind == "unassigned" and entry["members"]:
        return False
    if kind == "empty" and entry["permission_count"]:
        return False
    if category and category not in {group["key"] for group in entry["groups"]}:
        return False
    if query:
        haystack = " ".join(
            [role.display_name or "", role.name or "", role.description or ""]
            + [item["label"] for group in entry["groups"] for item in group["items"]]
            + list(role.permissions or [])
        ).casefold()
        if query.casefold() not in haystack:
            return False
    return True


def _sorted(entries, sort):
    if sort == "level_asc":
        return sorted(entries, key=lambda e: (e["level"], e["label"]))
    if sort == "name":
        return sorted(entries, key=lambda e: e["label"].casefold())
    if sort == "members_desc":
        return sorted(entries, key=lambda e: (-e["members"], -e["level"]))
    return sorted(entries, key=lambda e: (-e["level"], e["label"].casefold()))


def _entry(role, members):
    groups, wildcard = _permission_groups(role.permissions)
    permission_count = sum(group["count"] for group in groups)
    return {
        "id": str(role.id),
        "label": role.display_name or role.name,
        "name": role.name,
        "description": role.description or "",
        "level": role.level,
        "scope": role.scope_type,
        "scope_label": _scope_label(role.scope_type),
        "is_system": role.is_system,
        "is_active": role.is_active,
        "members": members,
        "groups": groups,
        "wildcard": wildcard,
        "permission_count": permission_count,
    }


def _filter_fields(query, scope, kind, category, sort):
    return [
        {
            "name": "q",
            "label": _t("Axtarış"),
            "kind": "search",
            "value": query,
            "wide": True,
            "placeholder": _t("Rol adı, izah və ya icazə"),
        },
        {
            "name": "scope",
            "label": _t("Əhatə"),
            "kind": "select",
            "value": scope,
            "options": [{"value": "", "label": _t("Bütün əhatələr")}]
            + [{"value": key, "label": _t(label)} for key, label in SCOPE_LABELS.items()],
        },
        {
            "name": "kind",
            "label": _t("Vəziyyət"),
            "kind": "select",
            "value": kind,
            "options": [
                {"value": "", "label": _t("Hamısı")},
                {"value": "system", "label": _t("Sistem rolu")},
                {"value": "custom", "label": _t("Təşkilatın öz rolu")},
                {"value": "unassigned", "label": _t("Heç kimə verilməyib")},
                {"value": "empty", "label": _t("İcazəsi yoxdur")},
            ],
        },
        {
            "name": "category",
            "label": _t("İcazə kateqoriyası"),
            "kind": "select",
            "searchable": True,
            "value": category,
            "options": [{"value": "", "label": _t("Bütün kateqoriyalar")}]
            + [{"value": key, "label": _category_label(key)} for key in PERMISSION_CATEGORIES],
        },
        {
            "name": "sort",
            "label": _t("Sıralama"),
            "kind": "select",
            "value": sort,
            "options": [
                {"value": "level_desc", "label": _t("Səviyyə (yuxarıdan)")},
                {"value": "level_asc", "label": _t("Səviyyə (aşağıdan)")},
                {"value": "name", "label": _t("Ad (A→Z)")},
                {"value": "members_desc", "label": _t("Üzv sayı")},
            ],
        },
    ]


def _kpi_tiles(entries):
    total = len(entries)
    system = sum(1 for e in entries if e["is_system"])
    assigned = sum(e["members"] for e in entries)
    unassigned = sum(1 for e in entries if not e["members"])
    empty = sum(1 for e in entries if not e["permission_count"] and not e["wildcard"])
    return [
        {
            "label": _t("Rol"),
            "value": total,
            "note": _t("kataloqda, süzgəcdən asılı deyil"),
            "tone": "accent-primary",
        },
        {"label": _t("Sistem rolu"), "value": system, "note": _t("miqrasiya ilə gəlir, silinmir")},
        {"label": _t("Təyinat"), "value": assigned, "note": _t("aktiv üzvlük (bir nəfər bir neçə dəfə sayıla bilər)")},
        {
            "label": _t("Verilməyib"),
            "value": unassigned,
            "note": _t("heç bir üzvdə yoxdur"),
            "tone": "accent-warning" if unassigned else None,
        },
        {
            "label": _t("İcazəsiz"),
            "value": empty,
            "note": _t("rol var, açar yoxdur"),
            "tone": "accent-danger" if empty else None,
        },
    ]


def _columns():
    return [
        {"key": "role", "label": _t("Rol")},
        {"key": "level", "label": _t("Kataloq səviyyəsi"), "align": "num"},
        {"key": "scope", "label": _t("Əhatə")},
        {"key": "members", "label": _t("Üzv"), "align": "num"},
        {"key": "perms", "label": _t("İcazələr")},
        {"key": "actions", "label": _t("Əməl"), "align": "end"},
    ]


def _row(entry):
    return {
        "entry": entry,
        "head_include": "organizations/partials/roles/_cell_role.html",
        "cells": [
            {"text": str(entry["level"]), "num": True, "mono": True},
            {"text": entry["scope_label"], "muted": True},
            {"text": str(entry["members"]), "num": True},
            {"include": "organizations/partials/roles/_cell_perms.html"},
        ],
        "actions_include": "organizations/partials/roles/_row_actions.html",
    }


def build_roles_ui(request, organization, roles) -> dict:
    """Rol kataloqunun görünüş modeli (süzgəc SERVERDƏ tətbiq olunur)."""
    params = request.GET if request is not None else {}
    query = (params.get(PREFIX + "q") or "").strip()
    scope = (params.get(PREFIX + "scope") or "").strip()
    kind = (params.get(PREFIX + "kind") or "").strip()
    category = (params.get(PREFIX + "category") or "").strip()
    sort = (params.get(PREFIX + "sort") or "level_desc").strip()

    members = _member_counts(organization)
    entries = [_entry(role, members.get(role.id, 0)) for role in roles]
    shown = _sorted(
        [e for role, e in zip(roles, entries) if _matches(role, e, query, scope, kind, category)],
        sort,
    )

    has_filters = any([query, scope, kind, category])
    return {
        "prefix": PREFIX,
        "header_subtitle": _t(
            "Təşkilatın rol kataloqu: hər rolun səviyyəsi, əhatəsi, neçə nəfərdə "
            "olduğu və hansı icazələri daşıdığı. Rola klik edib icazələri "
            "kateqoriya üzrə açın."
        ),
        "kpi_tiles": _kpi_tiles(entries),
        "filter_fields": _filter_fields(query, scope, kind, category, sort),
        "filter_count_label": _t("Nəticə: %(n)s rol") % {"n": len(shown)},
        "columns": _columns(),
        "table_rows": [_row(entry) for entry in shown],
        "table_state": "ready" if shown else "empty",
        "state_title": _t("Uyğun rol tapılmadı") if has_filters else _t("Kataloqda hələ rol yoxdur"),
        "state_body": (
            _t("Süzgəcləri sıfırlayıb yenidən yoxlayın.")
            if has_filters
            else _t("Rollar universitet şablonundan miqrasiya ilə gəlir.")
        ),
        "drawer_title": _t("Rol haqqında"),
        "drawer_subtitle": _t("İcazələr kateqoriya üzrə qruplaşdırılıb."),
        "entries": shown,
    }
