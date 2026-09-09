"""«Rolları idarə et» — TƏŞKİLAT rolunun verilməsi / geri alınması.

NİYƏ AYRICA AXIN?
-----------------
Köhnə checkbox səthi yalnız `ProfileRole` enum-undakı 12 adı tanıyırdı; təşkilat
kataloqundakı `program_coordinator`, `dean`, `tutor`, `lab_assistant` kimi
rollar nə görünürdü, nə də verilə bilirdi (sahib şikayəti 2026-09-09). Bundan
əlavə həmin səth naməlum rolları `member`-ə xəritələyib SƏSSİZCƏ söndürürdü.

Bu axın `organizations.Role` kataloqu ilə işləyir: bir şəxsə eyni anda bir neçə
üzvlük (məs. «Proqram koordinatoru» + «Müəllim») verilə bilir və hər biri ayrıca
geri alınır. `Membership` modeli bunu onsuz da dəstəkləyir
(`user × organization × role × scope_unit` unikal).

QAPILAR (heç biri zəiflədilmir — hamısı «Rol təyin et» axını ilə eynidir):
  * `role.assign` / `org.manage_members` + struktur əhatəsi (`_gates`);
  * aktor öz səviyyəsinə bərabər/yuxarı ROLU verə bilməz;
  * aktor öz səviyyəsinə bərabər/yuxarı ŞƏXSƏ toxuna bilməz;
  * owner rolu → `org.owner.assign`; admin rolu → `org.admin.assign`
    (və ya `user.grant_privileged`);
  * vahid-əhatəli aktor təşkilat-əhatəli rol verə bilməz;
  * son owner və şəxsin son üzvlüyü geri alına bilməz.
Hər əməl audit jurnalına yazılır.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import redirect
from django.utils.translation import pgettext

from apps.organizations.models import Membership, OrgUnit, Role

from ...services.role_catalog import (
    effective_level,
    is_admin_role,
    is_org_wide_role,
    is_owner_role,
    membership_queryset,
    role_label,
    sync_profile_primary_role,
)
from .._helpers.rbac import _collect_actor_permissions
from ._gates import actor_is_unit_scoped, manage_roles_gate_error

User = get_user_model()

_CTX = "accounts.manage_roles.message"

#: Bu modulun tanıdığı POST əməlləri.
ORG_ROLE_ACTIONS = frozenset({"grant_role", "revoke_role"})


def _deny(request, next_url, message):
    messages.error(request, message)
    return redirect(next_url)


def _actor_permission_list(request, organization):
    actor_permissions, _grantable = _collect_actor_permissions(request.user, organization)
    return list(actor_permissions)


def _can_assign_owner_roles(request, organization, *, is_superadmin) -> bool:
    from core.permissions import has_permission

    return is_superadmin or has_permission(_actor_permission_list(request, organization), "org.owner.assign")


def _can_assign_admin_roles(request, organization, *, is_superadmin) -> bool:
    from core.permissions import has_permission

    if _can_assign_owner_roles(request, organization, is_superadmin=is_superadmin):
        return True
    permission_list = _actor_permission_list(request, organization)
    return has_permission(permission_list, "org.admin.assign") or has_permission(
        permission_list, "user.grant_privileged"
    )


def _owner_membership_exists(organization, *, exclude_id=None) -> bool:
    queryset = membership_queryset(organization)
    if exclude_id is not None:
        queryset = queryset.exclude(id=exclude_id)
    return any(is_owner_role(membership.role) for membership in queryset)


def _resolve_target_user(request):
    user_id = (request.POST.get("user_id") or "").strip()
    if not user_id:
        return None
    return User.objects.filter(pk=user_id).first()


def _resolve_scope_unit(organization, raw_scope):
    raw_scope = (raw_scope or "").strip()
    if not raw_scope:
        return None
    return OrgUnit.objects.filter(organization=organization, pk=raw_scope).first()


def _guard(request, *, organization, target_user, target_role, is_superadmin, actor_level):
    """Ortaq qapı zənciri — `None` = keç, əks halda mesaj."""
    gate_error = manage_roles_gate_error(request, organization, target_user, is_superadmin=is_superadmin)
    if gate_error is not None:
        return gate_error

    is_self = target_user.pk == request.user.pk
    owner_of_org = getattr(organization, "owner_id", None) == request.user.id
    if is_self and not (is_superadmin or owner_of_org):
        return pgettext(_CTX, "Öz rollarınızı dəyişmək üçün təşkilat sahibi və ya superadmin olmalısınız.")

    # Səviyyə müqayisəsi EFFEKTİV səviyyə ilədir — `actor_level` də
    # `_highest_role_level()`-dən gəlir (bax `role_catalog.effective_level`).
    target_level = max(
        (
            effective_level(membership.role)
            for membership in membership_queryset(organization, user_ids=[target_user.pk])
        ),
        default=0,
    )
    if not is_superadmin and not is_self and target_level >= actor_level:
        return pgettext(_CTX, "insufficient_level_for_target_user")
    if not is_superadmin and effective_level(target_role) >= actor_level:
        return pgettext(_CTX, "Yalnız öz səviyyənizdən aşağı rolları verə bilərsiniz.")

    if is_owner_role(target_role) and not _can_assign_owner_roles(request, organization, is_superadmin=is_superadmin):
        return pgettext(_CTX, "«Sahib» səviyyəli rol üçün `org.owner.assign` icazəsi tələb olunur.")
    if is_admin_role(target_role) and not _can_assign_admin_roles(request, organization, is_superadmin=is_superadmin):
        return pgettext(_CTX, "«Administrator» səviyyəli rol üçün `org.admin.assign` icazəsi tələb olunur.")
    if not is_superadmin and is_org_wide_role(target_role) and actor_is_unit_scoped(request.user, organization):
        return pgettext(_CTX, "not_allowed_to_assign_some_roles")
    return None


def _grant(request, *, organization, is_superadmin, actor_level, next_url):
    target_user = _resolve_target_user(request)
    if target_user is None:
        return _deny(request, next_url, pgettext(_CTX, "user_not_selected"))

    target_role = Role.objects.filter(
        organization=organization, pk=(request.POST.get("role_id") or "").strip() or None, is_active=True
    ).first()
    if target_role is None:
        return _deny(request, next_url, pgettext(_CTX, "Rol tapılmadı və ya deaktivdir."))

    denial = _guard(
        request,
        organization=organization,
        target_user=target_user,
        target_role=target_role,
        is_superadmin=is_superadmin,
        actor_level=actor_level,
    )
    if denial is not None:
        return _deny(request, next_url, denial)

    scope_unit = _resolve_scope_unit(organization, request.POST.get("scope_unit"))
    reason = (request.POST.get("reason") or "").strip()[:500]

    with transaction.atomic():
        membership, created = Membership.objects.update_or_create(
            user=target_user,
            organization=organization,
            role=target_role,
            scope_unit=scope_unit,
            defaults={"is_active": True, "assigned_by": request.user},
        )
        sync_profile_primary_role(target_user, organization)

    _audit(
        request,
        organization=organization,
        membership=membership,
        action="create" if created else "update",
        reason=reason,
        new_values={
            "role_id": str(target_role.id),
            "role_name": target_role.name,
            "scope_unit": str(scope_unit.id) if scope_unit is not None else "",
            "target_user": target_user.username,
        },
    )
    messages.success(
        request,
        pgettext(_CTX, "«%(role)s» rolu %(user)s hesabına verildi.")
        % {"role": role_label(target_role), "user": target_user.username},
    )
    return redirect(next_url)


def _revoke(request, *, organization, is_superadmin, actor_level, next_url):
    membership = (
        Membership.objects.filter(
            organization=organization, pk=(request.POST.get("membership_id") or "").strip() or None, is_active=True
        )
        .select_related("user", "role", "scope_unit")
        .first()
    )
    if membership is None:
        return _deny(request, next_url, pgettext(_CTX, "Üzvlük tapılmadı."))

    target_user = membership.user
    denial = _guard(
        request,
        organization=organization,
        target_user=target_user,
        target_role=membership.role,
        is_superadmin=is_superadmin,
        actor_level=actor_level,
    )
    if denial is not None:
        return _deny(request, next_url, denial)

    remaining = [
        item for item in membership_queryset(organization, user_ids=[target_user.pk]) if item.id != membership.id
    ]
    if not remaining:
        return _deny(
            request,
            next_url,
            pgettext(_CTX, "Şəxsin son üzvlüyü buradan silinmir — «Rol təyin et» bölməsindən idarə edin."),
        )
    if is_owner_role(membership.role) and not _owner_membership_exists(organization, exclude_id=membership.id):
        return _deny(request, next_url, pgettext(_CTX, "Təşkilatda ən az bir sahib qalmalıdır."))

    reason = (request.POST.get("reason") or "").strip()[:500]
    old_values = {
        "role_id": str(membership.role_id),
        "role_name": membership.role.name,
        "scope_unit": str(membership.scope_unit_id) if membership.scope_unit_id else "",
        "target_user": target_user.username,
    }
    with transaction.atomic():
        membership.is_active = False
        membership.is_primary = False
        membership.save(update_fields=["is_active", "is_primary", "updated_at"])
        sync_profile_primary_role(target_user, organization)

    _audit(
        request,
        organization=organization,
        membership=membership,
        action="delete",
        reason=reason,
        old_values=old_values,
        new_values={"is_active": False},
    )
    messages.success(
        request,
        pgettext(_CTX, "«%(role)s» rolu %(user)s hesabından geri alındı.")
        % {"role": role_label(membership.role), "user": target_user.username},
    )
    return redirect(next_url)


def _audit(request, *, organization, membership, action, reason, old_values=None, new_values=None):
    from apps.organizations.public import create_audit_log

    create_audit_log(
        user=request.user,
        organization=organization,
        action=action,
        resource_type="membership",
        resource_id=membership.id,
        resource_repr=str(membership),
        old_values=old_values or {},
        new_values=new_values or {},
        reason=reason,
        request=request,
    )


def handle_org_role_action(request, *, organization, is_superadmin, actor_level, next_url):
    """`grant_role` / `revoke_role` — bizim əməl deyilsə `None` qaytarır."""
    action = (request.POST.get("action") or "").strip()
    if action not in ORG_ROLE_ACTIONS:
        return None
    handler = _grant if action == "grant_role" else _revoke
    return handler(
        request,
        organization=organization,
        is_superadmin=is_superadmin,
        actor_level=actor_level,
        next_url=next_url,
    )
