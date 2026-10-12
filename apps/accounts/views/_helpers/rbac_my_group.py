"""«Qrupum» (`my-group`) bölməsinin qapısı — rol auditi 2026-10-13 B10.

NİYƏ? ``lead_student`` (baş tələbə / starosta) şablonu «öz qrupuna aid məhdud üzv siyahısı və qrup
səviyyəli statistika» vəd edir və ``member.view`` daşıyır, amma kabinetdə bu açarı oxuyan heç bir
səth yox idi: ``is_lead_student`` hesablanırdı və heç yerdə işlənmirdi, «Üzvlər» (`org-members`)
rol bayrağı ilə qapalıdır, AI köməkçi isə ona açılmayan `org-members` linkini təklif edirdi.

QAYDA (rol ADI ilə yox, AÇAR + ƏHATƏ ilə — «hər rol öz səlahiyyəti qədər»):

* ``member.view`` açarını daşıyan **UNIT** rolunun ``scope_unit``-i AKADEMİK QRUP (``OrgUnitType.GROUP``)
  olmalıdır — həll ``get_permission_scope(user, org, "member.view")`` ilə aparılır;
* təşkilat-geniş əhatə (HR, imtahan mərkəzi, superadmin, sahib) «qrupum» DEYİL → bölmə yoxdur;
* fakültə/kafedra əhatəsi (dekan, kafedra müdiri) qrup deyil → bölmə yoxdur (onların öz səthləri var);
* ``scope_unit``-siz baş tələbə → əhatə boşdur → bölmə yoxdur (fail-closed).

SORĞU BÜDCƏSİ: kabinet qabığı sorğu-büdcəlidir (``test_rbac_permission_cache``). ``get_permission_scope``
üzvlük sətirlərini ``user``-də memoizasiya edir; qrup növü isə middleware/``roles.py``-in artıq
``select_related("scope_unit")`` ilə yüklədiyi üzvlük sətirlərindən oxunur — əlavə ``OrgUnit`` SELECT-i
yoxdur. Açarsız və ya əhatəsi qrup olmayan aktor üçün sıfır əlavə sorğu.

Bu GÖRÜNÜRLÜK qapısıdır; data qapısı (``templatetags/my_group_tags.my_group_unit``) EYNİ funksiyanı
render vaxtı yenidən çağırır, registrar paneli isə yalnız bu funksiyanın qaytardığı qrupu göstərir.
"""

from __future__ import annotations

MY_GROUP_SECTION = "my-group"

#: Qrup üzv siyahısının açarı — ``lead_student`` şablonunda (``default_roles_university``) var.
MY_GROUP_PERMISSION = "member.view"


def _org_memberships(user, organization) -> list:
    """Aktiv org üzvlükləri (``scope_unit`` yüklü) — bağlanmış siyahı varsa sorğusuz."""
    from apps.organizations.public import get_active_memberships

    from .rbac_memberships import _bound_active_org_memberships

    memberships = _bound_active_org_memberships(user, getattr(organization, "pk", None))
    if memberships is not None:
        return memberships
    return [m for m in get_active_memberships(user, organization) if m.organization_id == organization.pk]


def my_group_unit(user, organization):
    """Aktorun ``member.view`` əhatəsinin AKADEMİK QRUPU (``OrgUnit``) və ya ``None``.

    Bir neçə qrup varsa (nadir: iki baş tələbə üzvlüyü) ad sırasına görə birincisi götürülür —
    deterministik, menyu ilə panel eyni qrupu göstərir.
    """
    if user is None or organization is None or not getattr(user, "is_authenticated", False):
        return None
    from apps.organizations.public import get_permission_scope
    from core.constants import OrgUnitType

    scope = get_permission_scope(user, organization, MY_GROUP_PERMISSION)
    if not scope.is_unit_scoped or not scope.unit_ids:
        return None
    groups = []
    for membership in _org_memberships(user, organization):
        unit = getattr(membership, "scope_unit", None)
        if unit is None or membership.scope_unit_id not in scope.unit_ids:
            continue
        if unit.unit_type == OrgUnitType.GROUP and unit.is_active and unit.organization_id == organization.pk:
            groups.append(unit)
    if not groups:
        return None
    return min(groups, key=lambda unit: ((unit.name or "").lower(), str(unit.pk)))


def my_group_sections(user, organization) -> set:
    """``{"my-group"}`` və ya boş dəst (``rbac_sections.apply_permission_section_gates`` birləşdirir)."""
    return {MY_GROUP_SECTION} if my_group_unit(user, organization) is not None else set()


__all__ = ["MY_GROUP_PERMISSION", "MY_GROUP_SECTION", "my_group_sections", "my_group_unit"]
