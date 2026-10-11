"""«Kadr analitikası» filtrləri — GET normallaşdırma (``hr_*``) + yaddaşda tətbiq.

Xam GET heç vaxt aşağı qata düşmür: hər dəyər allowlist-ə (il siyahısı, struktur id-ləri, sabit
açarlar) qarşı yoxlanılır, tanınmayan dəyər səssizcə boşalır (500 yox, «filtrsiz» görünüş).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

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
            if value not in ("", None):
                params[f"{C.PARAM_PREFIX}{key}"] = value
        return params

    @property
    def is_filtered(self) -> bool:
        return any((self.faculty, self.chair, self.title, self.staff, self.q, self.issue))


def _int(value, default: int = 1) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def parse_filters(params, *, years, default_year: str, faculties, chairs) -> HrFilters:
    """``request.GET`` → ``HrFilters`` (allowlist-lə)."""

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
        tab=tab,
        page=_int(params.get(f"{C.PARAM_PREFIX}page")),
    )


def apply_filters(rows, filters: HrFilters, *, with_issue: bool = True) -> list[dict]:
    """Struktur / elmi ad / ştat / axtarış (+ istəyə görə problem) süzgəcləri."""
    out = []
    for row in rows:
        if filters.faculty and row["faculty_id"] != filters.faculty:
            continue
        if filters.chair and row["chair_id"] != filters.chair:
            continue
        if filters.title and row["title"] != filters.title:
            continue
        if filters.staff and row["staff_type"] != filters.staff:
            continue
        if with_issue and filters.issue and filters.issue not in row["issues"]:
            continue
        if filters.q and not tolerant_match(filters.q, row["name"], row["username"], row["chair"], row["faculty"]):
            continue
        out.append(row)
    return out


__all__ = ["HrFilters", "apply_filters", "parse_filters"]
