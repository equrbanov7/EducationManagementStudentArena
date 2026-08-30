"""Kataloq əməlləri — hesabı dayandır/bərpa et, müəllim statusunu ver/çıxar.

**MEXANİZM TƏKRAR YARADILMIR.** Hesabın bloklanması/açılması mövcud RİM
servisidir (`apps.accounts.services.rim.lifecycle`) — burada yalnız kataloqa xas
İKİ ƏLAVƏ QAT var:

1. **Scope qapısı.** RİM qatı «kim kimi idarə edə bilər»i bilir (rütbə, tenant,
   öz hesabı, superadmin, sahib), amma STRUKTUR scope-unu BİLMİR. Dekanın öz
   fakültəsindən kənar hesabı dayandıra bilməməsi məhz burada təmin olunur:
   hədəf aktorun GÖRÜNƏN siyahısında olmalıdır.
2. **İcazə tərcüməsi.** Kataloqun açarı ``people.manage_status``-dur; RİM qatı
   isə ``user.block`` gözləyir. Aktor kataloq açarını daşıyırsa, RİM aktoruna
   YALNIZ ``user.block`` əlavə olunur — ``user.soft_delete`` QƏSDƏN yox: sahib
   bu səthdə «hesabı dayandırmaq» istəyib, silmək yox. Silmə RİM mərkəzində
   öz ayrıca açarı ilə qalır.

Hər əməl audit jurnalına düşür və dağıdıcı əməllər üçün səbəb MƏCBURİDİR.
"""

from __future__ import annotations

from dataclasses import replace

from django.contrib.auth import get_user_model
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from ..rim import lifecycle as rim_lifecycle
from ..rim import policy as rim_policy
from ..rim.policy import RimAccessError
from .constants import DEFAULT_TEACHER_ROLE_NAME, TEACHER_ROLE_NAMES
from .permissions import PERM_MANAGE_STATUS, PERM_MANAGE_TEACHER_ROLE, PERM_VIEW_STUDENTS, PERM_VIEW_TEACHERS

User = get_user_model()

MIN_REASON_LENGTH = rim_lifecycle.MIN_REASON_LENGTH
MAX_REASON_LENGTH = rim_lifecycle.MAX_REASON_LENGTH

_AUDIT_RESOURCE = "accounts.people"


def _require(actor, permission):
    if not actor.has(permission):
        raise RimAccessError("permission_denied", "Bu əməliyyat üçün icazəniz yoxdur.")


def load_target(actor, user_id):
    """Hədəf hesabı yükləyir (profil ilə birlikdə). Tapılmasa 404."""
    if not user_id:
        raise RimAccessError("target_not_found", "İstifadəçi tapılmadı.", status=404)
    target = User.objects.select_related("profile").filter(pk=user_id).first()
    if target is None:
        raise RimAccessError("target_not_found", "İstifadəçi tapılmadı.", status=404)
    return target


def assert_in_catalog_scope(actor, target, *, request=None) -> str:
    """Hədəf aktorun GÖRÜNƏN kataloqunda olmalıdır — yoxsa 404.

    404 (403 deyil) qəsdəndir: scope-dan kənar hesabın MÖVCUDLUĞU da məlumatdır.
    Qaytarır: hədəfin hansı kataloqda tapıldığı (``teacher`` / ``student``).
    """
    from .students import visible_students_qs
    from .teachers import visible_teachers_qs

    target_id = target.pk
    if actor.has(PERM_VIEW_TEACHERS) and visible_teachers_qs(actor, request=request).filter(pk=target_id).exists():
        return "teacher"
    if actor.has(PERM_VIEW_STUDENTS) and visible_students_qs(actor, request=request).filter(pk=target_id).exists():
        return "student"
    raise RimAccessError(
        "target_outside_scope",
        "Bu hesab sizin görünüş sahənizdə deyil.",
        status=404,
    )


def _rim_actor(actor, request, *, extra_permissions):
    """Kataloq aktorunu RİM aktoruna çevirir (icazə tərcüməsi ilə).

    ``request`` verilməyibsə (servis səviyyəli çağırış/test) RİM aktoru kataloq
    aktorundan birbaşa qurulur — davranış eynidir, sadəcə sorğu konteksti yoxdur.
    """
    if request is not None:
        rim = rim_policy.resolve_actor(request)
    else:
        rim = rim_policy.RimActor(
            user=actor.user,
            organization=actor.organization,
            level=rim_policy.SUPERADMIN_LEVEL if actor.is_superadmin else _actor_level(actor),
            is_superadmin=actor.is_superadmin,
            permissions=set(actor.permissions),
        )
    missing = {perm for perm in extra_permissions if not rim.has(perm)}
    if missing:
        rim = replace(rim, permissions=set(rim.permissions) | missing)
    return rim


def _actor_level(actor) -> int:
    """Aktorun təşkilatdakı maksimum rol səviyyəsi (request-siz yol üçün)."""
    from django.db.models import Max

    from apps.organizations.models import Membership

    if actor.organization is None:
        return 0
    aggregate = Membership.objects.filter(
        user=actor.user, organization=actor.organization, is_active=True, role__is_active=True
    ).aggregate(top=Max("role__level"))
    level = int(aggregate.get("top") or 0)
    if getattr(actor.organization, "owner_id", None) == getattr(actor.user, "pk", None):
        from core.roles import ProfileRole

        level = max(level, ProfileRole.LEVELS.get(ProfileRole.ORG_OWNER, 90))
    return level


