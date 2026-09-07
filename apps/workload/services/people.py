"""Kafedranın müəllim hovuzu — bölgü seçicisinin YEGANƏ mənbəyi.

``apps/organizations``-da «bu bölməni kim tutur» üçün hazır helper YOXDUR
(bax SCOUT §12), ona görə ORM burada, öz modulumuzda qalır.

DEQRADASİYA QAYDASI (real datadan doğur)
----------------------------------------
Müəllim rolu ``COURSE`` scope-ludur və köçürülmüş tenantlarda ``scope_unit``
ÇOX VAXT BOŞDUR. Ona görə hovuz iki dalğada qurulur:

1. **Kafedra müəllimləri** — ``scope_unit`` kafedranın alt-ağacındadır
   (dəqiq bağlantı, ``is_chair_member=True``);
2. **Bağlanmamış müəllimlər** — ``scope_unit`` NULL (universitet hovuzu,
   ``is_chair_member=False``). Bunlar YALNIZ 1-ci dalğa boş olanda və ya
   axtarışla açıq istənəndə göstərilir; təyinat zamanı da qəbul edilir, çünki
   əks halda köçürülmüş bazada heç bir bölgü mümkün olmurdu.

Başqa kafedraya BAĞLI (``scope_unit`` var, amma bu kafedranın altında deyil)
müəllim hovuzda YOXDUR və təyin edilə BİLMƏZ.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db.models import Q

from ..constants import TEACHER_ROLE_NAMES
from .scoping import WorkloadDenied


def _membership_model():
    return django_apps.get_model("organizations", "Membership")


def _org_unit_model():
    return django_apps.get_model("organizations", "OrgUnit")


def _chair_subtree_q(chair) -> Q:
    """``scope_unit`` kafedranın özü və ya onun törəməsidir."""
    return Q(scope_unit_id=chair.pk) | Q(scope_unit__path__startswith=f"{chair.path}/")


def chair_teacher_memberships(organization, chair, *, include_unscoped: bool = True):
    """Kafedranın müəllim üzvlükləri (``select_related('user')``)."""
    Membership = _membership_model()
    base = Membership.objects.filter(
        organization=organization,
        is_active=True,
        role__is_active=True,
        role__name__in=TEACHER_ROLE_NAMES,
    ).select_related("user", "role", "scope_unit")
    scoped = base.filter(_chair_subtree_q(chair))
    if not include_unscoped:
        return scoped
    return base.filter(_chair_subtree_q(chair) | Q(scope_unit__isnull=True))


def teacher_pool(organization, chair, *, search: str = "", limit: int = 50) -> list[dict]:
    """Bölgü modalının müəllim siyahısı — ad, istifadəçi adı, bağlantı bayrağı."""
    memberships = chair_teacher_memberships(organization, chair)
    if search:
        memberships = memberships.filter(
            Q(user__username__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
        )
    seen: dict = {}
    for membership in memberships[: max(limit * 3, limit)]:
        user = membership.user
        if user is None or user.pk in seen:
            continue
        is_chair_member = membership.scope_unit_id is not None
        seen[user.pk] = {
            "id": str(user.pk),
            "username": user.username,
            "full_name": (user.get_full_name() or user.username).strip(),
            "role": membership.role.name if membership.role else "",
            "is_chair_member": is_chair_member,
        }
    rows = list(seen.values())
    rows.sort(key=lambda item: (not item["is_chair_member"], item["full_name"].lower()))
    return rows[:limit]


def is_assignable_teacher(organization, chair, teacher) -> bool:
    """Müəllim bu kafedraya təyin oluna bilərmi (fail-closed)."""
    if teacher is None:
        return True  # Vakant
    return chair_teacher_memberships(organization, chair).filter(user=teacher).exists()


def ensure_assignable_teacher(organization, chair, teacher) -> None:
    if not is_assignable_teacher(organization, chair, teacher):
        raise WorkloadDenied(
            "workload.teacher_not_in_chair",
            "Seçilmiş müəllimin bu kafedrada aktiv müəllim üzvlüyü yoxdur.",
        )


def parse_uuid(raw):
    """Qeyri-UUID id `filter(pk=...)`-də ValidationError → 500 verirdi (QA 2026-09-05 WORKLOAD-SCHEDULE-01)."""
    import uuid

    try:
        return uuid.UUID(str(raw or "").strip())
    except ValueError:
        return None


def resolve_chair(organization, chair_id):
    """Kafedra ``OrgUnit``-i — tapılmasa ``WorkloadDenied``."""
    from core.constants import OrgUnitType

    chair_id = parse_uuid(chair_id)
    if chair_id is None:
        raise WorkloadDenied("workload.chair_not_found", "Kafedra tapılmadı.")
    unit = (
        _org_unit_model()
        .objects.filter(
            organization=organization,
            pk=chair_id,
            is_active=True,
            unit_type__in=(OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT),
        )
        .first()
    )
    if unit is None:
        raise WorkloadDenied("workload.chair_not_found", "Kafedra tapılmadı.")
    return unit


__all__ = [
    "chair_teacher_memberships",
    "ensure_assignable_teacher",
    "is_assignable_teacher",
    "resolve_chair",
    "teacher_pool",
]
