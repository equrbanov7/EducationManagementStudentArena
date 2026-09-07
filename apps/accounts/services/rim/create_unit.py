"""RİM «yeni inzibati bölmə» — MÖVCUD struktur-ağac əməlinin RİM-dəki qapısı.

NİYƏ RİM-DƏ? Operator RİM mərkəzindən tələbə və müəllim hesabı yarada bilirdi,
amma YENİ ŞÖBƏ / MƏRKƏZ üçün «Universitet strukturu» ekranını tapıb ağacda
valideyni açmalı idi. Boşluq MƏLUMAT MODELİNDƏ deyil, YERLƏŞMƏDƏ idi: eyni
operator, eyni iş seansı, iki ayrı ekran.

⚠️ BURADA YAZI YOLU YOXDUR. Bölməni MƏHZ mövcud endpoint yaradır —
``organizations.structure_actions.structure_tree_action`` (``action=create_child``):
eyni ``unit.tree_manage`` açarı, eyni görünürlük qapısı (``_visible_units_queryset``),
eyni audit sətri. Bu modul yalnız OXUYUR — kim düyməni görür, hansı tiplər
seçilə bilər və valideyn seçicisi nə qaytarır.

TİP AYRILIĞI (ADMIN_UNIT_TYPES)
-------------------------------
RİM-dən yalnız İNZİBATİ bölmə yaradılır: şöbə, mərkəz, institut, laboratoriya.
Fakültə / kafedra / ixtisas / qrup QƏSDƏN kənardadır — onlar AKADEMİK ağacın
həlqələridir (tədris planı, proqram, jurnal onlardan asılıdır) və Tədris
şöbəsinin öz ekranından, tam ağac kontekstində qurulur.
"""

from __future__ import annotations

from django.utils.translation import pgettext

from core.constants import OrgUnitType

from .policy import RimAccessError, RimActor

_CTX = "profile.rim"

#: Ağac əməllərinin kanonik açarı (bax `structure_actions._TREE_MANAGE_ACTIONS`).
PERM_UNIT_TREE = "unit.tree_manage"

#: Serverin QƏBUL ETDİYİ köhnə açarlar — UI qapısı server qapısı ilə EYNİ
#: olmalıdır, əks halda düymə görünüb 403 verir (və ya əksinə: səlahiyyəti olan
#: operator düyməni görmür).
LEGACY_UNIT_PERMISSIONS = ("unit.edit", "unit.create")

#: RİM-dən yaradıla bilən tiplər (yuxarıdakı «TİP AYRILIĞI» izahına bax).
ADMIN_UNIT_TYPES = (
    OrgUnitType.DEPARTMENT,
    OrgUnitType.CENTER,
    OrgUnitType.INSTITUTE,
    OrgUnitType.LAB,
)

#: Valideyn ola BİLMƏYƏN tiplər — qrup tələbə konteynerdir, ixtisas isə
#: akademik proqramdır; inzibati şöbə onların altında dayanmır.
PARENT_EXCLUDED_TYPES = (OrgUnitType.GROUP, OrgUnitType.SPECIALTY)


def can_create_unit(actor: RimActor) -> bool:
    """Aktor bu təşkilatda inzibati bölmə yarada bilərmi (fail-closed)."""

    if actor is None or getattr(actor, "user", None) is None:
        return False
    if getattr(actor, "organization", None) is None:
        return False
    return any(actor.has(key) for key in (PERM_UNIT_TREE, *LEGACY_UNIT_PERMISSIONS))


def require_create_unit(actor: RimActor) -> None:
    """İcazə yoxdursa ``RimAccessError`` (403) — seçici kataloqunun qapısı."""

    if getattr(actor, "user", None) is None or getattr(actor, "organization", None) is None:
        raise RimAccessError(
            "no_organization_context",
            pgettext(_CTX, "Aktiv təşkilat konteksti yoxdur."),
        )
    if not can_create_unit(actor):
        raise RimAccessError(
            "permission_denied",
            pgettext(_CTX, "Struktur bölməsi yaratmaq üçün icazəniz yoxdur."),
        )


def admin_unit_type_choices(organization) -> list:
    """`<select>` variantları — təşkilat tipinin öz kataloqundan süzülür.

    Etiket `UNIT_TYPES_BY_ORG`-dan gəlir (tərcümə orada bir dəfə yazılır); tenant
    tipində olmayan kod siyahıya DÜŞMÜR və server qatı onu onsuz da rədd edir.
    """

    from apps.organizations.unit_types import UNIT_TYPES_BY_ORG

    labels = dict(UNIT_TYPES_BY_ORG.get(getattr(organization, "org_type", ""), []))
    return [{"value": code, "label": labels[code]} for code in ADMIN_UNIT_TYPES if code in labels]


def parent_units_queryset(actor: RimActor, request=None):
    """Valideyn seçicisinin əhatəsi — serverin GÖRDÜYÜ vahidlərlə EYNİ.

    Əhatə ``unit.view`` açarından çıxarılır (``structure_views.tree.tree_scope``
    ilə eyni resolver) və ``_visible_units_queryset`` ilə süzülür ki, seçici
    HEÇ VAXT serverin 404 verəcəyi valideyni təklif etməsin.

    ``is_service_unit`` konteynerləri kənardadır — onlar köçürmədən qalan
    texniki qovluqlardır və ağacda da göstərilmir.
    """

    from apps.organizations.models import OrgUnit
    from apps.organizations.scoping import get_permission_scope
    from apps.organizations.views import _visible_units_queryset

    organization = getattr(actor, "organization", None)
    if organization is None:
        return OrgUnit.objects.none()

    scope = get_permission_scope(actor.user, organization, "unit.view", request=request)
    return (
        _visible_units_queryset(organization, scope)
        .filter(is_service_unit=False)
        .exclude(unit_type__in=PARENT_EXCLUDED_TYPES)
    )


__all__ = [
    "ADMIN_UNIT_TYPES",
    "LEGACY_UNIT_PERMISSIONS",
    "PARENT_EXCLUDED_TYPES",
    "PERM_UNIT_TREE",
    "admin_unit_type_choices",
    "can_create_unit",
    "parent_units_queryset",
    "require_create_unit",
]