def set_account_status(actor, target, *, active: bool, reason: str, request=None) -> dict:
    """Hesabı dayandırır (``active=False``) və ya bərpa edir (``active=True``)."""
    _require(actor, PERM_MANAGE_STATUS)
    catalog = assert_in_catalog_scope(actor, target, request=request)
    rim = _rim_actor(actor, request, extra_permissions={rim_policy.PERM_BLOCK})

    if active:
        applied_reason = rim_lifecycle.unblock_user(rim, target, reason=reason, request=request)
        action_name = "people.account_unblocked"
    else:
        applied_reason = rim_lifecycle.block_user(rim, target, reason=reason, request=request)
        action_name = "people.account_blocked"

    log_action(
        AuditAction.UPDATE,
        user=actor.user,
        organization=actor.organization,
        obj=target,
        reason=applied_reason,
        request=request,
        resource_type=_AUDIT_RESOURCE,
        resource_id=str(target.pk),
        resource_repr=target.get_full_name() or target.username,
        changes={"action": action_name, "catalog": catalog, "is_active": active},
    )
    return {"status": "active" if active else "blocked", "reason": applied_reason}


def _teacher_role(organization):
    from apps.organizations.models import Role

    role = (
        Role.objects.filter(organization=organization, name=DEFAULT_TEACHER_ROLE_NAME, is_active=True)
        .order_by("-level")
        .first()
    )
    if role is None:
        raise RimAccessError(
            "teacher_role_missing",
            "Təşkilatda aktiv «müəllim» rolu tapılmadı — əvvəlcə rolu yaradın.",
            status=409,
        )
    return role


def _resolve_grant_unit(actor, organization, unit_id, *, request=None):
    """Müəllim təyinatının kafedrası — aktorun scope-u daxilində olmalıdır.

    Unit-scope-lu aktor (dekan/kafedra müdiri) unit GÖSTƏRMƏLİDİR: əks halda
    təyinat scope_unit-siz qalar və həmin müəllim heç kimin unit siyahısında
    görünməzdi (məlumat itkisi + gələcəkdə fail-closed görünməzlik).
    """
    from apps.organizations.models import OrgUnit

    scope = actor.scope_for(PERM_MANAGE_TEACHER_ROLE, request=request)
    if not unit_id:
        if scope.is_org_wide:
            return None
        raise RimAccessError(
            "unit_required",
            "Müəllim təyinatı üçün kafedra seçilməlidir.",
            status=400,
        )
    unit = (
        OrgUnit.objects.filter(scope.unit_subtree_q())
        .filter(organization=organization, pk=unit_id, is_active=True)
        .first()
    )
    if unit is None:
        raise RimAccessError(
            "unit_outside_scope",
            "Seçilmiş bölmə sizin görünüş sahənizdə deyil.",
            status=404,
        )
    return unit


@transaction.atomic
def set_teacher_role(actor, target, *, grant: bool, reason: str, unit_id=None, request=None) -> dict:
    """Müəllim statusunu verir və ya çıxarır (``Membership`` üzərindən).

    VERMƏ: kanonik ``teacher`` rolu ilə aktiv üzvlük yaradılır/aktivləşdirilir.
    ÇIXARMA: aktorun scope-undakı BÜTÜN müəllim üzvlükləri deaktiv edilir —
    üzvlük SƏTİRLƏRİ silinmir (tarixi jurnal/qiymət izi qorunur).
    """
    _require(actor, PERM_MANAGE_TEACHER_ROLE)
    organization = actor.organization
    if organization is None:
        raise RimAccessError("no_organization_context", "Aktiv təşkilat konteksti yoxdur.")

    reason = rim_lifecycle.normalize_reason(reason, required=not grant)

    # Rütbə/tenant/öz-hesabı qaydaları RİM qatından — təkrar yazılmır.
    rim = _rim_actor(actor, request, extra_permissions=set())
    rim_policy.assert_can_manage(rim, target)

    from apps.organizations.models import Membership

    if grant:
        unit = _resolve_grant_unit(actor, organization, unit_id, request=request)
        role = _teacher_role(organization)
        membership, created = Membership.objects.get_or_create(
            organization=organization,
            user=target,
            role=role,
            defaults={"is_active": True, "scope_unit": unit, "assigned_by": actor.user},
        )
        if not created:
            membership.is_active = True
            if unit is not None:
                membership.scope_unit = unit
            membership.save(update_fields=["is_active", "scope_unit", "updated_at"])
        changed = 1
        action_name = "people.teacher_role_granted"
    else:
        # ÇIXARMA scope-ludur: dekan yalnız öz alt-ağacındakı təyinatı söndürür.
        from apps.organizations.scoping import scope_memberships_by_unit

        scope = actor.scope_for(PERM_MANAGE_TEACHER_ROLE, request=request)
        memberships = Membership.objects.filter(
            organization=organization,
            user=target,
            is_active=True,
            role__name__in=TEACHER_ROLE_NAMES,
        )
        memberships = scope_memberships_by_unit(memberships, scope, organization=organization)
        changed = memberships.update(is_active=False)
        if not changed:
            raise RimAccessError(
                "no_teacher_membership",
                "Bu hesabın sizin sahənizdə aktiv müəllim təyinatı yoxdur.",
                status=409,
            )
        action_name = "people.teacher_role_revoked"

    log_action(
        AuditAction.UPDATE,
        user=actor.user,
        organization=organization,
        obj=target,
        reason=reason,
        request=request,
        resource_type=_AUDIT_RESOURCE,
        resource_id=str(target.pk),
        resource_repr=target.get_full_name() or target.username,
        changes={"action": action_name, "memberships_changed": changed, "unit_id": str(unit_id or "")},
    )
    return {"is_teacher": grant, "memberships_changed": changed, "reason": reason}


__all__ = [
    "MAX_REASON_LENGTH",
    "MIN_REASON_LENGTH",
    "RimAccessError",
    "assert_in_catalog_scope",
    "load_target",
    "set_account_status",
    "set_teacher_role",
]
