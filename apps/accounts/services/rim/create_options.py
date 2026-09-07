"""RİM «yeni hesab» — SEÇİCİ KATALOQU (qrup / kafedra type-ahead).

NİYƏ AYRICA ENDPOINT? Repetisiya bazasında bir universitetin 766 aktiv qrupu
var. Onları bölmə context-ində ``<select>`` kimi render etsək hər RİM açılışına
~50 KB ölü markup düşərdi (operator isə bir qrup seçir). Ona görə seçicilər
axtarışlı və səhifəlidir: istifadəçi yazır → server 20 nəticə qaytarır.

QAPI KATALOQA GÖRƏ DƏYİŞİR:

* ``group`` / ``unit`` (hesab formu)   → ``user.import`` (bax `create.require_create`);
* ``admin_parent`` (inzibati bölmə)    → ``unit.tree_manage`` (bax `create_unit.require_create_unit`).

Yəni seçici HEÇ VAXT öz axınının açarından ZƏİF qapıdan keçmir: hesab yarada
bilməyən operator qrup siyahısını, bölmə yarada bilməyən operator isə valideyn
siyahısını görmür. Qəsdən `people_academic_groups` endpoint-i TƏKRAR İSTİFADƏ
EDİLMİR — o, ayrı açardan (`people.manage_academic`) keçir və formu gizli ikinci
icazəyə bağlayardı.
"""

from __future__ import annotations

from django.db.models import Q

from core.constants import OrgUnitType

from .create import require_create
from .create_form import CHAIR_UNIT_TYPES
from .create_unit import parent_units_queryset, require_create_unit

#: Bir sorğuda qaytarılan maksimum nəticə (UI 20 göstərir, +1 «daha var» üçün).
DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_QUERY_LENGTH = 120

CATALOG_GROUP = "group"
CATALOG_UNIT = "unit"
#: «Yeni inzibati bölmə» dialoqunun VALİDEYN seçicisi (şöbə/mərkəz haraya qoşulur).
CATALOG_ADMIN_PARENT = "admin_parent"
CATALOGS = (CATALOG_GROUP, CATALOG_UNIT, CATALOG_ADMIN_PARENT)

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


def _type_labels(actor) -> dict:
    """``{unit_type: etiket}`` — təşkilat tipinin öz kataloqundan (tərcümə orada)."""

    from apps.organizations.unit_types import UNIT_TYPES_BY_ORG

    return dict(UNIT_TYPES_BY_ORG.get(getattr(actor.organization, "org_type", ""), []))


def _base_queryset(actor, catalog: str, request=None):
    """Kataloqun MƏNBƏ queryset-i (icazə qapısından SONRA çağırılır)."""

    if catalog == CATALOG_ADMIN_PARENT:
        # Valideyn siyahısı serverin görünürlük qapısından keçir — bax
        # `create_unit.parent_units_queryset` (tip filtri orada `exclude`-dur).
        return parent_units_queryset(actor, request=request)

    from apps.organizations.models import OrgUnit

    return OrgUnit.objects.filter(
        organization=actor.organization,
        unit_type__in=_UNIT_TYPES[catalog],
        is_active=True,
    )


def search_catalog(actor, *, catalog: str, query: str = "", limit=DEFAULT_LIMIT, offset=0, request=None) -> dict:
    """Aktorun təşkilatındakı qrup / kafedra / valideyn siyahısı — axtarışlı, səhifəli."""

    # Qapı KATALOQA GÖRƏ (yuxarıdakı «QAPI» izahı) — naməlum kataloq köhnə
    # davranışı saxlayır: yaratma açarı olmayan aktor 403, olan isə boş nəticə.
    if catalog == CATALOG_ADMIN_PARENT:
        require_create_unit(actor)
    else:
        require_create(actor)
    if catalog not in CATALOGS:
        return {"results": [], "has_more": False}

    text = str(query or "").strip()[:MAX_QUERY_LENGTH]
    queryset = _base_queryset(actor, catalog, request=request)
    if text:
        queryset = queryset.filter(Q(name__icontains=text) | Q(code__icontains=text))

    limit, offset = _bounds(limit, offset)
    # +1 sətir: «daha var» bayrağını ayrıca COUNT sorğusu olmadan hesablayır.
    window = list(
        queryset.order_by("name", "code").only("id", "name", "code", "parent_id", "unit_type")[
            offset : offset + limit + 1
        ]
    )
    labels = _parent_labels(window[:limit])
    # Valideyn seçicisində TİP etiketi vacibdir: «Mühəndislik» fakültədir, yoxsa
    # şöbə? Hesab seçicilərində tip birmənalıdır (qrup / kafedra), ona görə orada
    # göstərilmir.
    types = _type_labels(actor) if catalog == CATALOG_ADMIN_PARENT else {}

    return {
        "results": [
            {
                "id": str(unit.pk),
                "text": unit.name,
                "hint": " · ".join(
                    part
                    for part in (
                        str(types.get(unit.unit_type, "")),
                        unit.code or "",
                        labels.get(str(unit.parent_id or ""), ""),
                    )
                    if part
                ),
            }
            for unit in window[:limit]
        ],
        "has_more": len(window) > limit,
    }


__all__ = [
    "CATALOGS",
    "CATALOG_ADMIN_PARENT",
    "CATALOG_GROUP",
    "CATALOG_UNIT",
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "search_catalog",
]
