"""Kafedranın dərs materiallarına YALNIZ-OXU baxış — ``subject_folder.view_unit`` (sahib 2026-10-27).

Sahib: «tyutor və laborantlar … özlərinə aid olan kafedra sillabusa, dərs materialı varsa ona baxmaq olsun».

ƏHATƏ (``Membership.scope_unit`` alt-ağacı, fail-closed — əhatəsiz aktor heç nə görmür):

* qovluğun AKTİV təyinatının açılış qrupu alt-ağacdadır (fakültə / ixtisas kökü — tyutorun tələbələri), VƏ YA
* qovluğun sahibi (müəllim) alt-ağacdakı bölmənin aktiv üzvüdür (kafedra kökü — «kafedranın müəllimləri»;
  sillabusun ``author_chair_unit`` qaydasının güzgüsü), VƏ YA
* fənnin aparıcı kafedrası (``Subject.chair_unit``) alt-ağacdadır;
* org-wide əhatə (``*`` daşıyan rektor / RİM rəhbəri) — bütün təşkilat.

NƏ GÖRÜNÜR: yalnız QARALAMA OLMAYAN qovluqların DƏRC EDİLMİŞ, arxivlənməmiş materialları (tələbənin gördüyü
qayda). Tapşırıqlar, tələbə göndərişləri, oxşarlıq və müəllimin daxili qeydləri AÇILMIR; heç bir yazı əməli
bu açarla mümkün deyil — idarə ``access.can_manage_folder`` (sahib müəllim) qapısındadır.
"""

from __future__ import annotations

from django.db.models import Q

from ..constants import UNIT_VIEW_PERMISSION, FolderStatus
from ..models import SubjectFolder
from . import lookups

#: Baxışa açıq qovluq statusları (qaralama müəllimin yarımçıq işidir).
VISIBLE_STATUSES = (FolderStatus.ACTIVE, FolderStatus.ARCHIVED)


def _scope(user, organization):
    from apps.organizations.public import get_permission_scope

    return get_permission_scope(user, organization, UNIT_VIEW_PERMISSION)


def folders_q(user, organization) -> Q | None:
    """``SubjectFolder`` Q-su — aktorun əhatəsindəki qovluqlar; açar / əhatə yoxdursa ``None`` (fail-closed)."""
    if not lookups.is_authenticated(user) or organization is None:
        return None
    scope = _scope(user, organization)
    if not scope.has_structure_access:
        return None
    base = Q(organization=organization, status__in=VISIBLE_STATUSES)
    if scope.is_org_wide:
        return base
    units = lookups.org_unit_model().objects.filter(organization=organization).filter(scope.unit_subtree_q())
    unit_ids = units.values("pk")
    owners = (
        lookups.membership_model()
        .objects.filter(organization=organization, is_active=True, role__is_active=True, scope_unit__in=unit_ids)
        .values("user_id")
    )
    clause = (
        Q(assignments__is_active=True, assignments__offering__group__in=unit_ids)
        | Q(owner_id__in=owners)
        | Q(subject__chair_unit__in=unit_ids)
    )
    return base & clause


def has_unit_view(user, organization) -> bool:
    """Aktorun açarı + struktur əhatəsi varmı (menyu / boş vəziyyət üçün)."""
    return folders_q(user, organization) is not None


def visible_folders(user, organization):
    """Əhatədəki qovluqlar (təkrarsız) — açar / əhatə yoxdursa boş queryset."""
    clause = folders_q(user, organization)
    if clause is None:
        return SubjectFolder.objects.none()
    ids = SubjectFolder.objects.filter(clause).values("pk")
    return SubjectFolder.objects.filter(pk__in=ids)


def covers_folder(user, folder) -> bool:
    """Bu qovluq aktorun YALNIZ-OXU əhatəsindədirmi (fail-closed)."""
    if folder is None:
        return False
    clause = folders_q(user, folder.organization)
    if clause is None:
        return False
    return SubjectFolder.objects.filter(pk=folder.pk).filter(clause).exists()


def is_visible_item(item) -> bool:
    """Dərc edilmiş, arxivlənməmiş, mövzusu gizlədilməmiş material (tələbə görünüşü ilə eyni qayda)."""
    topic = getattr(item, "topic", None)
    if topic is not None and topic.is_archived:
        return False
    return bool(item.is_published) and not item.is_archived


def can_view_material(user, material) -> bool:
    """Endirmə qapısı: dərc edilmiş material + qovluq əhatədədir."""
    return is_visible_item(material) and covers_folder(user, material.folder)


def published_materials(folder):
    """Qovluğun görünən materialları — mövzu sırası ilə (bir sorğu)."""
    return (
        folder.materials.filter(is_published=True, is_archived=False)
        .filter(Q(topic__isnull=True) | Q(topic__is_archived=False))
        .select_related("topic")
        .order_by("topic__order", "topic__week_no", "order", "created_at")
    )


__all__ = [
    "VISIBLE_STATUSES",
    "can_view_material",
    "covers_folder",
    "folders_q",
    "has_unit_view",
    "is_visible_item",
    "published_materials",
    "visible_folders",
]
