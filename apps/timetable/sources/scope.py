"""İşləmənin ƏHATƏSİ — fakültə / ixtisas / seçilmiş qruplar → qrup siyahısı.

Hər şey aktorun ``schedule.manage`` alt-ağacı ilə kəsişir (fail-closed): proqram
koordinatoru «fakültə» seçsə belə yalnız öz ixtisasının qrupları daxil olur.
Qrup seçimində ALT QRUP AİLƏSİ avtomatik tamamlanır (birləşik qrup «234 K ing» ilə
«234 K ing-1/-2» birlikdə planlaşdırılmalıdır — biri o birinin tələbələrini tutur).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db.models import Q

from apps.registrar.public import schedule_manage, subgroup_rollup
from core.constants import OrgUnitType

from ..constants import ScopeKind


def _unit_model():
    return django_apps.get_model("organizations", "OrgUnit")


def actor_groups(actor, organization):
    """Aktorun cədvəl qura biləcəyi aktiv qruplar (queryset, fail-closed)."""
    return schedule_manage.scoped_groups(actor, organization)


def scope_options(actor, organization) -> dict:
    """Seçicilər üçün fakültə və ixtisaslar — yalnız aktorun qruplarının ataları."""
    ancestor_ids: set = set()
    for path in actor_groups(actor, organization).values_list("path", flat=True):
        parts = [part for part in str(path or "").split("/") if part]
        ancestor_ids.update(parts[:-1])
    units = _unit_model().objects.filter(organization=organization, pk__in=ancestor_ids, is_active=True)
    faculties, programs = [], []
    for unit in units.order_by("name"):
        row = {"id": str(unit.pk), "name": unit.name}
        if unit.unit_type == OrgUnitType.FACULTY:
            faculties.append(row)
        elif unit.unit_type == OrgUnitType.SPECIALTY:
            programs.append(row)
    return {"faculties": faculties, "programs": programs}


def normalize_scope(raw) -> dict:
    """Xam POST/JSON → ``{"kind", "unit_ids", "group_ids", "label"}``."""
    raw = raw if isinstance(raw, dict) else {}
    kind = str(raw.get("kind") or "").strip()
    if kind not in dict(ScopeKind.choices):
        kind = ScopeKind.FACULTY

    def _ids(key):
        value = raw.get(key) or []
        if isinstance(value, str):
            value = [part for part in value.split(",")]
        return sorted({str(item).strip() for item in value if str(item or "").strip()})

    return {
        "kind": kind,
        "unit_ids": _ids("unit_ids"),
        "group_ids": _ids("group_ids"),
        "label": str(raw.get("label") or "").strip()[:160],
    }


def _complete_families(base, selected):
    """Seçilmiş qrupların alt qrup / birləşik qrup qohumlarını da əlavə et."""
    selected = list(selected)
    if not selected:
        return selected
    parent_ids = {group.parent_id for group in selected if group.parent_id}
    siblings = list(base.filter(parent_id__in=parent_ids))
    chosen = {str(group.pk): group for group in selected}
    for group in selected:
        explicit = str((group.settings or {}).get("parent_group") or "") if isinstance(group.settings, dict) else ""
        for other in siblings:
            key = str(other.pk)
            if key in chosen or other.parent_id != group.parent_id:
                continue
            other_parent = (
                str((other.settings or {}).get("parent_group") or "") if isinstance(other.settings, dict) else ""
            )
            related = (
                explicit == key
                or other_parent == str(group.pk)
                or subgroup_rollup.is_subgroup_of(group.name, other.name)
                or subgroup_rollup.is_subgroup_of(other.name, group.name)
            )
            if related:
                chosen[key] = other
    return sorted(chosen.values(), key=lambda unit: (unit.name, str(unit.pk)))


def scope_groups(actor, organization, scope) -> list:
    """Əhatədəki qruplar (ada görə sıralı, deterministik)."""
    scope = normalize_scope(scope)
    base = actor_groups(actor, organization).select_related("parent")
    if scope["kind"] == ScopeKind.GROUPS:
        return _complete_families(base, base.filter(pk__in=scope["group_ids"]))
    units = list(_unit_model().objects.filter(organization=organization, pk__in=scope["unit_ids"]))
    if not units:
        return []
    condition = Q()
    for unit in units:
        condition |= Q(path__startswith=f"{unit.path}/")
    return sorted(base.filter(condition), key=lambda unit: (unit.name, str(unit.pk)))


def scope_label(organization, scope) -> str:
    """İnsan üçün əhatə adı (işləmə siyahısında göstərilir)."""
    scope = normalize_scope(scope)
    if scope["label"]:
        return scope["label"]
    ids = scope["group_ids"] if scope["kind"] == ScopeKind.GROUPS else scope["unit_ids"]
    names = list(
        _unit_model()
        .objects.filter(organization=organization, pk__in=ids)
        .order_by("name")
        .values_list("name", flat=True)
    )
    text = ", ".join(names[:4])
    if len(names) > 4:
        text += " …"
    return text[:160]


__all__ = ["actor_groups", "normalize_scope", "scope_groups", "scope_label", "scope_options"]
