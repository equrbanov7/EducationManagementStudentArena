"""«Mühasibatlıq» paneli — server-render konteksti (filtrlər URL-də, ``ac_*``).

Panel AJAX-safe-dir: avto filtr paneli (``filter_bar.js``), sıralama, səhifə və drill-down linkləri bölməni
yerində yeniləyir. Hər yükləmə SABİT sayda sorğu edir (``dataset``), qalan hər şey yaddaşda hesablanır.
Tələbə şəxsi məlumatı YOXDUR: yalnız müəllim, fənn, qrup adı və saatlar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.urls import reverse
from django.utils.translation import pgettext

from core.ui import status_catalog

from ..hr_analytics.constants import STAFF_TYPES
from ..hr_analytics.dataset import _CHAIR_TYPES, _FACULTY_TYPES, _placement, _structure
from . import constants as C
from . import dataset, rates
from .detail import period_bounds, period_label, teacher_detail
from .filters import MONTH_ALL, MONTH_RANGE, AccountingFilters, parse_filters
from .formatting import fmt_hours, fmt_money, kind_cells, staff_short
from .legend import legend_items, range_messages
from .periods import Semester, default_month, default_semester, month_label, months, semesters, teaching_days
from .policy import resolve_actor
from .ranges import range_day_counts
from .rates_view import rate_card
from .rows import apply_filters, build_rows, sort_rows, totals


@dataclass
class Resolved:
    actor: object
    filters: AccountingFilters | None
    semester: Semester | None
    semesters: list
    faculties: list
    chairs: list
    persons: dict
    rows: list
    #: Aralıq rejimi: aralığın fakt matrisi ({müəllim: {ay: {növ: [saat, dərs]}}}) və iş günləri (ay → gün).
    range_held: dict | None = None
    range_counts: dict | None = None
    day_counts: dict | None = None
    #: 2026-10-19: semestrin tədris ilinin ödəniş dərəcələri (aktiv + tarixçə; ``rates.year_rows``) və aktiv xəritə.
    rate_rows: list | None = None
    rate_map: dict | None = None


def _structure_options(units: dict, actor) -> tuple[list[dict], list[dict]]:
    """(fakültələr, kafedralar) — əhatə daxilində, ada görə (struktur sorğusu təkrarlanmır)."""
    faculties, chairs = [], []
    for unit_id, (name, kind, path) in units.items():
        if not actor.unit_visible(unit_id, path):
            continue
        if kind in _FACULTY_TYPES:
            faculties.append({"value": unit_id, "label": name})
        elif kind in _CHAIR_TYPES:
            faculty_id, _faculty, _cid, _chair = _placement(unit_id, path, kind, units)
            chairs.append({"value": unit_id, "label": name, "faculty_id": faculty_id})
    faculties.sort(key=lambda item: item["label"].casefold())
    chairs.sort(key=lambda item: item["label"].casefold())
    return faculties, chairs


def resolve(request) -> Resolved:
    """Panel və ixrac EYNİ yoldan keçir (fail-closed). Sorğu sayı sabitdir."""
    return _resolve(request)


def resolve_teacher(request, teacher_id: int) -> Resolved:
    """Müəllim pəncərəsi üçün: qapı, filtrlər və əhatə ``resolve`` ilə EYNİ, amma fakt / plan / şəxs sorğuları
    YALNIZ həmin müəllim üçündür — ``rows`` ən çox bir sətirdir (əhatədən kənardırsa boşdur)."""
    return _resolve(request, teacher_id=teacher_id)


def _resolve(request, *, teacher_id: int | None = None) -> Resolved:
    actor = resolve_actor(request)
    empty = Resolved(actor, None, None, [], [], [], {}, [])
    if not actor.has_access:
        return empty
    organization = actor.organization
    items = semesters(dataset.period_catalog(organization))
    units = _structure(organization)
    faculties, chairs = _structure_options(units, actor)
    filters = parse_filters(
        request.GET,
        semesters=items,
        default_semester=default_semester(items),
        months_for=months,
        default_month_for=default_month,
        faculties=faculties,
        chairs=chairs,
    )
    semester = next((item for item in items if item.key == filters.semester), None)
    if semester is None:
        return Resolved(actor, filters, None, items, faculties, chairs, {}, [])
    held = dataset.held_matrix(organization, semester, teacher=teacher_id)
    planned = dataset.planned_matrix(organization, semester, teacher=teacher_id)
    persons = dataset.people(actor, set(held) | set(planned), semester.year, units=units)
    day_counts = teaching_days(semester)
    range_held = range_counts = None
    if filters.is_range:
        start, end = filters.range_dates
        range_held = dataset.held_matrix(organization, semester, start=start, end=end, teacher=teacher_id)
        range_counts = range_day_counts(semester, start, end)
    rows = build_rows(
        persons,
        held,
        planned,
        month_keys=months(semester),
        day_counts=day_counts,
        month=filters.month,
        range_held=range_held,
        range_counts=range_counts,
    )
    rate_rows = rates.year_rows(organization, semester.year)
    rate_map = rates.active_map(rate_rows)
    rates.attach(rows, rate_map)
    return Resolved(
        actor,
        filters,
        semester,
        items,
        faculties,
        chairs,
        persons,
        rows,
        range_held,
        range_counts,
        day_counts,
        rate_rows,
        rate_map,
    )


def _url(base: str, filters: AccountingFilters, **overrides) -> str:
    return f"{base}?{urlencode({'section': C.SECTION, **filters.as_params(**overrides)})}"


def _option(value, label, current) -> dict:
    return {"value": value, "label": str(label), "selected": value == current}


def _filter_fields(resolved: Resolved) -> list[dict]:
    filters = resolved.filters
    all_label = pgettext(C.CTX, "Hamısı")
    month_keys = months(resolved.semester) if resolved.semester else []
    chairs = [item for item in resolved.chairs if not filters.faculty or item["faculty_id"] == filters.faculty]
    return [
        {
            "name": "ac_semester",
            "label": pgettext(C.CTX, "Semestr"),
            "options": [_option(item.key, item.label, filters.semester) for item in resolved.semesters],
        },
        {
            "name": "ac_month",
            "label": pgettext(C.CTX, "Ay"),
            "options": [_option(key, month_label(key), filters.month) for key in month_keys]
            + [
                _option(MONTH_ALL, pgettext(C.CTX, "Bütün semestr"), filters.month),
                _option(MONTH_RANGE, pgettext(C.CTX, "Tarix aralığı…"), filters.month),
            ],
        },
        {
            "name": "ac_faculty",
            "label": pgettext(C.CTX, "Fakültə"),
            "searchable": True,
            "options": [_option("", all_label, filters.faculty)]
            + [_option(item["value"], item["label"], filters.faculty) for item in resolved.faculties],
        },
        {
            "name": "ac_chair",
            "label": pgettext(C.CTX, "Kafedra"),
            "searchable": True,
            "wide": True,
            "options": [_option("", all_label, filters.chair)]
            + [_option(item["value"], item["label"], filters.chair) for item in chairs],
        },
        {
            "name": "ac_deviation",
            "label": pgettext(C.CTX, "Kənarlaşma"),
            "options": [
                _option("", pgettext(C.CTX, "Bütün müəllimlər"), filters.deviation),
                _option("1", pgettext(C.CTX, "Yalnız plandan kənarlaşanlar"), filters.deviation),
            ],
        },
    ]


def _status(key: str):
    return status_catalog.get(C.STATUS_FAMILY, key)


def _amount_kpi(pay: dict) -> dict:
    """«Hesablanmış məbləğ» — dərəcəsi olan müəllimlərin cəmi; dərəcəsizlər sayılmır və qeyddə göstərilir."""
    note = pgettext(C.CTX, "{n} müəllim · ilkin hesablama").format(n=pay["priced"])
    if pay["missing"]:
        note = pgettext(C.CTX, "{n} müəllim · dərəcəsi olmayan: {m}").format(n=pay["priced"], m=pay["missing"])
    return {
        "label": pgettext(C.CTX, "Hesablanmış məbləğ"),
        "value": fmt_money(pay["amount"]) if pay["priced"] else "—",
        "unit": "AZN" if pay["priced"] else "",
        "tone": "accent-primary",
        "note": note,
    }


def _kpis(summary: dict, period: str) -> list[dict]:
    """KPI kartları — hər kartın alt qeydi rəqəmin NƏ olduğunu bir cümlə ilə deyir (sahib: «daha aydın»)."""
    kinds = summary["kinds"]
    held_note = " · ".join(f"{label} {fmt_hours(kinds[key])}" for key, label in C.KINDS)
    pct = summary["pct"]
    band = C.deviation_percent()
    hours = pgettext(C.CTX, "saat")
    return [
        {
            "label": pgettext(C.CTX, "Keçirilmiş saat"),
            "value": fmt_hours(summary["held"]),
            "unit": hours,
            "note": held_note,
        },
        {
            "label": pgettext(C.CTX, "Plan"),
            "value": fmt_hours(summary["planned"]),
            "unit": hours,
            "note": pgettext(C.CTX, "{period} üçün paylanmış yükün payı").format(period=period),
        },
        {
            "label": pgettext(C.CTX, "İcra"),
            "value": "—" if pct is None else pct,
            "unit": "" if pct is None else "%",
            "note": pgettext(C.CTX, "fakt ÷ plan · fərq {diff} saat").format(
                diff=fmt_hours(summary["diff"], signed=True)
            ),
        },
        {
            "label": pgettext(C.CTX, "Plandan çox"),
            "value": summary["over"],
            "tone": "accent-warning",
            "note": pgettext(C.CTX, "müəllim · fakt > plan + {band}").format(band=f"{band}%"),
        },
        {
            "label": pgettext(C.CTX, "Plandan az"),
            "value": summary["under"],
            "tone": "accent-danger",
            "note": pgettext(C.CTX, "müəllim · fakt < plan − {band}").format(band=f"{band}%"),
        },
        _amount_kpi(summary["pay"]),
    ]


def _columns(filters: AccountingFilters, base: str) -> list[dict]:
    spec = (
        ("name", pgettext(C.CTX, "Müəllim"), False),
        ("planned", pgettext(C.CTX, "Plan"), True),
        ("held", pgettext(C.CTX, "Fakt"), True),
        ("diff", pgettext(C.CTX, "Fərq"), True),
        ("pct", pgettext(C.CTX, "İcra"), True),
    )
    current, desc = filters.sort.lstrip("-"), filters.sort.startswith("-")
    out = {}
    for key, label, num in spec:
        is_current = key == current
        target = f"-{key}" if is_current and not desc else key
        direction = ("descending" if desc else "ascending") if is_current else ""
        out[key] = {"label": label, "num": num, "url": _url(base, filters, sort=target, page=1), "dir": direction}
    return out


def detail_query(filters: AccountingFilters, **overrides) -> str:
    """Müəllim pəncərəsinin (modal) və ixracın query-si — panelin cari dövrü/filtrləri, səhifəsiz."""
    return urlencode(filters.as_params(**{"page": 1, "lpage": 1, "teacher": "", **overrides}))


def _table(rows, filters: AccountingFilters, base: str) -> dict:
    paginator = Paginator(rows, C.PAGE_SIZE)
    page = paginator.get_page(filters.page)
    query = detail_query(filters)
    results = []
    for row in page.object_list:
        status = _status(row["status"])
        results.append(
            {
                **row,
                "staff_short": staff_short(row),
                "staff_label": str(dict(STAFF_TYPES).get(row["staff_type"], "")),
                "planned_text": fmt_hours(row["planned"]),
                "held_text": fmt_hours(row["held"]),
                "diff_text": fmt_hours(row["diff"], signed=True),
                "kind_cells": kind_cells(row["kinds"]),
                "planned_sem_text": fmt_hours(row["planned_sem"]),
                "held_sem_text": fmt_hours(row["held_sem"]),
                "status_obj": status,
                "pay_text": fmt_money(row["pay"]["amount"]),
                "pay_missing": "" if row["pay"]["amount"] is not None else rates.missing_text(row["pay"]),
                "url": _url(base, filters, teacher=str(row["id"]), lpage=1),
                "detail_url": reverse("accounts:accounting_teacher_detail", args=[row["id"]]) + "?" + query,
            }
        )
    return {
        "results": results,
        "columns": _columns(filters, base),
        "total": paginator.count,
        "page": page.number,
        "num_pages": paginator.num_pages,
        "prev_url": _url(base, filters, page=page.number - 1) if page.has_previous() else "",
        "next_url": _url(base, filters, page=page.number + 1) if page.has_next() else "",
    }


def _range_context(resolved: Resolved) -> dict:
    filters, semester = resolved.filters, resolved.semester
    return {
        "is_range": filters.is_range,
        "range_from": filters.date_from,
        "range_to": filters.date_to,
        "range_min": semester.start.isoformat(),
        "range_max": semester.end.isoformat(),
        "range_messages": range_messages(filters.range_notes, semester),
    }


def build_panel(request, *, profile_base_url: str = "") -> dict:
    resolved = resolve(request)
    actor, filters = resolved.actor, resolved.filters
    panel = {
        "has_access": actor.has_access,
        "access_denied_message": pgettext(
            C.CTX, "Mühasibatlıq bölməsi mühasib, rektor, Qəyyumlar Şurası və RİM rəhbəri üçündür."
        ),
    }
    if not actor.has_access:
        return panel
    base = profile_base_url or reverse("accounts:profile")
    panel.update(
        section=C.SECTION,
        base_url=base,
        filters=filters,
        view_as=actor.view_as,
        has_semester=resolved.semester is not None,
        filter_fields=_filter_fields(resolved),
        kind_labels=[str(label) for _key, label in C.KINDS],
        deviation_percent=C.deviation_percent(),
    )
    if resolved.semester is None:
        return panel
    period = period_label(filters, resolved.semester)
    rows = sort_rows(apply_filters(resolved.rows, filters), filters)
    # Drill-down açıqdırsa KPI-lar həmin müəllimindir (siyahının cəmi yox).
    focus = [row for row in resolved.rows if str(row["id"]) == filters.teacher] if filters.teacher else rows
    summary = {**totals(focus), "pay": rates.totals(focus)}
    panel.update(
        semester_label=resolved.semester.label,
        period_label=period,
        is_whole_semester=filters.month == MONTH_ALL,
        month_in_progress=_in_progress(filters),
        total_all=len(resolved.rows),
        total=len(rows),
        is_filtered=filters.is_filtered,
        kpis=_kpis(summary, period),
        legend=legend_items(),
        summary={
            **summary,
            "planned_text": fmt_hours(summary["planned"]),
            "held_text": fmt_hours(summary["held"]),
            "diff_text": fmt_hours(summary["diff"], signed=True),
            "kind_cells": kind_cells(summary["kinds"]),
            "pay_text": fmt_money(summary["pay"]["amount"]) if summary["pay"]["priced"] else "",
        },
        rates=rate_card(resolved),
        export_url=reverse("accounts:accounting_export") + "?" + urlencode(filters.as_params(page=1, lpage=1)),
        list_url=_url(base, filters, teacher="", lpage=1),
        reset_url=_url(base, filters, faculty="", chair="", q="", deviation="", page=1, teacher="", lpage=1),
        **_range_context(resolved),
    )
    if filters.teacher:
        panel["detail"] = teacher_detail(resolved, base=base, url=_url)
    else:
        panel["table"] = _table(rows, filters, base)
    return panel


def _in_progress(filters: AccountingFilters) -> bool:
    """Seçilmiş dövr bu günü əhatə edir (ay və ya aralıq) — fakt hələ artacaq."""
    if not filters.month or filters.month == MONTH_ALL:
        return False
    first, last = period_bounds(filters)
    return first <= date.today() <= last


__all__ = ["Resolved", "build_panel", "detail_query", "resolve", "resolve_teacher"]
