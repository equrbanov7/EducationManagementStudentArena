"""«Kadr analitikası» paneli — server-render konteksti (filtrlər URL-də, ``hr_*``).

Panel AJAX-safe-dir: avto filtr paneli (``filter_bar.js``), tab və səhifə linkləri bölməni yerində
yenidən yükləyir; hər yükləmə SABİT sayda sorğu edir (``dataset.build_rows``), qalan hər şey
yaddaşda hesablanır. Yalnız aktiv tabın bölgüsü qurulur.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import replace
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.urls import reverse
from django.utils.translation import pgettext

from . import aggregates as agg
from . import constants as C
from .dataset import build_rows, profile_history, structure_options, year_options
from .filters import HrFilters, apply_filters, parse_filters, sort_rows
from .policy import resolve_actor

_ROLE_TOKEN = re.compile(r"^[a-z0-9_]{1,64}$")


def _admin_role_options(rows) -> list[dict]:
    """Datada rast gəlinən inzibati rollar (ad → etiket, say) — filtr seçimləri; kataloq sorğusu YOXDUR."""
    labels, counts = {}, Counter()
    for row in rows:
        for item in row["admin_roles"]:
            labels.setdefault(item["role"], item["label"])
            counts[item["role"]] += 1
    return [
        {"value": role, "label": labels[role], "count": counts[role]}
        for role in sorted(labels, key=lambda name: (-counts[name], labels[name].casefold()))
    ]


def resolve(request):
    """(aktor, filtrlər, seçimlər, sətirlər) — panel və ixrac EYNİ yoldan keçir (fail-closed).

    İnzibati rol filtri datadan asılıdır (yalnız heyətdə olan rollar): əvvəl il seçilib sətirlər qurulur,
    sonra ``hr_admin`` həmin rollara qarşı yoxlanır — tanınmayan dəyər boşalır (500 yox)."""
    actor = resolve_actor(request)
    if not actor.has_access:
        return actor, None, None, []
    years, default_year = year_options(actor.organization)
    faculties, chairs = structure_options(actor.organization, actor)
    raw_admin = (request.GET.get(f"{C.PARAM_PREFIX}admin") or "").strip()
    provisional = (raw_admin,) if _ROLE_TOKEN.match(raw_admin) else ()
    filters = parse_filters(
        request.GET,
        years=years,
        default_year=default_year,
        faculties=faculties,
        chairs=chairs,
        admin_roles=provisional,
    )
    rows = build_rows(actor, filters.year)
    admin_roles = _admin_role_options(rows)
    allowed = {C.ADMIN_ANY, C.ADMIN_NONE, *(item["value"] for item in admin_roles)}
    if filters.admin and filters.admin not in allowed:
        filters = replace(filters, admin="")
    options = {"years": years, "faculties": faculties, "chairs": chairs, "admin_roles": admin_roles}
    return actor, filters, options, rows


def _url(base: str, filters: HrFilters, **overrides) -> str:
    params = {"section": C.SECTION, **filters.as_params(**overrides)}
    return f"{base}?{urlencode(params)}"


def _option(value, label, current) -> dict:
    return {"value": value, "label": str(label), "selected": value == current}


def _filter_fields(filters: HrFilters, options: dict) -> list[dict]:
    titles = agg._labels()["title"]
    chairs = [item for item in options["chairs"] if not filters.faculty or item["faculty_id"] == filters.faculty]
    all_label = pgettext(C.CTX, "Hamısı")
    return [
        {
            "name": "hr_year",
            "label": pgettext(C.CTX, "Tədris ili"),
            "options": [_option(year, year, filters.year) for year in options["years"]],
        },
        {
            "name": "hr_faculty",
            "label": pgettext(C.CTX, "Fakültə"),
            "searchable": True,
            "options": [_option("", all_label, filters.faculty)]
            + [_option(item["value"], item["label"], filters.faculty) for item in options["faculties"]],
        },
        {
            "name": "hr_chair",
            "label": pgettext(C.CTX, "Kafedra"),
            "searchable": True,
            "wide": True,
            "options": [_option("", all_label, filters.chair)]
            + [_option(item["value"], item["label"], filters.chair) for item in chairs],
        },
        {
            "name": "hr_title",
            "label": pgettext(C.CTX, "Elmi ad / vəzifə"),
            "options": [_option("", all_label, filters.title)]
            + [_option(key, titles[key], filters.title) for key in (*C.TITLE_ORDER, C.TITLE_NONE)],
        },
        {
            "name": "hr_staff",
            "label": pgettext(C.CTX, "Ştat növü"),
            "options": [_option("", all_label, filters.staff)]
            + [_option(key, label, filters.staff) for key, label in C.STAFF_TYPES],
        },
        {
            "name": "hr_status",
            "label": pgettext(C.CTX, "Hesab vəziyyəti"),
            "options": [_option("", all_label, filters.status)]
            + [_option(key, label, filters.status) for key, label in C.ACCOUNT_FILTERS],
        },
        {
            "name": "hr_admin",
            "label": pgettext(C.CTX, "İnzibati vəzifə"),
            "searchable": len(options["admin_roles"]) > 8,
            "options": [_option("", all_label, filters.admin)]
            + [_option(key, label, filters.admin) for key, label in C.ADMIN_FIXED]
            + [
                _option(item["value"], f"{item['label']} ({item['count']})", filters.admin)
                for item in options["admin_roles"]
            ],
        },
        {
            "name": "hr_degree",
            "label": pgettext(C.CTX, "Elmi dərəcə"),
            "options": [_option("", all_label, filters.degree)]
            + [_option(key, agg._labels()["degree"][key], filters.degree) for key in (*C.DEGREE_ORDER, C.DEGREE_NONE)],
        },
        {
            "name": "hr_band",
            "label": pgettext(C.CTX, "Yük bandı"),
            "options": [_option("", all_label, filters.band)]
            + [_option(key, label, filters.band) for key, label in C.LOAD_BANDS],
        },
    ]


def _people_columns(filters: HrFilters, base: str) -> list[dict]:
    """Başlıq linkləri: eyni açara ikinci klik istiqaməti çevirir; ``aria-sort`` yalnız aktiv sütunda."""
    labels = (
        (C.SORT_NAME, pgettext(C.CTX, "Müəllim"), False),
        (C.SORT_CHAIR, pgettext(C.CTX, "Fakültə · kafedra"), False),
        (C.SORT_TITLE, pgettext(C.CTX, "Elmi ad · dərəcə"), False),
        (C.SORT_STAFF, pgettext(C.CTX, "Ştat"), True),
        (C.SORT_ADMIN, pgettext(C.CTX, "İnzibati vəzifə"), False),
        (C.SORT_LOAD, pgettext(C.CTX, "Dərs yükü"), False),
        (C.SORT_ACTIVITY, pgettext(C.CTX, "Jurnal / dərs"), True),
        (C.SORT_STATUS, pgettext(C.CTX, "Hesab"), False),
    )
    columns = []
    for key, label, num in labels:
        active = filters.sort_key == key
        next_sort = f"-{key}" if active and not filters.sort_desc else key
        columns.append(
            {
                "key": key,
                "label": label,
                "num": num,
                "url": _url(base, filters, sort=next_sort, page=1),
                "dir": ("descending" if filters.sort_desc else "ascending") if active else "",
            }
        )
    return columns


def _staff_short(staff_type: str, fraction: float) -> str:
    """Ştat sütununun qısa dəyəri: «1», «0,5», «0,75», saathesabı «s/h», profil yoxdursa «—»."""
    if staff_type == C.STAFF_NONE:
        return "—"
    if staff_type == C.STAFF_HOURLY:
        return pgettext(C.CTX, "s/h")
    text = f"{fraction:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _history_rows(timeline, labels, current_year: str) -> list[dict]:
    """Ştat tarixçəsi → ``_timeline.html`` müqaviləsi (who = il, when = ştat, what = vəzifə · norma)."""
    out = []
    for item in timeline:
        short = _staff_short(item["staff_type"], item["staff_fraction"])
        staff = labels["staff"].get(item["staff_type"], "")
        what = labels["position"].get(item["position"], item["position"]) or str(C.UNSET_LABEL)
        if item["norm"]:
            what = pgettext(C.CTX, "%(position)s · norma %(norm)s saat") % {"position": what, "norm": item["norm"]}
        out.append(
            {
                **item,
                "staff_short": short,
                "staff_label": staff,
                "position_label": labels["position"].get(item["position"], item["position"]),
                "who": item["year"],
                "when": f"{short} · {staff}" if staff else short,
                "what": what,
                "reason": pgettext(C.CTX, "Əvvəlki ilə nisbətən dəyişib") if item["changed"] else "",
                "tone": "warning" if item["changed"] else ("primary" if item["year"] == current_year else "neutral"),
                "current": item["year"] == current_year,
            }
        )
    return out


def _people_page(rows, filters: HrFilters, base: str, organization) -> dict:
    labels = agg._labels()
    issue_labels = {key: str(label) for key, label in C.ISSUES}
    paginator = Paginator(sort_rows(rows, filters), C.PAGE_SIZE)
    page = paginator.get_page(filters.page)
    history = profile_history(organization, [row["id"] for row in page.object_list])
    results = []
    for row in page.object_list:
        timeline = _history_rows(history.get(row["id"], []), labels, filters.year)
        results.append(
            {
                **row,
                "staff_short": _staff_short(row["staff_type"], row["staff_fraction"] or 0),
                "title_label": labels["title"].get(row["title"], ""),
                "degree_label": "" if row["degree"] == C.DEGREE_NONE else labels["degree"].get(row["degree"], ""),
                "staff_label": labels["staff"].get(row["staff_type"], ""),
                "position_label": labels["position"].get(row["position"], ""),
                "status_label": str(C.STATUS_LABELS.get(row["status"], "")),
                "band_label": str(C.LOAD_BAND_LABELS.get(row["load_band"], "")),
                "issue_labels": [issue_labels[key] for key in row["issues"] if key != C.ISSUE_NO_DEGREE],
                "history": timeline,
                "history_changes": sum(1 for item in timeline if item["changed"]),
            }
        )
    return {
        "results": results,
        "columns": _people_columns(filters, base),
        "sort": filters.sort,
        "total": paginator.count,
        "page": page.number,
        "num_pages": paginator.num_pages,
        "prev_url": _url(base, filters, page=page.number - 1) if page.has_previous() else "",
        "next_url": _url(base, filters, page=page.number + 1) if page.has_next() else "",
        "issue_options": [_option("", pgettext(C.CTX, "Bütün müəllimlər"), filters.issue)]
        + [_option(key, label, filters.issue) for key, label in C.ISSUES],
    }


def build_panel(request, *, profile_base_url: str = "") -> dict:
    actor, filters, options, all_rows = resolve(request)
    panel = {
        "has_access": actor.has_access,
        "access_denied_message": pgettext(
            C.CTX, "Kadr analitikası İnsan resursları, rektor, RİM rəhbəri və superadmin üçündür."
        ),
    }
    if not actor.has_access:
        return panel
    base = profile_base_url or reverse("accounts:profile")
    rows = apply_filters(all_rows, filters, with_issue=filters.tab == C.TAB_PEOPLE)
    kpis = agg.kpis(rows)
    for tile in kpis:
        # Hesab kartları klik ediləndə ``hr_status`` filtri olur (hr_analytics.js → filter_bar.apply).
        if tile["key"] in C.KPI_TO_ACCOUNT:
            tile["filter"] = tile["key"]
            tile["pressed"] = bool(C.KPI_TO_ACCOUNT[tile["key"]]) and filters.status == C.KPI_TO_ACCOUNT[tile["key"]]
    tabs = [
        {"key": key, "label": str(label), "url": _url(base, filters, tab=key, page=1), "current": key == filters.tab}
        for key, label in C.TABS
    ]
    panel.update(
        filters=filters,
        tab=filters.tab,
        tabs=tabs,
        base_url=base,
        section=C.SECTION,
        filter_fields=_filter_fields(filters, options),
        total_all=len(all_rows),
        total=len(rows),
        kpis=kpis,
        kpi_filter_map=json.dumps(C.KPI_TO_ACCOUNT),
        is_filtered=filters.is_filtered,
        view_as=actor.view_as,
        can_view_demographics=actor.can_view_demographics,
        export_url=(
            reverse("accounts:hr_analytics_export") + "?" + urlencode(filters.as_params(tab=C.TAB_OVERVIEW, page=1))
        ),
        people_url=_url(base, filters, tab=C.TAB_PEOPLE, page=1),
    )
    labels = agg._labels()
    if filters.tab == C.TAB_OVERVIEW:
        total = len(rows)
        panel["overview"] = {
            "staff": agg.distribution(Counter(row["staff_type"] for row in rows), C.STAFF_KEYS, labels["staff"], total),
            "titles": agg.composition(rows, demographics=False)["titles"],
            "bands": agg.distribution(
                Counter(row["load_band"] for row in rows),
                [key for key, _label in C.LOAD_BANDS],
                {key: str(label) for key, label in C.LOAD_BANDS},
                total,
            ),
            "quality": [item for item in agg.quality(rows) if item["count"]][:5],
            "staff_total": agg.staff_metrics(rows),
        }
    elif filters.tab == C.TAB_STAFF:
        panel["staff"] = agg.tree(rows, agg.staff_metrics)
        panel["staff_headers"] = [str(label) for _key, label in C.STAFF_TYPES]
    elif filters.tab == C.TAB_COMPOSITION:
        panel["composition"] = agg.composition(rows, demographics=actor.can_view_demographics)
    elif filters.tab == C.TAB_WORKLOAD:
        from apps.workload.public import norm_rule_note

        panel["workload"] = {**agg.workload(rows), "norm_note": norm_rule_note()}
    elif filters.tab == C.TAB_ACTIVITY:
        panel["activity"] = agg.tree(rows, agg.activity_metrics)
    elif filters.tab == C.TAB_QUALITY:
        panel["quality"] = [
            {**item, "url": _url(base, filters, tab=C.TAB_PEOPLE, issue=item["key"], page=1)}
            for item in agg.quality(rows)
        ]
    else:
        panel["people"] = _people_page(rows, filters, base, actor.organization)
    return panel


__all__ = ["build_panel", "resolve"]
