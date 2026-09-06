"""Ekran 01 «Universitet strukturu» — OrgUnit AĞACI (dizayn handoff Mərhələ 1).

Mövcud `org-faculties` / `org-kafedras` səthləri DÜZ siyahılardır və yalnız iki
tipi (fakültə + kafedra) idarə edir. Bu modul onların üstündə AĞAC görünüşü
qurur: rektorat → fakültə → dekanlıq → kafedra → ixtisas → qrup, həmçinin
mərkəz/laboratoriya kimi fakültədən kənar bölmələr.

TƏKRAR İSTİFADƏ (yenidən yazılmır):
  * scope + görünürlük  → ``tree_scope`` (permission-specific) / ``_visible_units_queryset``
    (FAIL-CLOSED: əhatəsiz aktor ``none()`` alır — handoff §8 qayda 8);
  * seçilmiş bölmənin detalı → ``unit_detail.build_unit_detail_context``
    (müəllim/tələbə/qrup/ixtisas sayğacları ORADA hesablanır, burada YOX);
  * yaratma/redaktə/rəhbər təyini/arxivləmə → ``structure_actions`` (POST).

SORĞU BÜDCƏSİ: ağac TƏK sorğu ilə yığılır (bütün görünən vahidlər + `head`),
sonra Python-da valideyn→uşaq xəritəsinə çevrilir. Vahid sayı ilə artan sorğu
YOXDUR. Seçilmiş bölmə üçün ayrıca detal sorğuları işləyir (N=1).
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext, pgettext_lazy

from core.constants import OrgUnitType

from ..scoping import get_permission_scope
from ..unit_types import UNIT_TYPES_BY_ORG
from ..views import _has_org_permission, _visible_units_queryset
from ._shared import _head_candidates, _unit_permission_flags
from .constants import KAFEDRA_UNIT_TYPES
from .unit_detail import build_unit_detail_context

_CTX = "accounts.structure_tree"

#: Ağacda göstərilən tiplərin sırası — handoff «Bölmə tipləri» siyahısı.
TREE_TYPE_ORDER: tuple[str, ...] = (
    OrgUnitType.RECTORATE,
    OrgUnitType.VICE_RECTORATE,
    OrgUnitType.FACULTY,
    OrgUnitType.DEANERY,
    OrgUnitType.CHAIR,
    OrgUnitType.DEPARTMENT,
    OrgUnitType.SPECIALTY,
    OrgUnitType.GROUP,
    OrgUnitType.CENTER,
    OrgUnitType.INSTITUTE,
    OrgUnitType.LAB,
)

#: «Rəhbəri olmayan bölmə» bayrağı YALNIZ rəhbər gözlənilən tiplərdə qalxır —
#: tələbə qrupunda rəhbər (dekan/müdir) anlayışı yoxdur, ona görə boş rəhbər
#: orada xəbərdarlıq deyil.
HEAD_EXPECTED_TYPES: frozenset[str] = frozenset(
    {
        OrgUnitType.RECTORATE,
        OrgUnitType.VICE_RECTORATE,
        OrgUnitType.FACULTY,
        OrgUnitType.DEANERY,
        *KAFEDRA_UNIT_TYPES,
        OrgUnitType.CENTER,
        OrgUnitType.INSTITUTE,
        OrgUnitType.LAB,
    }
)


def tree_scope(request, organization):
    """Ağac ekranının ƏHATƏSİ — `unit.view` açarına GÖRƏ (permission-specific).

    ⚠️ NİYƏ ``get_unit_scope`` DEYİL? Ümumi resolver ORGANIZATION rollarına
    yalnız ``level >= 90`` olduqda org-wide verir; Tədris şöbəsi rəhbəri (85),
    əməkdaşı (60) və RİM (88) həmin həddin altındadır və ``scope_unit``-ləri
    olmadığı üçün BOŞ əhatə alardılar (ekran tamamilə boş görünərdi).
    ``get_permission_scope`` isə əhatəni MƏHZ açarı daşıyan üzvlükdən çıxarır:
    org-scope rol → bütün təşkilat, unit-scope rol (kafedra müdiri) → öz
    alt-ağacı, açarı olmayan → ``EMPTY_SCOPE`` (fail-closed).
    """
    return get_permission_scope(request.user, organization, "unit.view", request=request)


def _type_labels(organization) -> dict:
    """`unit_type` → AZ etiket (təşkilat tipinin öz kataloqundan)."""
    return {code: label for code, label in UNIT_TYPES_BY_ORG.get(organization.org_type, [])}


def unit_kind_choices(organization) -> list:
    """Yeni alt bölmə üçün icazəli tiplər — handoff-un 8 tipi.

    Köhnə `org_admin` konsolu yaratmanı {fakültə, kafedra} ilə məhdudlaşdırırdı;
    ağac ekranında bütün universitet tipləri açıqdır, çünki iyerarxiya məhz
    burada qurulur. Seçim `UNIT_TYPES_BY_ORG` kataloqundan gəlir — tenant tipinə
    uyğun olmayan dəyər servis qatında rədd edilir.
    """
    labels = _type_labels(organization)
    return [{"value": code, "label": labels[code]} for code in TREE_TYPE_ORDER if code in labels]


def _node_payload(unit, labels, *, expanded_ids, selected_id):
    return {
        "id": str(unit.id),
        "label": unit.name,
        "type": unit.unit_type,
        "type_label": labels.get(unit.unit_type, unit.unit_type),
        "code": unit.code or "",
        "head_name": (unit.head.get_full_name() or unit.head.username) if unit.head_id else "",
        "flagged": unit.head_id is None and unit.unit_type in HEAD_EXPECTED_TYPES,
        "expanded": str(unit.id) in expanded_ids,
        "selected": str(unit.id) == selected_id,
        "children": [],
    }


def _build_forest(units, labels, *, expanded_ids, selected_id):
    """Düz siyahını ağaca çevirir (tək keçid, sorğu yoxdur)."""
    nodes = {}
    for unit in units:
        nodes[str(unit.id)] = _node_payload(unit, labels, expanded_ids=expanded_ids, selected_id=selected_id)

    roots = []
    for unit in units:
        node = nodes[str(unit.id)]
        parent = nodes.get(str(unit.parent_id)) if unit.parent_id else None
        if parent is None:
            roots.append(node)
        else:
            parent["children"].append(node)

    order = {code: index for index, code in enumerate(TREE_TYPE_ORDER)}

    def _sort(items):
        items.sort(key=lambda item: (order.get(item["type"], 99), item["label"].lower()))
        for item in items:
            _sort(item["children"])

    _sort(roots)
    return roots


def _expand_to(units, target_id):
    """Seçilmiş qovşağa qədər valideyn zəncirini açır (ağac özü açılsın)."""
    by_id = {str(unit.id): unit for unit in units}
    expanded = set()
    node = by_id.get(target_id)
    while node is not None and node.parent_id:
        expanded.add(str(node.parent_id))
        node = by_id.get(str(node.parent_id))
    return expanded


def build_structure_tree_context(request, organization) -> dict:
    """«Universitet strukturu» bölməsinin konteksti."""
    scope = tree_scope(request, organization)
    can_view = scope.has_structure_access
    flags = _unit_permission_flags(request, organization)
    can_manage_tree = flags["can_edit"] or _has_org_permission(request, "unit.tree_manage")
    can_assign_head = _has_org_permission(request, "unit.assign_head")

    search = (request.GET.get("st_q") or "").strip()[:120]
    type_filter = (request.GET.get("st_type") or "").strip()
    labels = _type_labels(organization)
    if type_filter not in labels:
        type_filter = ""

    units = []
    if can_view:
        # ``is_service_unit=True`` — köçürmədən gələn texniki/status konteyneri
        # (bax ``OrgUnit.is_service_unit``) — ağacda GÖSTƏRİLMİR. Digər
        # istehlakçılar (qrup reyestri, struktur əməlləri) bu filtri
        # DAŞIMIR — orada bölmə hələ də tapılıb idarə oluna bilər.
        units = list(
            _visible_units_queryset(organization, scope)
            .filter(is_service_unit=False)
            .select_related("head", "parent")
            .order_by("path", "order")
        )

    if type_filter:
        keep = {str(unit.id) for unit in units if unit.unit_type == type_filter}
        # Filtrdə valideyn zənciri saxlanılır ki, ağacın forması pozulmasın.
        by_id = {str(unit.id): unit for unit in units}
        for unit_id in list(keep):
            node = by_id.get(unit_id)
            while node is not None and node.parent_id:
                keep.add(str(node.parent_id))
                node = by_id.get(str(node.parent_id))
        units = [unit for unit in units if str(unit.id) in keep]
    if search:
        needle = search.casefold()
        keep = {
            str(unit.id) for unit in units if needle in unit.name.casefold() or needle in (unit.code or "").casefold()
        }
        by_id = {str(unit.id): unit for unit in units}
        for unit_id in list(keep):
            node = by_id.get(unit_id)
            while node is not None and node.parent_id:
                keep.add(str(node.parent_id))
                node = by_id.get(str(node.parent_id))
        units = [unit for unit in units if str(unit.id) in keep]

    selected_id = (request.GET.get("st_unit") or "").strip()
    visible_ids = {str(unit.id) for unit in units}
    if selected_id not in visible_ids:
        selected_id = ""

    expanded_ids = _expand_to(units, selected_id) if selected_id else set()
    if not selected_id:
        # Başlanğıc vəziyyət: yalnız köklər açıq (dərin ağac ekranı boğmasın).
        expanded_ids = {str(unit.id) for unit in units if unit.parent_id is None}

    tree_nodes = _build_forest(units, labels, expanded_ids=expanded_ids, selected_id=selected_id)

    head_missing = [unit for unit in units if unit.head_id is None and unit.unit_type in HEAD_EXPECTED_TYPES]

    detail = None
    selected_unit = next((unit for unit in units if str(unit.id) == selected_id), None)
    if selected_unit is not None:
        if selected_unit.unit_type == OrgUnitType.FACULTY or selected_unit.unit_type in KAFEDRA_UNIT_TYPES:
            detail = build_unit_detail_context(request, organization, scope, selected_unit)
        else:
            # Digər tiplər üçün yüngül detal — sayğac sorğuları açılmır.
            detail = {
                "unit": selected_unit,
                "unit_type_label": labels.get(selected_unit.unit_type, selected_unit.unit_type),
                "is_light": True,
            }

    kpi_tiles = [
        {"label": pgettext(_CTX, "BÖLMƏ"), "value": len(units)},
        {
            "label": pgettext(_CTX, "FAKÜLTƏ"),
            "value": sum(1 for unit in units if unit.unit_type == OrgUnitType.FACULTY),
        },
        {
            "label": pgettext(_CTX, "KAFEDRA"),
            "value": sum(1 for unit in units if unit.unit_type in KAFEDRA_UNIT_TYPES),
        },
        {
            "label": pgettext(_CTX, "RƏHBƏRİ YOXDUR"),
            "value": len(head_missing),
            "tone": "warning" if head_missing else None,
            "note": pgettext(_CTX, "Təyinat gözləyir") if head_missing else "",
        },
    ]

    filter_fields = [
        {
            "name": "st_q",
            "label": pgettext(_CTX, "Axtarış"),
            "kind": "search",
            "value": search,
            "placeholder": pgettext(_CTX, "Bölmə adı və ya kodu"),
            "wide": True,
        },
        {
            "name": "st_type",
            "label": pgettext(_CTX, "Bölmə tipi"),
            "kind": "select",
            "value": type_filter,
            "options": [{"value": "", "label": pgettext(_CTX, "Bütün tiplər")}] + unit_kind_choices(organization),
        },
    ]

    return {
        "has_access": can_view,
        "filter_fields": filter_fields,
        "filter_count_label": pgettext(_CTX, "Nəticə: %(count)d bölmə") % {"count": len(units)},
        # Dialoq gizli sahələri — dəyərlər JS-in `data-tof-prefill` JSON-undan gəlir
        # (sətir/qovşaqdan asılıdır), server yalnız SAHƏ ADLARINI elan edir.
        "unit_dialog_hidden": [{"name": "action"}, {"name": "parent"}],
        "rename_dialog_hidden": [{"name": "action"}, {"name": "unit"}],
        "archive_dialog_hidden": [{"name": "action"}, {"name": "unit"}],
        "head_dialog_hidden": [{"name": "action"}, {"name": "unit"}],
        "form_data": {
            "data-tof-form": "1",
            "data-tof-url": reverse("organizations:structure_tree_action", kwargs={"slug": organization.slug}),
        },
        "access_denied_message": pgettext(
            _CTX, "Bu bölməyə baxış üçün struktur əhatəniz yoxdur. Administratora müraciət edin."
        ),
        "organization": organization,
        "tree_nodes": tree_nodes,
        "tree_label": pgettext(_CTX, "Universitetin struktur ağacı"),
        "tree_state": "ready" if units else "empty",
        "unit_total": len(units),
        "head_missing_count": len(head_missing),
        "kpi_tiles": kpi_tiles,
        "search_query": search,
        "type_filter": type_filter,
        "type_options": [{"value": "", "label": pgettext(_CTX, "Bütün tiplər")}] + unit_kind_choices(organization),
        "unit_kind_choices": unit_kind_choices(organization),
        "selected_unit_id": selected_id,
        "detail": detail,
        "head_candidates": _head_candidates(organization) if can_assign_head else [],
        "can_manage_tree": can_manage_tree,
        "can_assign_head": can_assign_head,
        "action_url": reverse("organizations:structure_tree_action", kwargs={"slug": organization.slug}),
        "section_url": reverse("accounts:profile") + "?section=org-structure-tree",
        "archive_hint": pgettext_lazy(
            _CTX, "Bölmə SİLİNMİR — arxivlənir. Əlaqəli tələbə, jurnal və qiymət tarixçəsi olduğu kimi qalır."
        ),
    }


# --------------------------------------------------------------------------- #
# Ekran 02 «Kafedra profili» üçün struktur qatı
# --------------------------------------------------------------------------- #


def visible_chairs(request, organization) -> list:
    """Aktorun ƏHATƏSİNDƏKİ aktiv kafedralar (fail-closed).

    Kafedra müdiri yalnız ÖZ kafedrasını görür — filtr ``_visible_units_queryset``
    üzərindən gəlir (``scope_org_units``: əhatəsiz aktor ``none()``). Yəni
    «əhatə yoxdur ≠ bütün universitet» qaydası (handoff §8/8) burada da işləyir.
    """
    scope = tree_scope(request, organization)
    if not scope.has_structure_access:
        return []
    return list(
        _visible_units_queryset(organization, scope)
        .filter(unit_type__in=KAFEDRA_UNIT_TYPES)
        .select_related("parent", "head")
        .order_by("name")
    )


def chair_detail_context(request, organization, chair) -> dict:
    """Seçilmiş kafedranın detal konteksti — mövcud qurucunun üstündən."""
    scope = tree_scope(request, organization)
    return build_unit_detail_context(request, organization, scope, chair)


__all__ = [
    "HEAD_EXPECTED_TYPES",
    "tree_scope",
    "TREE_TYPE_ORDER",
    "build_structure_tree_context",
    "chair_detail_context",
    "unit_kind_choices",
    "visible_chairs",
]
