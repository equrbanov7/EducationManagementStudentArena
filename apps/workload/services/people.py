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
müəllim əsas hovuzda YOXDUR. Sahib 2026-10-25: «ştat olaraq bir kafedradadır, saat hesabı olaraq başqa
kafedrada fənn götürüb» — belə müəllim seçicidə AYRICA («kənar», ştat kafedrası yazılı) göstərilir
(``include_outside``) və təyin olunanda yükü verən kafedrada ƏLAVƏ (``is_primary=False``) müəllim üzvlüyü
alır (:func:`join_chair_as_teacher` — 2026-10-12 idxal qaydası). ŞTAT kafedrası dəyişmir:
:func:`home_chair_rank` əlavə üzvlüyü heç vaxt ştat kafedrası seçmir.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db.models import Q

from core.constants import OrgUnitType
from core.search_text import tolerant_q

from ..constants import TEACHER_ROLE_NAMES
from .scoping import WorkloadDenied

CHAIR_TYPES = (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)
#: Seçicidəki kənar müəllim siyahısının tavanı (bütün təşkilat ~10³ müəllimdir).
OUTSIDE_POOL_LIMIT = 1500
_LATEST = "9999"


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


def _kafedra_types(organization) -> tuple:
    """Təşkilatda kafedra sayılan tiplər — inzibati şöbə (``department``) ``chair`` olan təşkilatda kafedra deyil."""
    from apps.organizations.public import kafedra_unit_types

    return kafedra_unit_types(organization)


def home_chair_rank(row: dict, chair_types=CHAIR_TYPES) -> tuple:
    """Müəllimin ŞTAT (əsas) kafedrasını seçən sıralama açarı — kiçik açar üstündür.

    ``row`` — ``Membership.values(...)`` sətri (``scope_unit__unit_type``, ``is_primary``, ``role__name``,
    ``role__level``, ``created_at``). Kənar kafedranın yükü üçün yaradılan üzvlük (:func:`join_chair_as_teacher`)
    ``is_primary=False`` və ştat üzvlüyündən YENİDİR — ona görə: kafedra tipli bölmə → əsas üzvlük → müəllim
    rolu → yüksək səviyyə → köhnə. Əvvəl «müəllim rolu» birinci idi: kafedra müdiri (əsas ``chair_head``) başqa
    kafedrada saathesabı dərs alanda ştatı həmin kafedraya «köçürdü» (sahib 2026-10-25)."""
    created = row.get("created_at")
    return (
        row.get("scope_unit__unit_type") not in chair_types,
        not row.get("is_primary"),
        row.get("role__name") not in TEACHER_ROLE_NAMES,
        -(row.get("role__level") or 0),
        created.isoformat() if created is not None else _LATEST,
    )


def home_chairs(organization, user_ids) -> dict:
    """İstifadəçi id → ``{"id", "name"}`` — ştat kafedrası (:func:`home_chair_rank`); kafedrasız → yoxdur. 1 sorğu."""
    ids = [pk for pk in user_ids if pk]
    if not ids:
        return {}
    best: dict = {}
    rows = (
        _membership_model()
        .objects.filter(
            organization=organization,
            user_id__in=ids,
            is_active=True,
            role__is_active=True,
            scope_unit__unit_type__in=_kafedra_types(organization),
        )
        .values(
            "user_id",
            "scope_unit_id",
            "scope_unit__name",
            "scope_unit__unit_type",
            "is_primary",
            "role__name",
            "role__level",
            "created_at",
        )
        .order_by()
    )
    for row in rows:
        current = best.get(row["user_id"])
        if current is None or home_chair_rank(row) < home_chair_rank(current):
            best[row["user_id"]] = row
    return {
        user_id: {"id": str(row["scope_unit_id"]), "name": row["scope_unit__name"] or ""}
        for user_id, row in best.items()
    }


def teacher_pool(
    organization, chair, *, search: str = "", limit: int | None = 50, include_outside: bool = False
) -> list[dict]:
    """Bölgü modalının müəllim siyahısı — ad, istifadəçi adı, bağlantı bayrağı.

    ``include_outside`` — sonda başqa kafedraların müəllimləri (``is_outside``, ``home_chair`` — ştat kafedrası).
    ``limit=None`` — lokal axtarışlı modal üçün kafedranın tam hovuzu; səhifələnən seçici öz limitini verir.
    """
    memberships = chair_teacher_memberships(organization, chair)
    search_q = tolerant_q(search, ("user__username", "user__first_name", "user__last_name"))
    if search_q is not None:
        memberships = memberships.filter(search_q)
    seen: dict = {}
    candidates = memberships if limit is None else memberships[: max(limit * 3, limit)]
    for membership in candidates:
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
            "is_outside": False,
            "home_chair": "",
        }
    rows = list(seen.values())
    rows.sort(key=lambda item: (not item["is_chair_member"], item["full_name"].lower()))
    rows = rows[:limit]
    if include_outside:
        rows += outside_teachers(organization, chair, exclude_ids={item["id"] for item in rows}, search=search)
    return rows


def _org_teacher_memberships(organization):
    return _membership_model().objects.filter(
        organization=organization,
        is_active=True,
        role__is_active=True,
        role__name__in=TEACHER_ROLE_NAMES,
        user__is_active=True,
    )


