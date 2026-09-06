"""RİM «yeni hesab» — SEÇİCİ KATALOQU (qrup / kafedra type-ahead).

NİYƏ AYRICA ENDPOINT? Repetisiya bazasında bir universitetin 766 aktiv qrupu
var. Onları bölmə context-ində ``<select>`` kimi render etsək hər RİM açılışına
~50 KB ölü markup düşərdi (operator isə bir qrup seçir). Ona görə seçicilər
axtarışlı və səhifəlidir: istifadəçi yazır → server 20 nəticə qaytarır.

QAPI: eyni ``user.import`` açarı (bax `create.require_create`). Qəsdən
`people_academic_groups` endpoint-i TƏKRAR İSTİFADƏ EDİLMİR — o, ayrı açardan
(`people.manage_academic`) keçir və formu gizli ikinci icazəyə bağlayardı.
"""

from __future__ import annotations

from django.db.models import Q

from core.constants import OrgUnitType

from .create import require_create
from .create_form import CHAIR_UNIT_TYPES

#: Bir sorğuda qaytarılan maksimum nəticə (UI 20 göstərir, +1 «daha var» üçün).
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_QUERY_LENGTH = 120

CATALOG_GROUP = "group"
CATALOG_UNIT = "unit"
CATALOGS = (CATALOG_GROUP, CATALOG_UNIT)

_UNIT_TYPES = {
    CATALOG_GROUP: (OrgUnitType.GROUP,),
    CATALOG_UNIT: CHAIR_UNIT_TYPES,
}


def _bounds(limit, offset):
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    try:
        offset = int(offset)
    except (TypeError, ValueError):
        offset = 0
    return max(1, min(limit, MAX_LIMIT)), max(0, offset)


def _parent_labels(units) -> dict:
    """``{parent_id: ad}`` — nəticə sətrinin ikinci sətri (kontekst).

    766 «BM-21» adlı qrupdan hansının seçildiyini ADDAN bilmək olmur; valideyn
    bölmənin (ixtisas/kafedra) adı seçimi birmənalı edir.
    """

    from apps.organizations.models import OrgUnit

    parent_ids = {unit.parent_id for unit in units if unit.parent_id}
    if not parent_ids:
        return {}
    return {str(row["id"]): row["name"] for row in OrgUnit.objects.filter(pk__in=list(parent_ids)).values("id", "name")}


def search_catalog(actor, *, catalog: str, query: str = "", limit=DEFAULT_LIMIT, offset=0) -> dict:
    """Aktorun təşkilatındakı qrup / kafedra siyahısı — axtarışlı, səhifəli."""

    require_create(actor)
    if catalog not in CATALOGS:
        return {"results": [], "has_more": False}

    from apps.organizations.models import OrgUnit

    text = str(query or "").strip()[:MAX_QUERY_LENGTH]
    queryset = OrgUnit.objects.filter(
        organization=actor.organization,
        unit_type__in=_UNIT_TYPES[catalog],
        is_active=True,
    )
    if text:
        queryset = queryset.filter(Q(name__icontains=text) | Q(code__icontains=text))

    limit, offset = _bounds(limit, offset)
    # +1 sətir: «daha var» bayrağını ayrıca COUNT sorğusu olmadan hesablayır.
    window = list(
        queryset.order_by("name", "code").only("id", "name", "code", "parent_id")[offset : offset + limit + 1]
    )
    labels = _parent_labels(window[:limit])

    return {
        "results": [
            {
                "id": str(unit.pk),
                "text": unit.name,
                "hint": " · ".join(
                    part for part in (unit.code or "", labels.get(str(unit.parent_id or ""), "")) if part
                ),
            }
            for unit in window[:limit]
        ],
        "has_more": len(window) > limit,
    }


__all__ = [
    "CATALOGS",
    "CATALOG_GROUP",
    "CATALOG_UNIT",
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "search_catalog",
]
