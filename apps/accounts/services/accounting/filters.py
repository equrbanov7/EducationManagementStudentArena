"""«Mühasibatlıq» filtrləri — GET normallaşdırma (``ac_*``), allowlist ilə (tanınmayan dəyər boşalır)."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from . import constants as C

MONTH_ALL = "all"


@dataclass(frozen=True)
class AccountingFilters:
    semester: str = ""
    month: str = ""
    faculty: str = ""
    chair: str = ""
    q: str = ""
    deviation: str = ""
    sort: str = C.SORT_DEFAULT
    page: int = 1
    #: Drill-down: müəllimin istifadəçi id-si (yalnız əhatədəki müəllim açılır).
    teacher: str = ""
    lpage: int = 1

    def as_params(self, **overrides) -> dict:
        values = {**asdict(self), **overrides}
        params = {}
        for key, value in values.items():
            if key in ("page", "lpage") and int(value or 1) <= 1:
                continue
            if key == "sort" and value == C.SORT_DEFAULT:
                continue
            if value not in ("", None):
                params[f"{C.PARAM_PREFIX}{key}"] = value
        return params

    @property
    def is_filtered(self) -> bool:
        return any((self.faculty, self.chair, self.q, self.deviation))


def _int(value, default: int = 1) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return number if 0 < number < 100_000 else default


def parse_filters(params, *, semesters, default_semester, months_for, default_month_for, faculties, chairs):
    """``request.GET`` → ``AccountingFilters``. ``months_for(semester)`` — həmin semestrin ay açarları."""

    def get(name):
        return str(params.get(f"{C.PARAM_PREFIX}{name}") or "").strip()

    by_key = {item.key: item for item in semesters}
    semester = by_key.get(get("semester")) or default_semester
    semester_key = semester.key if semester else ""
    month = get("month")
    allowed_months = months_for(semester) if semester else []
    if month != MONTH_ALL and month not in allowed_months:
        month = default_month_for(semester) if semester else ""
    faculty = get("faculty")
    if faculty not in {item["value"] for item in faculties}:
        faculty = ""
    chair = get("chair")
    allowed_chairs = {item["value"] for item in chairs if not faculty or item["faculty_id"] == faculty}
    if chair not in allowed_chairs:
        chair = ""
    sort = get("sort") or C.SORT_DEFAULT
    if sort.lstrip("-") not in C.SORT_KEYS:
        sort = C.SORT_DEFAULT
    teacher = get("teacher")
    teacher_id = parse_teacher_id(teacher)
    return AccountingFilters(
        semester=semester_key,
        month=month,
        faculty=faculty,
        chair=chair,
        q=get("q")[:100],
        deviation="1" if get("deviation") == "1" else "",
        sort=sort,
        page=_int(get("page")),
        teacher=str(teacher_id) if teacher_id is not None else "",
        lpage=_int(get("lpage")),
    )


def parse_teacher_id(raw):
    """İstifadəçi id-si — müsbət tam ədəd (``User.pk``); pozuq dəyər → ``None``."""
    raw = str(raw or "").strip()
    return int(raw) if raw.isdigit() and 0 < len(raw) < 12 and int(raw) > 0 else None


__all__ = ["AccountingFilters", "MONTH_ALL", "parse_filters", "parse_teacher_id"]
