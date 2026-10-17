"""«Heyət idarəetməsi» (``student-organization-management``) bölməsini kim açır — sahib 2026-10-17.

Bölmə tələbə qoşulma müraciətlərini (təsdiq / rədd), dəvətləri və üzv çıxarılmasını aparır. QA-2 F-03-ün davamı:
HR (heyət idxalı) tələbə tərəfini görmür → bölmə RİM-ə və tələbə tərəfi AÇARI daşıyan rollara keçdi. Rol ADI
yoxlanmır, yalnız açar (``apps.organizations.student_privacy`` + müəllimə delegasiya ``member.student_manage``) —
«hər rol öz səlahiyyəti qədər»: icazə redaktorunda HR-a tələbə açarı verilsə, bölmə də qayıdır.

«Rol təyin et»dəki hələ üzv olmayan müraciətçilərin e-poçtu HR-a görünür qalır (onlar hələ tələbə deyil).
"""

from __future__ import annotations

from core.permissions import has_permission

from .rbac import _collect_actor_permissions


def holds_student_side_key(user, organization, *, request=None) -> bool:
    """Superadmin / təşkilat sahibi və ya aktiv təşkilatda tələbə tərəfi açarı (``member.student_manage`` daxil)."""
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True
    if organization is None:
        return False
    if getattr(organization, "owner_id", None) == getattr(user, "pk", None):
        return True
    from apps.organizations.public import holds_student_key

    permissions = list(_collect_actor_permissions(user, organization, request=request)[0])
    return holds_student_key(permissions) or has_permission(permissions, "member.student_manage")


__all__ = ["holds_student_side_key"]
