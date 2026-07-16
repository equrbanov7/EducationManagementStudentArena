"""Monitorinq API-ları üçün kiçik, sərt limitli pagination helper-ləri."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DEFAULT_PAGE_SIZE = 25
MIN_PAGE_SIZE = 10
MAX_PAGE_SIZE = 50
MAX_PAGE = 1000


def _bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def parse_pagination(
    params: Mapping[str, Any],
    *,
    default_page_size: int = DEFAULT_PAGE_SIZE,
    max_page: int = MAX_PAGE,
) -> tuple[int, int]:
    """İstifadəçi pagination parametrlərini təhlükəsiz intervala sal."""
    page = _bounded_int(params.get("page"), default=1, minimum=1, maximum=max_page)
    page_size = _bounded_int(
        params.get("page_size"),
        default=default_page_size,
        minimum=MIN_PAGE_SIZE,
        maximum=MAX_PAGE_SIZE,
    )
    return page, page_size


def clamp_page(page: int, *, total: int, page_size: int) -> int:
    """Silinmiş/azalmış dataset üçün səhifəni son mövcud səhifəyə sal."""
    total_pages = max(1, (total + page_size - 1) // page_size)
    return min(max(1, page), total_pages)


def paginated_data(
    field: str,
    items: list[dict],
    *,
    total: int,
    page: int,
    page_size: int,
    has_next: bool | None = None,
    total_pages: int | None = None,
    total_exact: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Köhnə siyahı açarını qoruyaraq vahid pagination contract-ı yarat."""
    if total_pages is None:
        total_pages = (total + page_size - 1) // page_size if total else 0
    if has_next is None:
        has_next = page < total_pages

    pagination = {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": has_next,
        "has_previous": page > 1,
        "total_exact": total_exact,
    }
    data: dict[str, Any] = {
        field: items,
        "items": items,
        **pagination,
        "pagination": pagination.copy(),
    }
    if extra:
        data.update(extra)
    return data
