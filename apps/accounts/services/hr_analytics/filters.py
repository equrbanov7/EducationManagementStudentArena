"""«Kadr analitikası» filtrləri — GET normallaşdırma (``hr_*``) + yaddaşda tətbiq.

Xam GET heç vaxt aşağı qata düşmür: hər dəyər allowlist-ə (il siyahısı, struktur id-ləri, sabit
açarlar) qarşı yoxlanılır, tanınmayan dəyər səssizcə boşalır (500 yox, «filtrsiz» görünüş).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from core.search_text import tolerant_match

from . import constants as C


@dataclass(frozen=True)
class HrFilters:
    year: str = ""
    faculty: str = ""
    chair: str = ""
    title: str = ""
    staff: str = ""
    q: str = ""
    issue: str = ""
    #: Hesab vəziyyəti (``ACCOUNT_KEYS``) — KPI kartları ilə eyni dəstlər.
    status: str = ""
    #: İnzibati vəzifə: ``any`` / ``none`` / konkret rol adı (yalnız datada olan rollar).
    admin: str = ""
    #: Elmi dərəcə: ``phd`` / ``dsc`` / ``none``.
    degree: str = ""
    #: Dərs yükü bandı (``LOAD_BANDS`` açarı).
    band: str = ""
    #: Sıralama açarı, «-» prefiksi azalan (``SORT_KEYS``); yalnız «Müəllimlər» tabına təsir edir.
    sort: str = C.SORT_DEFAULT
    tab: str = C.TAB_OVERVIEW
    page: int = 1

    def as_params(self, **overrides) -> dict:
        """URL parametrləri (``hr_`` prefiksli, boşlar atılır) — tab/səhifə linkləri üçün."""
        values = {**asdict(self), **overrides}
        params = {}
        for key, value in values.items():
            if key == "page" and int(value or 1) <= 1:
                continue
            if key == "tab" and value == C.TAB_OVERVIEW:
                continue
            if key == "sort" and value == C.SORT_DEFAULT:
                continue
            if value not in ("", None):
                params[f"{C.PARAM_PREFIX}{key}"] = value
        return params

    @property
    def is_filtered(self) -> bool:
        return any(
            (self.faculty, self.chair, self.title, self.staff, self.q, self.issue)
            + (self.status, self.admin, self.degree, self.band)
        )

    @property
    def sort_key(self) -> str:
        return self.sort.lstrip("-")

    @property
    def sort_desc(self) -> bool:
        return self.sort.startswith("-")


def _int(value, default: int = 1) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def parse_filters(params, *, years, default_year: str, faculties, chairs, admin_roles=()) -> HrFilters:
    """``request.GET`` → ``HrFilters`` (allowlist-lə). ``admin_roles`` — datada rast gəlinən inzibati rol adları."""

    def get(name: str) -> str:
        return (params.get(f"{C.PARAM_PREFIX}{name}") or "").strip()

    year = get("year")
    if year not in years:
        year = default_year
    faculty = get("faculty")
    if faculty not in {item["value"] for item in faculties}:
        faculty = ""
    chair = get("chair")
    if chair not in {item["value"] for item in chairs}:
        chair = ""
    title = get("title")
    if title not in (*C.TITLE_ORDER, C.TITLE_NONE):
        title = ""
    staff = get("staff")
    if staff not in C.STAFF_KEYS:
        staff = ""
    issue = get("issue")
    if issue not in C.ISSUE_KEYS:
        issue = ""
    status = get("status")
    if status not in C.ACCOUNT_KEYS:
        status = ""
    admin = get("admin")
    if admin not in (C.ADMIN_ANY, C.ADMIN_NONE, *admin_roles):
        admin = ""
    degree = get("degree")
    if degree not in (*C.DEGREE_ORDER, C.DEGREE_NONE):
        degree = ""
    band = get("band")
    if band not in {key for key, _label in C.LOAD_BANDS}:
        band = ""
    sort = get("sort")
    if sort.lstrip("-") not in C.SORT_KEYS or sort in ("-", ""):
        sort = C.SORT_DEFAULT
    tab = get("tab") or C.TAB_OVERVIEW
    if tab not in C.TAB_KEYS:
        tab = C.TAB_OVERVIEW
    return HrFilters(
        year=year,
        faculty=faculty,
        chair=chair,
        title=title,
        staff=staff,
        q=get("q")[:100],
        issue=issue,
        status=status,
        admin=admin,
        degree=degree,
        band=band,
        sort=sort,
        tab=tab,
        page=_int(params.get(f"{C.PARAM_PREFIX}page")),
    )


def _status_matches(row: dict, status: str) -> bool:
    """``hr_status`` — KPI kartlarının dəstləri ilə birəbir (``aggregates.kpis``)."""
    if status == C.ACCOUNT_ACTIVE:
        return row["status"] == C.STATUS_ACTIVE
    if status == C.ACCOUNT_STOPPED:
        return row["status"] in (C.STATUS_BLOCKED, C.STATUS_ARCHIVED)
    if status == C.ACCOUNT_BLOCKED:
        return row["status"] == C.STATUS_BLOCKED
    if status == C.ACCOUNT_ARCHIVED:
        return row["status"] == C.STATUS_ARCHIVED
    if status == C.ACCOUNT_NEVER:
        return bool(row["never_logged_in"])
    if status == C.ACCOUNT_INITIAL:
        return bool(row["not_activated"])
    if status == C.ACCOUNT_NEW:
        return bool(row["is_new"])
    return True


def _admin_matches(row: dict, admin: str) -> bool:
    has_any = bool(row["admin_roles"] or row["staff_position"])
    if admin == C.ADMIN_ANY:
        return has_any
    if admin == C.ADMIN_NONE:
        return not has_any
    return admin in row["admin_role_names"]


def apply_filters(rows, filters: HrFilters, *, with_issue: bool = True) -> list[dict]:
    """Struktur / elmi ad / dərəcə / ştat / hesab / inzibati vəzifə / yük bandı / axtarış (+ problem)."""
    out = []
    for row in rows:
        if filters.faculty and row["faculty_id"] != filters.faculty:
            continue
        if filters.chair and row["chair_id"] != filters.chair:
            continue
        if filters.title and row["title"] != filters.title:
            continue
        if filters.degree and row["degree"] != filters.degree:
            continue
        if filters.staff and row["staff_type"] != filters.staff:
            continue
        if filters.status and not _status_matches(row, filters.status):
            continue
        if filters.admin and not _admin_matches(row, filters.admin):
            continue
        if filters.band and row["load_band"] != filters.band:
            continue
        if with_issue and filters.issue and filters.issue not in row["issues"]:
            continue
        if filters.q and not tolerant_match(
            filters.q, row["name"], row["username"], row["chair"], row["faculty"], row["admin_label"]
        ):
            continue
        out.append(row)
    return out


# ── Sıralama (yalnız «Müəllimlər» tabı) ────────────────────────────────────
_TITLE_RANK = {key: index for index, key in enumerate((*C.TITLE_ORDER, C.TITLE_NONE))}
_STATUS_RANK = {key: index for index, key in enumerate(C.STATUS_ORDER)}


def _staff_rank(row: dict) -> float:
    """Ştat payı rəqəmlə; saathesabı → −1, təyin edilməyib → −2 (azalan sırada sonda)."""
    if row["staff_type"] == C.STAFF_NONE:
        return -2.0
    if row["staff_type"] == C.STAFF_HOURLY:
        return -1.0
    return float(row["staff_fraction"] or 0)


_SORTERS = {
    C.SORT_NAME: lambda row: (row["name"].casefold(),),
    C.SORT_CHAIR: lambda row: (not row["chair"], row["chair"].casefold(), row["name"].casefold()),
    C.SORT_TITLE: lambda row: (_TITLE_RANK.get(row["title"], 99), row["name"].casefold()),
    C.SORT_STAFF: lambda row: (_staff_rank(row), row["name"].casefold()),
    C.SORT_ADMIN: lambda row: (not row["admin_label"], row["admin_label"].casefold(), row["name"].casefold()),
    C.SORT_LOAD: lambda row: (row["fill_percent"], row["planned_load"], row["name"].casefold()),
    C.SORT_ACTIVITY: lambda row: (row["journals"], row["lessons"], row["name"].casefold()),
    C.SORT_STATUS: lambda row: (_STATUS_RANK.get(row["status"], 99), row["name"].casefold()),
    C.SORT_JOINED: lambda row: (row["joined"] or date.min, row["name"].casefold()),
}


def sort_rows(rows, filters: HrFilters) -> list[dict]:
    """Seçilmiş açara görə sıralayır; bərabərlikdə ad, sonra id (sabit səhifələmə)."""
    key = _SORTERS.get(filters.sort_key, _SORTERS[C.SORT_NAME])
    ordered = sorted(rows, key=lambda row: (*key(row), row["id"]))
    if filters.sort_desc:
        ordered.reverse()
    return ordered


__all__ = ["HrFilters", "apply_filters", "parse_filters", "sort_rows"]
