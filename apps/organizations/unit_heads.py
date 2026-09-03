"""Tərs istiqamətli scope axtarışı: «bu bölməni KİM əhatə edir?».

``scoping.py`` İRƏLİ istiqaməti həll edir (istifadəçi → görə bildiyi alt-ağac).
Müraciət marşrutlaşdırması üçün isə TƏRSİ lazımdır: verilmiş bölmə (fakültə /
kafedra / ixtisas) üçün həmin bölməyə cavabdeh AKTİV üzvlükləri tapmaq —
məsələn «bu ixtisasın proqram koordinatoru kimdir?».

İki funksiya:

``resolve_ancestor(unit, unit_type)``
    Bölmədən yuxarı qalxaraq verilmiş tipdə ilk əcdadı (və ya bölmənin özünü)
    qaytarır. Sabit dərinlik FƏRZ EDİLMİR — universitetlərin ağac dərinliyi
    fərqlidir, ona görə ``unit_type`` yoxlaması ilə yuxarı gedilir.

``members_covering_unit(organization, unit, *, role_names)``
    Verilmiş rollardan birini daşıyan və ``unit``-i ƏHATƏ EDƏN aktiv üzvlüklər.
    Əhatə iki yolla ola bilər:
      1. ORGANIZATION scope-lu rol (mərkəzi şöbələr: RİM, HR, imtahan mərkəzi,
         prorektor) — bütün təşkilatı əhatə edir, ``scope_unit`` boşdur;
      2. UNIT scope-lu rol (dekan, kafedra müdiri, koordinator) — ``scope_unit``
         ``unit``-in ÖZÜ və ya ƏCDADIDIR (materialized path prefiksi).

``unit`` ``None`` verilsə yalnız (1) qaytarılır — «mərkəzi şöbə» halı.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db.models import Q

from core.constants import RoleScopeType
from core.permissions import has_permission


def resolve_ancestor(unit, unit_type):
    """``unit``-dən başlayaraq yuxarı ``unit_type`` tipli ilk bölməni qaytarır.

    Bölmənin ÖZÜ həmin tipdədirsə özü qaytarılır. Tapılmasa ``None``.
    ``unit`` ``None``-dursa dərhal ``None`` (fail-closed: uydurma əcdad yoxdur).
    """
    if unit is None or not unit_type:
        return None
    current = unit
    seen = set()
    while current is not None:
        if current.pk in seen:  # pragma: no cover — pozulmuş ağac qoruyucusu
            return None
        seen.add(current.pk)
        if current.unit_type == unit_type:
            return current
        current = current.parent
    return None


def ancestor_unit_ids(unit) -> list:
    """``unit``-in materialized path-indən özü + bütün əcdad id-ləri.

    ``OrgUnit.path`` formatı ``"<root-id>/<child-id>/…/<self-id>"``-dir.
    Path boşdursa (nadir hal — köhnə sətir) yalnız öz id-si qaytarılır.
    """
    if unit is None:
        return []
    path = (getattr(unit, "path", "") or "").strip("/")
    if not path:
        return [str(unit.pk)]
    return [segment for segment in path.split("/") if segment]


def ancestor_paths(unit) -> list:
    """``unit``-in materialized-path PREFİKSLƏRİ, kök birinci, özü daxil.

    ``ancestor_unit_ids`` sadəcə əcdad ID siyahısı qaytarır; bu isə hər
    səviyyə üçün KUMULYATİV path prefiksini qaytarır (məs. path
    ``"a/b/c"`` üçün ``["a", "a/b", "a/b/c"]``) — `OrgUnit.path` üzərində
    ``path__in=...`` filtri üçün faydalıdır. Əlavə DB sorğusu YOXDUR.
    """
    if unit is None:
        return []
    path = (getattr(unit, "path", "") or "").strip("/")
    segments = [segment for segment in path.split("/") if segment] if path else [str(unit.pk)]
    prefixes = []
    accumulated: list = []
    for segment in segments:
        accumulated.append(segment)
        prefixes.append("/".join(accumulated))
    return prefixes


def members_covering_unit(organization, unit, *, role_names, permission=None):
    """``unit``-i əhatə edən, verilmiş adlı rolları daşıyan AKTİV üzvlüklər.

    Args:
        organization: Tenant.
        unit: ``OrgUnit`` və ya ``None`` (yalnız org-scope rollar).
        role_names: Rol adları (``Role.name``) — iterable.
        permission: Verilsə, əlavə olaraq rolun bu icazəni daşıması tələb
            olunur (``core.permissions.has_permission``, wildcard-safe).

    Returns:
        ``QuerySet[Membership]`` (``user``, ``role``, ``scope_unit`` select_related).
        Rol adları boşdursa BOŞ queryset (fail-closed).
    """
    from apps.organizations.models import Membership

    names = [name for name in (role_names or []) if name]
    if organization is None or not names:
        return Membership.objects.none()

    base = Membership.objects.filter(
        organization=organization,
        is_active=True,
        role__organization=organization,
        role__is_active=True,
        role__name__in=names,
    ).select_related("user", "role", "scope_unit")

    # Mərkəzi (ORGANIZATION scope) rol — bölmədən asılı olmayaraq əhatə edir.
    org_wide = Q(role__scope_type=RoleScopeType.ORGANIZATION)
    if unit is None:
        result = base.filter(org_wide)
    else:
        covering_ids = ancestor_unit_ids(unit)
        result = base.filter(org_wide | Q(scope_unit_id__in=covering_ids))

    if not permission:
        return result

    matching_ids = [m.pk for m in result if has_permission(list(m.role.permissions or []), permission)]
    return Membership.objects.filter(pk__in=matching_ids).select_related("user", "role", "scope_unit")


def coordinator_memberships_for_student(organization, student_user):
    """``student_user``-in AKTİV ``StudentAcademicRecord.group``-unu əhatə
    edən aktiv ``program_coordinator`` üzvlükləri.

    MODUL SƏRHƏDİ: ``organizations`` ``registrar``-ı statik idxal etmir
    (``scripts/module_deps_baseline.json`` — organizations yalnız ``audit``
    kənarına icazəlidir), ona görə model ``django.apps`` registry-si ilə
    həll olunur.
    """
    from apps.organizations.models import Membership

    if organization is None or student_user is None:
        return Membership.objects.none()

    StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")
    record = (
        StudentAcademicRecord.objects.filter(
            organization=organization,
            student=student_user,
            is_active=True,
            group__isnull=False,
        )
        .select_related("group")
        .order_by("-created_at")
        .first()
    )
    if record is None or record.group_id is None:
        return Membership.objects.none()

    return members_covering_unit(organization, record.group, role_names=["program_coordinator"])


def chair_head_memberships_for_unit(organization, unit):
    """``unit``-i (özü və ya kafedra əcdadı ilə) əhatə edən aktiv
    ``chair_head`` üzvlükləri."""
    return members_covering_unit(organization, unit, role_names=["chair_head"])


def dean_memberships_for_unit(organization, unit):
    """``unit``-i (özü və ya fakültə əcdadı ilə) əhatə edən aktiv
    ``dean`` üzvlükləri."""
    return members_covering_unit(organization, unit, role_names=["dean"])


def membership_covers_unit(membership, unit) -> bool:
    """Bir üzvlük verilmiş bölməni əhatə edirmi (path prefiksi ilə).

    ORGANIZATION scope-lu rol həmişə əhatə edir. ``unit`` ``None``-dursa yalnız
    org-scope üzvlük əhatə sayılır (unit-scope üzvlük üçün aidiyyət müəyyən
    deyil → fail-closed ``False``).
    """
    role = getattr(membership, "role", None)
    if role is not None and role.scope_type == RoleScopeType.ORGANIZATION:
        return True
    scope_unit = getattr(membership, "scope_unit", None)
    if scope_unit is None or unit is None:
        return False
    return str(scope_unit.pk) in set(ancestor_unit_ids(unit))


__all__ = [
    "ancestor_paths",
    "ancestor_unit_ids",
    "chair_head_memberships_for_unit",
    "coordinator_memberships_for_student",
    "dean_memberships_for_unit",
    "members_covering_unit",
    "membership_covers_unit",
    "resolve_ancestor",
]
