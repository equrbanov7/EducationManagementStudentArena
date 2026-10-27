"""RİM istifadəçi kartı — siyahı sətri və detal paneli üçün serializasiya.

İKİLİ ROL DƏSTƏYİ
-----------------
`organizations.Membership.Meta.unique_together` = ``(user, organization, role,
scope_unit)`` — yəni bir istifadəçinin EYNİ təşkilatda bir neçə aktiv üzvlüyü
ola bilər. Praktikada bu, «həm müəllim, həm inzibati işçi» halıdır: məsələn
kafedra müdiri (`department_head`) həm də dərs deyir (`teacher`).

RİM bu üzvlüklərin HAMISINI göstərir və effektiv səviyyəni onların
MAKSİMUMU kimi hesablayır (`policy.target_level`) — yəni ikili rollu hesabı
idarə etmək üçün aktor onun ƏN YÜKSƏK rolundan da yuxarı olmalıdır.

Rol TƏYİNATI burada TƏKRAR YARADILMIR: mövcud «Rol təyinatı» axını
(`accounts:role_assignment`, `role.assign` icazəsi) kanonik yerdir; RİM kartı
ora dərin-link verir.
"""

from __future__ import annotations

from django.urls import reverse

from core import phone as phone_lib
from core.staff_position import visible_role_label

from .policy import RimActor, target_level
from .search import account_status


def _profile_of(user):
    return getattr(user, "profile", None)


def serialize_memberships(user, organization=None, *, scope=None):
    """İstifadəçinin AKTİV üzvlüklərini qaytarır (ikili rol burada görünür)."""
    prefetched = getattr(user, PREFETCH_ATTR, None)
    if prefetched is not None and scope is None:
        # PERF-1 F-02 (2026-10-17): axtarış səhifəsi üzvlükləri BİR sorğu ilə gətirir (`prefetch_memberships`).
        memberships = [m for m in prefetched if organization is None or m.organization_id == organization.pk]
        memberships.sort(key=lambda m: (-int(m.role.level or 0), m.role.name))
        return [_membership_row(membership) for membership in memberships]

    from apps.organizations.models import Membership

    queryset = Membership.objects.filter(user=user, is_active=True).select_related("role", "organization", "scope_unit")
    if organization is not None:
        queryset = queryset.filter(organization=organization)
    if scope is not None and not scope.is_org_wide:
        # Vahid-əhatəli aktor (dekan/kafedra müdiri) yalnız öz alt-ağacındakı
        # vahid üzvlüklərini görür; vahidsiz (təşkilat-səviyyəli) üzvlüklər —
        # «tələbə», «müəllim» — hədəf artıq kataloq əhatəsindədirsə görünməlidir,
        # əks halda şəxs kartı boş gəlir (QA 2026-09-05 P1-2).
        if not scope.is_unit_scoped:
            queryset = queryset.none()
        else:
            from django.db.models import Q

            from apps.organizations.models import OrgUnit

            subtree = OrgUnit.objects.filter(scope.unit_subtree_q())
            if organization is not None:
                subtree = subtree.filter(organization=organization)
            queryset = queryset.filter(Q(scope_unit__isnull=True) | Q(scope_unit__in=subtree.values("pk")))

    return [_membership_row(membership) for membership in queryset.order_by("-role__level", "role__name")]


def _membership_row(membership) -> dict:
    return {
        "id": str(membership.id),
        "role_name": membership.role.name,
        "role_label": visible_role_label(membership.role.name, membership.role.display_name),
        "role_level": int(membership.role.level or 0),
        "organization": membership.organization.name,
        "scope_unit": membership.scope_unit.name if membership.scope_unit_id else "",
        "title": membership.title or "",
        "is_primary": bool(membership.is_primary),
    }


#: `prefetch_memberships` nəticəsinin atributu (``serialize_memberships`` onu oxuyur).
PREFETCH_ATTR = "_rim_memberships"


def prefetch_memberships(users, organization=None) -> None:
    """Siyahı sətirləri üçün AKTİV üzvlükləri BİR sorğu ilə yükləyir (PERF-1 F-02: sətir başına sorğu idi)."""
    from django.db.models import Prefetch, prefetch_related_objects

    from apps.organizations.models import Membership

    queryset = Membership.objects.filter(is_active=True).select_related("role", "organization", "scope_unit")
    if organization is not None:
        queryset = queryset.filter(organization=organization)
    prefetch_related_objects(list(users), Prefetch("memberships", queryset=queryset, to_attr=PREFETCH_ATTR))


