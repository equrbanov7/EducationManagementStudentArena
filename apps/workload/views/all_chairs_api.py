"""``rows?chair=all`` — «Bütün kafedralar» axtarışı (sahib 2026-11-04; bax ``services/all_chairs.py``)."""

from __future__ import annotations

from django.http import JsonResponse

from core.http_ids import parse_int

from ..services import WorkloadDenied
from ..services.all_chairs import all_chairs_rows_page
from ._base import denied

#: ``limit`` verilməyibsə / oxunmursa — ilk dilimin ölçüsü (``distribution_api._DEFAULT_PAGE`` ilə eyni).
_DEFAULT_PAGE = 30


def all_chairs_rows(request, actor) -> JsonResponse:
    """Yalnız oxu: sətirlərdə kafedra adı + ``can_edit`` / ``edit_url``; müəllim paneli və hazırlıq gəlmir."""
    limit = parse_int(request.GET.get("limit"))
    try:
        page = all_chairs_rows_page(
            actor,
            academic_year=(request.GET.get("year") or "").strip(),
            season=(request.GET.get("season") or "").strip(),
            search=request.GET.get("q") or "",
            activity=(request.GET.get("activity") or "").strip(),
            offset=parse_int(request.GET.get("offset")) or 0,
            limit=_DEFAULT_PAGE if limit is None else limit,
        )
    except WorkloadDenied as exc:
        return denied(exc)
    return JsonResponse({"ok": True, "task": None, "all_chairs": True, "readiness": None, **page})
