"""«Jurnal təmizliyi» — OXU endpoint-i (JSON): siyahı sətirləri, çip sayları, «hamısını seç», tarixçə.

Fail-closed: icazəsiz aktor ``has_access: false`` və BOŞ data alır — nə sətir, nə say, nə ad sızır.
Domen məntiqi registrar-dadır (``journal_hygiene`` sorğu, ``journal_hygiene_rows`` təqdimat).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.registrar.public import journal_hygiene as hygiene
from apps.registrar.public import journal_hygiene_rows as hygiene_rows

from .policy import resolve_actor

TABS = {"left": hygiene.LEFT, "empty": hygiene.EMPTY, "not_held": hygiene.NOT_HELD}
_EMPTY = {
    "has_access": False,
    "can_apply": False,
    "results": [],
    "page": 1,
    "num_pages": 1,
    "total": 0,
    "has_next": False,
    "has_previous": False,
    "counts": {},
}


def _int(value, default):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _filters(request) -> dict:
    keys = (*hygiene.FILTER_KEYS, "state")
    return {key: (request.GET.get(key) or "").strip()[:100] for key in keys}


@never_cache
@login_required
@require_GET
def journal_hygiene_rows(request):
    """``?tab=left|empty|not_held|history`` + süzgəclər + ``page``/``page_size``; ``select=all`` → ilk ≤500 id.

    ``not_held`` vahid açılışdır: «hamısını seç» yalnız 500-ə TAM sığan açılışları götürür (yarımçıq yox)."""
    actor = resolve_actor(request)
    if not actor.has_access:
        return JsonResponse(_EMPTY)
    organization = actor.organization
    tab = (request.GET.get("tab") or "left").strip()
    filters = _filters(request)
    number = _int(request.GET.get("page"), 1)
    size = _int(request.GET.get("page_size"), hygiene_rows.PAGE_SIZE)
    if tab == "history":
        data = hygiene_rows.history_page(hygiene_rows.history_queryset(organization, filters), number=number, size=size)
        data["counts"] = hygiene_rows.history_counts(organization)
    else:
        category = TABS.get(tab, hygiene.LEFT)
        queryset = hygiene.candidates(organization, category, filters)
        if request.GET.get("select") == "all":
            if category == hygiene.NOT_HELD:
                pairs = queryset.values_list("pk", "offering_id")[: hygiene_rows.MAX_BATCH + 1]
                ids = hygiene.not_held.whole_offering_ids(pairs, hygiene_rows.MAX_BATCH)
            else:
                ids = queryset.values_list("pk", flat=True)[: hygiene_rows.MAX_BATCH]
            return JsonResponse({"has_access": True, "ids": [str(pk) for pk in ids]})
        chips = hygiene.counts(hygiene.candidates(organization, category, {**filters, "category": ""}), category)
        total = hygiene_rows.page_total(chips, filters.get("category"))
        data = hygiene_rows.page(queryset, category, number=number, size=size, total=total)
        data["counts"] = chips
    data.update(has_access=True, can_apply=actor.can_apply, tab=tab)
    return JsonResponse(data)


__all__ = ["journal_hygiene_rows"]