def serialize_row(user, actor: RimActor):
    """Axtarış siyahısının bir sətri — username AÇIQ göstərilir (əsas tələb)."""
    profile = _profile_of(user)
    status = account_status(user)
    # Redaktə formasında telefon (ölkə, yerli nömrə) cütü kimi göstərilir (``core.phone``, sahib 2026-10-25).
    phone_parts = phone_lib.split_phone(getattr(profile, "phone", "") or "")
    return {
        "id": user.pk,
        # Operator username-i BİLMİR — axtarışın bütün mənası onu tapmaqdır.
        "username": user.username,
        "full_name": profile.full_name_with_patronymic if profile is not None else user.get_full_name(),
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "patronymic": getattr(profile, "patronymic", "") or "",
        "email": user.email or "",
        "fin": getattr(profile, "fin", "") or "",
        "phone": getattr(profile, "phone", "") or "",
        "phone_country": phone_parts.region,
        "phone_national": phone_parts.national,
        "staff_position": getattr(profile, "staff_position", "") or "",
        "status": status,
        "status_label": {
            "active": "Aktiv",
            "blocked": "Bloklanıb",
            "deleted": "Silinib",
            "archived": "Arxiv (məzun/xaric)",
        }.get(status, "Naməlum"),
        "organization": getattr(getattr(profile, "organization", None), "name", "") or "",
        "department": getattr(profile, "department", "") or "",
        "block_reason": getattr(profile, "block_reason", "") or "",
        "deletion_reason": getattr(profile, "deletion_reason", "") or "",
        "password_change_required": bool(getattr(profile, "password_change_required", False)),
        "email_verified": bool(getattr(profile, "email_verified", False)),
        "last_login": user.last_login.isoformat() if user.last_login else "",
        "roles": serialize_memberships(user, actor.organization if not actor.is_superadmin else None),
    }


def serialize_detail(user, actor: RimActor):
    """Detal paneli — sətir + aktorun bu hədəf üçün icazə xəritəsi."""
    from .policy import (
        PERM_BLOCK,
        PERM_CREDENTIALS,
        PERM_EDIT,
        PERM_SOFT_DELETE,
        RimAccessError,
        assert_can_manage,
    )

    row = serialize_row(user, actor)

    manageable = True
    block_reason_code = ""
    try:
        assert_can_manage(actor, user)
    except RimAccessError as exc:
        manageable = False
        block_reason_code = exc.reason_code

    status = row["status"]
    row["effective_level"] = target_level(user, actor.organization)
    row["manageable"] = manageable
    row["not_manageable_reason"] = block_reason_code
    row["actions"] = {
        "set_password": manageable and actor.has(PERM_CREDENTIALS) and status != "deleted",
        "block": manageable and actor.has(PERM_BLOCK) and status == "active",
        "unblock": manageable and actor.has(PERM_BLOCK) and status == "blocked",
        "soft_delete": manageable and actor.has(PERM_SOFT_DELETE) and status in {"active", "blocked"},
        "restore": manageable and actor.has(PERM_SOFT_DELETE) and status == "deleted",
        "edit": manageable and actor.has(PERM_EDIT) and status != "deleted",
    }
    # Sahib 2026-10-27: səhv arxivlənmiş CARİ tələbə — «Arxivdən çıxar» (`member.edit`, services/archive_restore.py).
    row["archive_restore"] = None
    if status == "archived":
        from .archive import archive_restore_card

        row["archive_restore"] = archive_restore_card(user, actor)
    row["actions"]["archive_restore"] = bool(
        manageable and row["archive_restore"] and row["archive_restore"]["can_restore"]
    )
    # Rol təyinatı RİM-də TƏKRAR YARADILMIR — kanonik bölməyə dərin link.
    row["role_assignment_url"] = f"{reverse('accounts:profile')}?section=role-assignment"
    return row


__all__ = ["PREFETCH_ATTR", "prefetch_memberships", "serialize_detail", "serialize_memberships", "serialize_row"]
