"""«Sorğu nəticələri» — URL parametrləri (``er_*``) ↔ ``ResultFilters`` və dövr seçimi.

Bütün filtrlər query string-dədir (paylaşıla bilən URL) və SERVERDƏ tətbiq olunur.
Ad fəzası ``er_`` — kabinetin başqa parametrləri (``section``, ``q``, ``page``) ilə
toqquşmasın deyə.

* ``er_period`` — boş: son kampaniya; ``all``: bütün kampaniyalar; ``y:<il>``: tədris
  ilinin bütün kampaniyaları; ``<uuid>``: bir kampaniya.
* ``er_faculty`` · ``er_department`` · ``er_teacher`` · ``er_subject`` · ``er_group`` ·
  ``er_program`` · ``er_course_year`` · ``er_question`` · ``er_q`` (şərh mətnində axtarış).
* Vəziyyət (filtr deyil, ``filter_bar.js`` onlara toxunmur): ``er_tab``, ``er_sort``;
  kliyent tərəfli cədvəl vəziyyəti ``er_view`` / ``er_min`` / ``er_tq`` / ``er_page``.

Yanlış dəyər səssizcə atılır (``ResultFilters.from_params`` UUID/tam ədəd yoxlayır).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from urllib.parse import urlencode

from django.utils.translation import pgettext

from .. import public
from ..public import ResultFilters
from .results_labels import DEFAULT_SORT, SORT_KEYS, TAB_OVERVIEW, TABS

CTX = "surveys.results"

PREFIX = "er_"
PERIOD_PARAM = "er_period"
FILTER_PARAMS = ("faculty", "department", "teacher", "subject", "group", "program", "course_year", "question", "q")
STATE_PARAMS = ("tab", "sort", "view", "min", "tq", "page")


@dataclass(frozen=True)
class PeriodChoice:
    mode: str  # latest | all | year | campaign
    value: str  # URL dəyəri («son kampaniya» üçün boş)
    campaign_ids: tuple
    label: str
    is_open: bool = False
    previous_ids: tuple = ()
    previous_label: str = ""


@dataclass(frozen=True)
class ResultsQuery:
    period: PeriodChoice
    filters: ResultFilters
    tab: str = TAB_OVERVIEW
    sort: str = DEFAULT_SORT
    params: dict = field(default_factory=dict)

    @property
    def question(self) -> str:
        return self.filters.question_code


def campaign_label(row) -> str:
    """«2026/2027 · Payız» — dövr adında il artıq varsa təkrarlanmır."""
    name, year = row.get("period_name") or "", row.get("academic_year") or ""
    return name if not year or year in name else f"{year} · {name}"


def period_options(campaigns) -> list:
    """Dövr select-inin seçimləri: son kampaniya, bütün dövrlər, tədris illəri, kampaniyalar."""
    if not campaigns:
        return []
    latest = campaign_label(campaigns[0])
    options = [
        {"value": "", "label": pgettext(CTX, "Son kampaniya — %(label)s") % {"label": latest}},
        {"value": "all", "label": pgettext(CTX, "Bütün dövrlər")},
    ]
    years: dict = {}
    for row in campaigns:
        years.setdefault(row.get("academic_year") or "", []).append(row)
    for year, rows in years.items():
        if year and len(rows) > 1:
            options.append({"value": f"y:{year}", "label": pgettext(CTX, "%(year)s — bütün il") % {"year": year}})
    options.extend({"value": str(row["id"]), "label": campaign_label(row)} for row in campaigns)
    return options


def _is_open(rows) -> bool:
    return any(row.get("effective_status") == "open" for row in rows)


def resolve_period(raw, campaigns) -> PeriodChoice:
    """``er_period`` dəyərini kampaniya dəstinə çevirir (+ müqayisə üçün əvvəlki dəst)."""
    raw = str(raw or "").strip()
    if not campaigns:
        return PeriodChoice(mode="latest", value="", campaign_ids=(), label="")
    if raw == "all":
        return PeriodChoice(
            mode="all",
            value="all",
            campaign_ids=tuple(row["id"] for row in campaigns),
            label=pgettext(CTX, "Bütün dövrlər"),
            is_open=_is_open(campaigns),
        )
    if raw.startswith("y:"):
        year = raw[2:]
        rows = [row for row in campaigns if row.get("academic_year") == year]
        if rows:
            older = [row.get("academic_year") for row in campaigns[campaigns.index(rows[-1]) + 1 :]]
            previous_year = next((value for value in older if value and value != year), None)
            previous = [row for row in campaigns if previous_year and row.get("academic_year") == previous_year]
            return PeriodChoice(
                mode="year",
                value=raw,
                campaign_ids=tuple(row["id"] for row in rows),
                label=pgettext(CTX, "%(year)s — bütün il") % {"year": year},
                is_open=_is_open(rows),
                previous_ids=tuple(row["id"] for row in previous),
                previous_label=previous_year or "",
            )
    index, mode = 0, "latest"
    try:
        wanted = uuid.UUID(raw) if raw and not raw.startswith("y:") else None
    except ValueError:
        wanted = None
    if wanted is not None:
        found = next((position for position, row in enumerate(campaigns) if row["id"] == wanted), None)
        if found is not None:
            index, mode = found, "campaign"
    row = campaigns[index]
    previous = campaigns[index + 1] if index + 1 < len(campaigns) else None
    return PeriodChoice(
        mode=mode,
        value=str(row["id"]) if mode == "campaign" else "",
        campaign_ids=(row["id"],),
        label=campaign_label(row),
        is_open=_is_open([row]),
        previous_ids=(previous["id"],) if previous else (),
        previous_label=campaign_label(previous) if previous else "",
    )


def raw_params(params) -> dict:
    """Request GET-dən yalnız ``er_*`` açarları (boş olmayan, qısaldılmış)."""
    result = {}
    for name in ("period", *FILTER_PARAMS, *STATE_PARAMS):
        value = str(params.get(PREFIX + name) or "").strip()[:120]
        if value:
            result[name] = value
    return result


def parse_query(params, campaigns) -> ResultsQuery:
    raw = raw_params(params)
    period = resolve_period(raw.get("period"), campaigns)
    filters = ResultFilters.from_params({name: raw.get(name, "") for name in FILTER_PARAMS})
    filters = replace(filters, campaign_ids=period.campaign_ids)
    tab = raw.get("tab") if raw.get("tab") in TABS else TAB_OVERVIEW
    sort = raw.get("sort", DEFAULT_SORT)
    if sort.lstrip("-") not in SORT_KEYS:
        sort = DEFAULT_SORT
    return ResultsQuery(period=period, filters=filters, tab=tab, sort=sort, params=raw)


@dataclass(frozen=True)
class Resolved:
    """Bir sorğunun həll olunmuş vəziyyəti: əhatə, kampaniyalar, URL, TƏTBİQ olunan filtrlər."""

    organization: object
    scope: object
    campaigns: list
    query: ResultsQuery
    filters: ResultFilters
    choices: dict | None = None
    teacher_name: str = ""

    @property
    def campaign_ids(self) -> list:
        return list(self.query.period.campaign_ids)


def resolve(request, *, with_choices=False):
    """İcazə (FAIL-CLOSED) + ``er_*`` parametrləri → ``Resolved`` və ya ``None`` (əhatə yoxdur).

    Əhatədə cavabı olmayan müəllim filtri atılır; ``with_choices`` ilə kaskadlı filtr
    seçimləri hesablanır və uyğunsuz seçimlər ``effective`` filtrlərdən çıxarılır.
    """
    organization = getattr(request, "organization", None)
    user = getattr(request, "user", None)
    if organization is None or user is None:
        return None
    scope = public.results_scope(user, organization, request=request)
    if not scope.has_structure_access:
        return None
    campaigns = public.campaign_choices(organization)
    query = parse_query(request.GET, campaigns)
    filters = query.filters
    campaign_ids = list(query.period.campaign_ids)
    teacher_name = ""
    if campaigns and filters.teacher_id is not None:
        teacher_name = public.teacher_label(organization, scope, filters, campaign_ids, filters.teacher_id)
        if not teacher_name:
            filters = replace(filters, teacher_id=None)
    choices = None
    if campaigns and with_choices:
        choices = public.filter_choices(organization, scope, filters, campaign_ids)
        filters = choices["effective"]
    return Resolved(organization, scope, campaigns, query, filters, choices, teacher_name)


def effective_params(query, filters=None) -> dict:
    """Serverin HƏQİQƏTƏN tətbiq etdiyi filtrlər — ``er_*`` açarları ilə (boşlar atılır)."""
    filters = filters or query.filters
    values = {
        "period": query.period.value,
        "faculty": filters.faculty_id,
        "department": filters.department_id,
        "teacher": filters.teacher_id,
        "subject": filters.subject_id,
        "group": filters.group_id,
        "program": filters.program_id,
        "course_year": filters.course_year,
        "question": filters.question_code,
        "q": filters.text_query,
    }
    return {PREFIX + key: str(value) for key, value in values.items() if value not in (None, "")}


def query_string(query, filters=None, *, state=True, **overrides) -> str:
    """Link üçün ``er_*`` query string-i; ``state=False`` — tab/sıralama daxil deyil."""
    params = effective_params(query, filters)
    if state:
        if query.tab != TAB_OVERVIEW:
            params[PREFIX + "tab"] = query.tab
        if query.sort != DEFAULT_SORT:
            params[PREFIX + "sort"] = query.sort
    for key, value in overrides.items():
        name = PREFIX + key
        if value in (None, ""):
            params.pop(name, None)
        else:
            params[name] = str(value)
    return urlencode(params)
