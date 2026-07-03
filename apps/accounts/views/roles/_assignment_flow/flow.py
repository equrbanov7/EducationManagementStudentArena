"""role_assignment flow — əsas sinif (__init__ + run) + mixin birləşməsi."""

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext, pgettext_lazy

from apps.notifications.models import StudentOrganizationRequestStatus

from ....models import UserProfile
from ..._helpers import (
    ROLE_ASSIGNMENT_OPERATION_TOKEN_MAX_AGE_SECONDS,
    _append_query_params,
    _close_other_pending_student_requests,
    _collect_actor_permissions,
    _ensure_profile_admin_membership,
    _get_active_organization,
    _is_superadmin_user,
    _map_org_role_to_profile_role,
    _pending_student_request_queryset,
    _resolve_next_url,
)
from ._audit import _AuditMixin
from ._predicates import _PredicatesMixin
from ._resolvers import _ResolversMixin


class _RoleAssignmentFlow(_AuditMixin, _PredicatesMixin, _ResolversMixin):
    """role_assignment view-nin request-scoped məntiqi (god-file refaktoru).

    Davranış köhnə tək-funksiyalı implementasiya ilə eynidir."""

    def __init__(self, request):
        from apps.organizations.models import Membership, Role
        from apps.organizations.public import create_audit_log, get_user_org_role_level
        from core.permissions import has_permission

        self.request = request
        self.Membership = Membership
        self.Role = Role
        self.create_audit_log = create_audit_log
        self.get_user_org_role_level = get_user_org_role_level
        self.next_url = None

        self.org = _get_active_organization(request)
        self.is_superadmin = _is_superadmin_user(request.user)
        self.actor_primary_membership = None
        self.actor_primary_level = 999 if self.is_superadmin else 0
        self.can_manage_members = False
        self.can_assign_owner_roles = False
        self.can_assign_admin_roles = False
        if not self.org:
            return

        _ensure_profile_admin_membership(request.user, self.org)
        actor_memberships = Membership.objects.filter(
            user=request.user, organization=self.org, is_active=True
        ).select_related("role")
        self.actor_primary_membership = actor_memberships.order_by("-role__level").first()
        self.actor_primary_level = (
            999
            if self.is_superadmin
            else (self.actor_primary_membership.role.level if self.actor_primary_membership else 0)
        )
        actor_permissions, _ = _collect_actor_permissions(request.user, self.org)
        actor_permission_list = list(actor_permissions)
        self.can_manage_members = (
            self.is_superadmin
            or has_permission(actor_permission_list, "role.assign")
            or has_permission(actor_permission_list, "org.manage_members")
        )
        self.can_assign_owner_roles = self.is_superadmin or has_permission(actor_permission_list, "org.owner.assign")
        self.can_assign_admin_roles = (
            self.is_superadmin
            or self.can_assign_owner_roles
            or has_permission(actor_permission_list, "org.admin.assign")
        )

    def run(self):
        if not self.org:
            messages.error(
                self.request, pgettext_lazy("accounts.role_assignment.message", "active_organization_not_found")
            )
            return redirect("accounts:profile")
        if not self.is_superadmin and self.actor_primary_level < 50:
            messages.error(self.request, pgettext_lazy("accounts.role_assignment.message", "teacher_or_higher_only"))
            return redirect("accounts:profile")
        search = self.request.GET.get("q", self.request.GET.get("search", ""))
        unassigned_search = self.request.GET.get("unassigned_search", "")
        profile_section_url = _append_query_params(
            reverse("accounts:profile"),
            section="role-assignment",
            q=search,
            unassigned_search=unassigned_search,
            role_members_page=self.request.GET.get("role_members_page", ""),
            role_pending_page=self.request.GET.get("role_pending_page", ""),
        )
        if self.request.method != "POST":
            return redirect(profile_section_url)
        if self.request.method == "POST":
            action = self.request.POST.get("action", "update_member")
            self.next_url = _resolve_next_url(self.request, profile_section_url)
            requested_action = action
            role_id = self.request.POST.get("role_id")
            if action == "prepare_operation":
                requested_action = (self.request.POST.get("target_action") or "").strip()
                role_id = self.request.POST.get("new_role_id") or role_id
            if requested_action not in {"attach_user", "update_member"}:
                return self._deny_assignment(
                    "unknown_action", "Bilinməyən əməliyyat.", action_name=requested_action or action
                )
            if not self.is_superadmin and self.actor_primary_membership is None:
                return self._deny_assignment(
                    "actor_not_member_of_active_organization",
                    "Aktiv təşkilatda üzvlük tapılmadı.",
                    action_name=requested_action,
                )
            if not self.can_manage_members:
                return self._deny_assignment(
                    "missing_member_management_permission",
                    "`role.assign` və ya `org.manage_members` icazəsi tələb olunur.",
                    action_name=requested_action,
                )
            target_role, role_error = self._resolve_target_role(action_name=requested_action, role_id=role_id)
            if role_error:
                return role_error
            target_membership = None
            target_user = None
            target_profile = None
            existing_membership = None
            if requested_action == "attach_user":
                target_user, target_profile, existing_membership, attach_error = self._resolve_attach_target(
                    action_name=requested_action, target_role=target_role
                )
                if attach_error:
                    return attach_error
            else:
                target_membership, membership_error = self._resolve_update_target(
                    action_name=requested_action, target_role=target_role
                )
                if membership_error:
                    return membership_error
            if action == "prepare_operation":
                operation_token = self._build_operation_token(
                    action_name=requested_action,
                    target_role=target_role,
                    target_membership=target_membership,
                    target_user=target_user,
                )
                old_role_label = (
                    target_membership.role.display_name
                    if target_membership is not None
                    else existing_membership.role.display_name if existing_membership is not None else "Üzvlük yoxdur"
                )
                return JsonResponse(
                    {
                        "success": True,
                        "operation_token": operation_token,
                        "expires_in_seconds": ROLE_ASSIGNMENT_OPERATION_TOKEN_MAX_AGE_SECONDS,
                        "action": requested_action,
                        "target": {
                            "organization_id": str(self.org.id),
                            "target_id": str(target_membership.id if target_membership is not None else target_user.id),
                            "old_role": old_role_label,
                            "new_role": target_role.display_name,
                        },
                    }
                )
            token_error = self._validate_operation_token(
                action_name=requested_action,
                target_role=target_role,
                target_membership=target_membership,
                target_user=target_user,
            )
            if token_error:
                return token_error
            if requested_action == "attach_user":
                attach_old_role = existing_membership.role if existing_membership is not None else None
                membership, created = self.Membership.objects.get_or_create(
                    user=target_user,
                    organization=self.org,
                    defaults={
                        "role": target_role,
                        "assigned_by": self.request.user,
                        "is_primary": True,
                        "is_active": True,
                    },
                )
                if not created:
                    denied_response = self._enforce_role_change_guards(
                        action_name=requested_action, target_membership=membership, target_role=target_role
                    )
                    if denied_response:
                        return denied_response
                    membership.role = target_role
                    membership.assigned_by = self.request.user
                    membership.is_active = True
                    membership.save(update_fields=["role", "assigned_by", "is_active", "updated_at"])
                target_profile.organization = self.org
                target_profile.organization_type = self.org.org_type
                target_profile.role = _map_org_role_to_profile_role(target_role)
                target_profile.requested_organization = self.org
                target_profile.requested_organization_name = self.org.name
                target_profile.requested_organization_message = ""
                target_profile.save(
                    update_fields=[
                        "organization",
                        "organization_type",
                        "role",
                        "requested_organization",
                        "requested_organization_name",
                        "requested_organization_message",
                        "updated_at",
                    ]
                )
                now = timezone.now()
                _pending_student_request_queryset(
                    user=target_user, organization=self.org, statuses=[StudentOrganizationRequestStatus.PENDING]
                ).update(
                    status=StudentOrganizationRequestStatus.APPROVED,
                    resolution_note="Təşkilat tərəfindən qəbul edildi.",
                    responded_by=self.request.user,
                    responded_at=now,
                    updated_at=now,
                )
                _close_other_pending_student_requests(
                    user=target_user, accepted_organization=self.org, responded_by=self.request.user
                )
                self.create_audit_log(
                    user=self.request.user,
                    organization=self.org,
                    action="update",
                    resource_type="membership",
                    resource_id=membership.id,
                    resource_repr=str(membership),
                    old_values={
                        "old_role_id": str(attach_old_role.id) if attach_old_role is not None else "",
                        "old_role_name": attach_old_role.display_name if attach_old_role is not None else "",
                    },
                    new_values=self._build_role_assignment_audit_values(
                        status="success",
                        action_name=requested_action,
                        target_role=target_role,
                        target_membership=membership,
                        target_user=target_user,
                        old_role=attach_old_role,
                        reason_code="",
                        extra={"attached_user": target_user.username},
                    ),
                    request=self.request,
                )
                success_message = pgettext(
                    "accounts.role_assignment.message", "Uğurla əlavə edildi: {user} → {role}."
                ).format(user=target_user.username, role=target_role.display_name)
                if self._wants_json_response():
                    return JsonResponse({"success": True, "message": success_message, "redirect_url": self.next_url})
                messages.success(self.request, success_message)
                return redirect(self.next_url)
            old_role = target_membership.role
            target_membership.role = target_role
            target_membership.assigned_by = self.request.user
            target_membership.save(update_fields=["role", "assigned_by", "updated_at"])
            target_profile, _ = UserProfile.objects.get_or_create(user=target_membership.user)
            target_profile.role = _map_org_role_to_profile_role(target_role)
            target_profile.organization = self.org
            target_profile.organization_type = self.org.org_type
            target_profile.requested_organization = self.org
            target_profile.requested_organization_name = self.org.name
            target_profile.requested_organization_message = ""
            target_profile.save(
                update_fields=[
                    "role",
                    "organization",
                    "organization_type",
                    "requested_organization",
                    "requested_organization_name",
                    "requested_organization_message",
                    "updated_at",
                ]
            )
            now = timezone.now()
            _pending_student_request_queryset(
                user=target_membership.user, organization=self.org, statuses=[StudentOrganizationRequestStatus.PENDING]
            ).update(
                status=StudentOrganizationRequestStatus.APPROVED,
                resolution_note="Üzvlük aktiv olduğuna görə müraciət bağlandı.",
                responded_by=self.request.user,
                responded_at=now,
                updated_at=now,
            )
            _close_other_pending_student_requests(
                user=target_membership.user, accepted_organization=self.org, responded_by=self.request.user
            )
            self.create_audit_log(
                user=self.request.user,
                organization=self.org,
                action="update",
                resource_type="membership",
                resource_id=target_membership.id,
                resource_repr=str(target_membership),
                old_values={
                    "old_role_id": str(old_role.id) if old_role is not None else "",
                    "old_role_name": old_role.display_name if old_role is not None else "",
                },
                new_values=self._build_role_assignment_audit_values(
                    status="success",
                    action_name=requested_action,
                    target_role=target_role,
                    target_membership=target_membership,
                    target_user=target_membership.user,
                    old_role=old_role,
                ),
                request=self.request,
            )
            success_message = pgettext(
                "accounts.role_assignment.message", "Uğurla yeniləndi: {user} → {role}."
            ).format(user=target_membership.user.username, role=target_role.display_name)
            if self._wants_json_response():
                return JsonResponse({"success": True, "message": success_message, "redirect_url": self.next_url})
            messages.success(self.request, success_message)
            return redirect(self.next_url)
        return redirect(profile_section_url)