def outside_teachers(organization, chair, *, exclude_ids=(), search: str = "", limit: int = OUTSIDE_POOL_LIMIT):
    """Başqa kafedraya bağlı aktiv müəllimlər (bu kafedrada üzvlüyü olmayan) — ştat kafedrası ilə."""
    in_chair = chair_teacher_memberships(organization, chair, include_unscoped=False).values("user_id")
    memberships = (
        _org_teacher_memberships(organization)
        .filter(scope_unit__isnull=False)
        .exclude(_chair_subtree_q(chair))
        .exclude(user_id__in=in_chair)
        .select_related("user")
    )
    search_q = tolerant_q(search, ("user__username", "user__first_name", "user__last_name"))
    if search_q is not None:
        memberships = memberships.filter(search_q)
    excluded = {str(pk) for pk in exclude_ids}
    users = {}
    for membership in memberships.order_by("user__last_name", "user__first_name")[: limit * 2]:
        if membership.user_id not in users and str(membership.user_id) not in excluded:
            users[membership.user_id] = membership.user
    homes = home_chairs(organization, list(users))
    rows = [
        {
            "id": str(user.pk),
            "username": user.username,
            "full_name": (user.get_full_name() or user.username).strip(),
            "role": "teacher",
            "is_chair_member": False,
            "is_outside": True,
            "home_chair": (homes.get(user.pk) or {}).get("name", ""),
        }
        for user in users.values()
    ]
    rows.sort(key=lambda item: item["full_name"].lower())
    return rows[:limit]


def is_assignable_teacher(organization, chair, teacher) -> bool:
    """Müəllim bu kafedraya təyin oluna bilərmi (fail-closed)."""
    if teacher is None:
        return True  # Vakant
    return chair_teacher_memberships(organization, chair).filter(user=teacher).exists()


def is_outside_teacher(organization, chair, teacher) -> bool:
    """Müəllim başqa kafedranın aktiv müəllimidir (bu kafedrada üzvlüyü yoxdur) — kənar təyinat namizədi."""
    if teacher is None or is_assignable_teacher(organization, chair, teacher):
        return False
    return _org_teacher_memberships(organization).filter(user=teacher, scope_unit__isnull=False).exists()


def ensure_assignable_teacher(organization, chair, teacher, *, actor_user=None) -> None:
    """Təyinat qapısı. ``actor_user`` verilibsə başqa kafedranın müəllimi bu kafedrada ƏLAVƏ üzvlük alır
    (sahib 2026-10-25 «saat hesabı başqa kafedrada») — ştat kafedrası dəyişmir; tələbə / əməkdaş — rədd."""
    if actor_user is not None and is_outside_teacher(organization, chair, teacher):
        join_chair_as_teacher(
            organization=organization,
            user=teacher,
            chair=chair,
            actor_user=actor_user,
            reason="workload.assign: başqa kafedranın müəllimi bu kafedranın yükünü alır (saathesabı)",
        )
        return
    if not is_assignable_teacher(organization, chair, teacher):
        raise WorkloadDenied(
            "workload.teacher_not_in_chair",
            "Seçilmiş müəllimin bu kafedrada aktiv müəllim üzvlüyü yoxdur.",
        )


def join_chair_as_teacher(*, organization, user, chair, actor_user, reason: str) -> bool:
    """Başqa kafedranın (və ya bağlanmamış) müəllimi bu kafedranın yükünü alır → kafedrada ƏLAVƏ
    (``is_primary=False``) ``teacher`` üzvlüyü; öz kafedrası dəyişmir, audit jurnalına yazılır.

    Yük servisi müəllimi yalnız kafedra üzvü olanda təyin edir (``workload.teacher_not_in_chair``) —
    sahib 2026-10-12 «hamısını bağla» qərarı. Qaytarır: üzvlük yaradıldı/aktivləşdirildimi."""
    from core.audit import log_action
    from core.constants import AuditAction

    Role = django_apps.get_model("organizations", "Role")
    role = Role.objects.get(organization=organization, name="teacher")
    membership, created = _membership_model().objects.get_or_create(
        organization=organization,
        user=user,
        role=role,
        scope_unit=chair,
        defaults={"is_active": True, "is_primary": False, "assigned_by": actor_user},
    )
    if not created and not membership.is_active:
        membership.is_active = True
        membership.save(update_fields=["is_active", "updated_at"])
        created = True
    if created:
        log_action(
            AuditAction.CREATE,
            user=actor_user,
            organization=organization,
            obj=membership,
            reason=reason,
            new_values={"user": user.username, "chair": chair.name, "role": "teacher"},
        )
    return created


def parse_uuid(raw):
    """Qeyri-UUID id `filter(pk=...)`-də ValidationError → 500 verirdi (QA 2026-09-05 WORKLOAD-SCHEDULE-01)."""
    import uuid

    try:
        return uuid.UUID(str(raw or "").strip())
    except ValueError:
        return None


def resolve_chair(organization, chair_id):
    """Kafedra ``OrgUnit``-i — tapılmasa ``WorkloadDenied``."""
    chair_id = parse_uuid(chair_id)
    if chair_id is None:
        raise WorkloadDenied("workload.chair_not_found", "Kafedra tapılmadı.")
    unit = (
        _org_unit_model()
        .objects.filter(
            organization=organization,
            pk=chair_id,
            is_active=True,
            unit_type__in=_kafedra_types(organization),
        )
        .first()
    )
    if unit is None:
        raise WorkloadDenied("workload.chair_not_found", "Kafedra tapılmadı.")
    return unit


__all__ = [
    "CHAIR_TYPES",
    "chair_teacher_memberships",
    "ensure_assignable_teacher",
    "home_chair_rank",
    "home_chairs",
    "is_assignable_teacher",
    "is_outside_teacher",
    "join_chair_as_teacher",
    "outside_teachers",
    "resolve_chair",
    "teacher_pool",
]
