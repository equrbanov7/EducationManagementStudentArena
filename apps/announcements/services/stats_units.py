"""Elan statistikası — bölmə köməkçiləri: ad/yol xəritəsi, ölçü üzrə «yuxarı bölmə», uzaq axtarış.

Struktur (prod, 2026-11-18): ``fakültə → ixtisas → qrup`` (tələbələr) və ``fakültə → kafedra``
(müəllimlər; ``Membership.scope_unit``). ``OrgUnit.path`` = ``"<kök-id>/…/<öz-id>"`` olduğundan
istifadəçinin hər ölçüdəki bölməsi yol seqmentlərindən tapılır — hər istifadəçi üçün sorğu YOX:
bölmə xəritəsi ən çox İKİ sorğudur (bölmələrin özü + yoldakı əcdadlar).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.utils.translation import pgettext

from core.constants import OrgUnitType
from core.search_text import tolerant_q

from ..constants import STATS_UNIT_SEARCH_LIMIT, UNIT_TYPE_LABELS

_CTX = "announcements.stats"

#: Ölçü → bu ölçüdə sayılan bölmə tipləri (ən yaxın əcdad götürülür).
DIMENSION_TYPES = {
    "faculty": (OrgUnitType.FACULTY,),
    "chair": (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT),
    "specialty": (OrgUnitType.SPECIALTY,),
    "group": (OrgUnitType.GROUP,),
}
#: Filtr/axtarışda təklif olunan bölmə tipləri.
FILTER_TYPES = (
    OrgUnitType.FACULTY,
    OrgUnitType.CHAIR,
    OrgUnitType.DEPARTMENT,
    OrgUnitType.SPECIALTY,
    OrgUnitType.GROUP,
)


def _segments(path) -> list:
    return [segment for segment in (path or "").strip("/").split("/") if segment]


def unit_map(org_id, unit_ids) -> dict:
    """``{id: {"name", "type", "path"}}`` — verilən bölmələr VƏ onların bütün əcdadları (≤ 2 sorğu)."""
    wanted = {str(pk) for pk in unit_ids or () if pk}
    if not wanted:
        return {}
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    result: dict = {}

    def _load(ids):
        rows = OrgUnit.objects.filter(organization_id=org_id, pk__in=sorted(ids)).values_list(
            "pk", "name", "unit_type", "path"
        )
        for pk, name, unit_type, path in rows:
            result[str(pk)] = {"name": name, "type": unit_type, "path": path or ""}

    _load(wanted)
    ancestors = {segment for item in result.values() for segment in _segments(item["path"])} - set(result)
    if ancestors:
        _load(ancestors)
    return result


def nearest(units: dict, unit_id, types) -> str:
    """Bölmənin özü və ya ən yaxın əcdadı arasında ``types``-dan olanın id-si (yoxdursa ``""``)."""
    item = units.get(str(unit_id or ""))
    if item is None:
        return ""
    chain = _segments(item["path"]) or [str(unit_id)]
    for segment in reversed(chain):
        node = units.get(segment)
        if node is not None and node["type"] in types:
            return segment
    return ""


def unit_label(units: dict, unit_id) -> str:
    item = units.get(str(unit_id or ""))
    return item["name"] if item else ""


def option_text(name, unit_type) -> str:
    label = UNIT_TYPE_LABELS.get(unit_type, "")
    return f"{name} · {label}" if label else str(name)


def _scoped(queryset, scope):
    if not scope.is_org_wide or scope.excluded_unit_ids:
        queryset = queryset.filter(scope.unit_subtree_q())
    return queryset


def initial_options(scope, organization) -> list:
    """Filtrin ilk siyahısı: yalnız fakültə və kafedralar (az sayda); qalanı uzaq axtarışla gəlir."""
    if not scope.has_structure_access:
        return []
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    queryset = OrgUnit.objects.filter(
        organization=organization,
        is_active=True,
        unit_type__in=(OrgUnitType.FACULTY, OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT),
    )
    rows = _scoped(queryset, scope).order_by("path").values_list("pk", "name", "unit_type")[:300]
    return [{"id": str(pk), "text": option_text(name, unit_type)} for pk, name, unit_type in rows]


def search_units(scope, organization, query: str) -> list:
    """Uzaq axtarış (``bootstrap_select_remote``): ad / kod üzrə dözümlü, əhatə ilə süzülür."""
    if not scope.has_structure_access:
        return []
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    queryset = _scoped(
        OrgUnit.objects.filter(organization=organization, is_active=True, unit_type__in=FILTER_TYPES), scope
    )
    search = tolerant_q(query, ("name",), compact_fields=("code",)) if query else None
    if search is not None:
        queryset = queryset.filter(search)
    rows = queryset.order_by("level", "name").values_list("pk", "name", "unit_type")[:STATS_UNIT_SEARCH_LIMIT]
    return [{"id": str(pk), "text": option_text(name, unit_type)} for pk, name, unit_type in rows]


def selected_option(scope, organization, unit_id) -> dict | None:
    """Seçilmiş bölmə (əhatədə olmalıdır) — seçicidə göstərmək üçün; yoxdursa ``None``."""
    if not unit_id:
        return None
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    queryset = _scoped(OrgUnit.objects.filter(organization=organization, pk=unit_id, unit_type__in=FILTER_TYPES), scope)
    row = queryset.values_list("pk", "name", "unit_type").first()
    return {"id": str(row[0]), "text": option_text(row[1], row[2])} if row else None


def missing_label() -> str:
    return pgettext(_CTX, "Bölmə göstərilməyib")


__all__ = [
    "DIMENSION_TYPES",
    "FILTER_TYPES",
    "initial_options",
    "missing_label",
    "nearest",
    "option_text",
    "search_units",
    "selected_option",
    "unit_label",
    "unit_map",
]
