"""«Kadr analitikası» paneli — server-render konteksti (filtrlər URL-də, ``hr_*``).

Panel AJAX-safe-dir: avto filtr paneli (``filter_bar.js``), tab və səhifə linkləri bölməni yerində
yenidən yükləyir; hər yükləmə SABİT sayda sorğu edir (``dataset.build_rows``), qalan hər şey
yaddaşda hesablanır. Yalnız aktiv tabın bölgüsü qurulur.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.urls import reverse
from django.utils.translation import pgettext

from . import aggregates as agg
from . import constants as C
from .dataset import build_rows, structure_options, year_options
from .filters import HrFilters, apply_filters, parse_filters
from .policy import resolve_actor


def resolve(request):
    """(aktor, filtrlər, seçimlər, sətirlər) — panel və ixrac EYNİ yoldan keçir (fail-closed)."""
    actor = resolve_actor(request)
    if not actor.has_access:
        return actor, None, None, []
    years, default_year = year_options(actor.organization)
    faculties, chairs = structure_options(actor.organization, actor)
    filters = parse_filters(request.GET, years=years, default_year=default_year, faculties=faculties, chairs=chairs)
    rows = build_rows(actor, filters.year)
    options = {"years": years, "faculties": faculties, "chairs": chairs}
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
    ]


def _people_page(rows, filters: HrFilters, base: str) -> dict:
    labels = agg._labels()
    issue_labels = {key: str(label) for key, label in C.ISSUES}
    paginator = Paginator(sorted(rows, key=lambda row: (row["name"].casefold(), row["id"])), C.PAGE_SIZE)
    page = paginator.get_page(filters.page)
    results = []
    for row in page.object_list:
        results.append(
            {
                **row,
                "title_label": labels["title"].get(row["title"], ""),
                "degree_label": "" if row["degree"] == C.DEGREE_NONE else labels["degree"].get(row["degree"], ""),
                "staff_label": labels["staff"].get(row["staff_type"], ""),
                "status_label": str(C.STATUS_LABELS.get(row["status"], "")),
                "band_label": str(C.LOAD_BAND_LABELS.get(row["load_band"], "")),
                "issue_labels": [issue_labels[key] for key in row["issues"] if key != C.ISSUE_NO_DEGREE],
            }
        )
    return {
        "results": results,
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
        kpis=agg.kpis(rows),
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
        from collections import Counter

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
        panel["workload"] = agg.workload(rows)
    elif filters.tab == C.TAB_ACTIVITY:
        panel["activity"] = agg.tree(rows, agg.activity_metrics)
    elif filters.tab == C.TAB_QUALITY:
        panel["quality"] = [
            {**item, "url": _url(base, filters, tab=C.TAB_PEOPLE, issue=item["key"], page=1)}
            for item in agg.quality(rows)
        ]
    else:
        panel["people"] = _people_page(rows, filters, base)
    return panel


__all__ = ["build_panel", "resolve"]
