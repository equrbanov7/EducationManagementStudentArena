"""role_assignment flow — hədəf resolver-lər + role-change guard-ları mixin-i."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from django.utils.translation import pgettext_lazy

from apps.notifications.models import StudentOrganizationRequestStatus

from ....models import UserProfile
from ..._helpers import _normalized_org_name, _pending_student_request_queryset

User = get_user_model()


class _ResolversMixin:
    """hədəf resolver-lər + role-change guard-ları (RoleAssignmentFlow MRO ilə istifadə edir)."""

    def _enforce_role_change_guards(self, *, action_name, target_membership, target_role):
        if target_membership.user_id == self.request.user.id:
            return self._deny_assignment(
                "self_role_change_forbidden",
                "Öz rolunuzu dəyişdirə bilməzsiniz.",
                action_name=action_name,
                target_membership=target_membership,
                target_role=target_role,
            )
        target_primary_level = self.get_user_org_role_level(target_membership.user, self.org)
        if not self.is_superadmin and target_primary_level >= self.actor_primary_level:
            return self._deny_assignment(
                "target_level_not_lower_than_actor",
                "Yalnız sizdən aşağı səviyyəli üzvlərin rolunu dəyişə bilərsiniz.",
                action_name=action_name,
                target_membership=target_membership,
                target_role=target_role,
                extra={"target_primary_level": target_primary_level, "actor_primary_level": self.actor_primary_level},
            )
        if not self.is_superadmin and target_role.level >= self.actor_primary_level:
            return self._deny_assignment(
                "requested_role_not_lower_than_actor",
                "Yalnız sizdən aşağı səviyyəli rolları təyin edə bilərsiniz.",
                action_name=action_name,
                target_membership=target_membership,
                target_role=target_role,
                extra={"actor_primary_level": self.actor_primary_level},
            )
        if (self._is_owner_role(target_membership.role) or self._is_owner_role(target_role)) and (
            not self.can_assign_owner_roles
        ):
            return self._deny_assignment(
                "owner_role_assignment_permission_required",
                "`org.owner.assign` icazəsi olmadan owner səviyyəli rol təyini/dəyişimi qadağandır.",
                action_name=action_name,
                target_membership=target_membership,
                target_role=target_role,
            )
        if (
            (self._is_admin_role(target_membership.role) or self._is_admin_role(target_role))
            and (not self._is_owner_role(target_membership.role))
            and (not self._is_owner_role(target_role))
            and (not self.can_assign_admin_roles)
        ):
            return self._deny_assignment(
                "admin_role_assignment_permission_required",
                "`org.admin.assign` icazəsi olmadan admin səviyyəli rol təyini/dəyişimi qadağandır.",
                action_name=action_name,
                target_membership=target_membership,
                target_role=target_role,
            )
        if self._is_owner_role(target_membership.role) and (not self._is_owner_role(target_role)):
            has_other_owner = self._owner_membership_queryset().exclude(id=target_membership.id).exists()
            if not has_other_owner:
                return self._deny_assignment(
                    "last_owner_must_remain",
                    "Təşkilatda ən az bir owner qalmalıdır.",
                    status=409,
                    action_name=action_name,
                    target_membership=target_membership,
                    target_role=target_role,
                )
        return None

    def _resolve_target_role(self, *, action_name, role_id):
        target_role_uuid = self._parse_uuid(role_id)
        if target_role_uuid is None:
            return (
                None,
                self._deny_assignment("invalid_role_id", "Düzgün `role_id` göndərilməyib.", action_name=action_name),
            )
        target_role = self.Role.objects.filter(id=target_role_uuid, is_active=True).first()
        if target_role is None:
            return (
                None,
                self._deny_assignment("role_not_found", "Rol tapılmadı və ya deaktivdir.", action_name=action_name),
            )
        if target_role.organization_id != self.org.id:
            return (
                None,
                self._deny_assignment(
                    "role_outside_active_organization",
                    "Rol yalnız aktiv təşkilat scope-u daxilində təyin oluna bilər.",
                    action_name=action_name,
                    target_role=target_role,
                ),
            )
        return (target_role, None)

    def _resolve_attach_target(self, *, action_name, target_role):
        user_id = self.request.POST.get("user_id")
        try:
            target_user_id = int(str(user_id))
        except (TypeError, ValueError):
            return (
                None,
                None,
                None,
                self._deny_assignment(
                    "invalid_user_id",
                    "Düzgün `user_id` göndərilməyib.",
                    action_name=action_name,
                    target_role=target_role,
                ),
            )
        target_user = User.objects.filter(id=target_user_id, is_active=True).first()
        if target_user is None:
            return (
                None,
                None,
                None,
                self._deny_assignment(
                    "target_user_not_found", "İstifadəçi tapılmadı.", action_name=action_name, target_role=target_role
                ),
            )
        if target_user.id == self.request.user.id:
            return (
                None,
                None,
                None,
                self._deny_assignment(
                    "self_role_change_forbidden",
                    "Öz rolunuzu dəyişdirə bilməzsiniz.",
                    action_name=action_name,
                    target_user=target_user,
                    target_role=target_role,
                ),
            )
        target_profile, _ = UserProfile.objects.get_or_create(user=target_user)
        if target_profile.organization and target_profile.organization != self.org:
            return (
                None,
                None,
                None,
                self._deny_assignment(
                    "user_bound_to_other_org",
                    "İstifadəçi başqa təşkilata bağlıdır.",
                    action_name=action_name,
                    target_user=target_user,
                    target_role=target_role,
                ),
            )
        if self.Membership.objects.filter(user=target_user, is_active=True).exclude(organization=self.org).exists():
            return (
                None,
                None,
                None,
                self._deny_assignment(
                    "user_has_membership_in_other_org",
                    "İstifadəçi başqa təşkilat üzvlüyünə malikdir.",
                    action_name=action_name,
                    target_user=target_user,
                    target_role=target_role,
                ),
            )
        target_primary_level = self.get_user_org_role_level(target_user, self.org)
        if not self.is_superadmin and target_primary_level >= self.actor_primary_level:
            return (
                None,
                None,
                None,
                self._deny_assignment(
                    "target_level_not_lower_than_actor",
                    "Yalnız sizdən aşağı səviyyəli üzvlərin rolunu dəyişə bilərsiniz.",
                    action_name=action_name,
                    target_user=target_user,
                    target_role=target_role,
                    extra={
                        "target_primary_level": target_primary_level,
                        "actor_primary_level": self.actor_primary_level,
                    },
                ),
            )
        if not self.is_superadmin and target_role.level >= self.actor_primary_level:
            return (
                None,
                None,
                None,
                self._deny_assignment(
                    "requested_role_not_lower_than_actor",
                    "Yalnız sizdən aşağı səviyyəli rolları təyin edə bilərsiniz.",
                    action_name=action_name,
                    target_user=target_user,
                    target_role=target_role,
                    extra={"actor_primary_level": self.actor_primary_level},
                ),
            )
        if self._is_owner_role(target_role) and (not self.can_assign_owner_roles):
            return (
                None,
                None,
                None,
                self._deny_assignment(
                    "owner_role_assignment_permission_required",
                    "`org.owner.assign` icazəsi olmadan owner səviyyəli rol təyin etmək olmaz.",
                    action_name=action_name,
                    target_user=target_user,
                    target_role=target_role,
                ),
            )
        if (
            self._is_admin_role(target_role)
            and (not self._is_owner_role(target_role))
            and (not self.can_assign_admin_roles)
        ):
            return (
                None,
                None,
                None,
                self._deny_assignment(
                    "admin_role_assignment_permission_required",
                    "`org.admin.assign` icazəsi olmadan admin səviyyəli rol təyin etmək olmaz.",
                    action_name=action_name,
                    target_user=target_user,
                    target_role=target_role,
                ),
            )
        if not self.is_superadmin:
            is_requested_for_org = _pending_student_request_queryset(
                user=target_user, organization=self.org, statuses=[StudentOrganizationRequestStatus.PENDING]
            ).exists()
            if not is_requested_for_org:
                requested_org = target_profile.requested_organization
                requested_name = _normalized_org_name(target_profile.requested_organization_name)
                is_requested_for_org = (
                    requested_org is not None
                    and requested_org == self.org
                    or (
                        requested_org is None
                        and requested_name
                        and (requested_name == _normalized_org_name(self.org.name))
                    )
                )
            if not is_requested_for_org:
                signup_mismatch_message = pgettext_lazy(
                    "accounts.role_assignment.message", "user_did_not_select_this_org_on_signup"
                )
                if self._wants_json_response() or self.request.POST.get("action") == "prepare_operation":
                    return (
                        None,
                        None,
                        None,
                        self._deny_assignment(
                            "user_did_not_select_this_org_on_signup",
                            signup_mismatch_message,
                            action_name=action_name,
                            target_user=target_user,
                            target_role=target_role,
                        ),
                    )
                self.create_audit_log(
                    user=self.request.user,
                    organization=self.org,
                    action="update",
                    resource_type="user",
                    resource_id=target_user.id,
                    resource_repr=target_user.username,
                    old_values=None,
                    new_values=self._build_role_assignment_audit_values(
                        status="denied",
                        action_name=action_name,
                        target_role=target_role,
                        target_user=target_user,
                        reason_code="user_did_not_select_this_org_on_signup",
                        extra={
                            "requested_membership_id": self.request.POST.get("membership_id"),
                            "requested_user_id": self.request.POST.get("user_id"),
                            "requested_role_id": self.request.POST.get("role_id"),
                            "reason": str(signup_mismatch_message),
                        },
                    ),
                    reason=str(signup_mismatch_message),
                    request=self.request,
                )
                messages.error(self.request, signup_mismatch_message)
                return (None, None, None, redirect(self.next_url))
        existing_membership = (
            self.Membership.objects.filter(user=target_user, organization=self.org)
            .select_related("role", "organization", "user")
            .first()
        )
        if existing_membership is not None:
            denied_response = self._enforce_role_change_guards(
                action_name=action_name, target_membership=existing_membership, target_role=target_role
            )
            if denied_response:
                return (None, None, None, denied_response)
        return (target_user, target_profile, existing_membership, None)

    def _resolve_update_target(self, *, action_name, target_role):
        membership_id = self.request.POST.get("membership_id")
        target_membership_uuid = self._parse_uuid(membership_id)
        if target_membership_uuid is None:
            return (
                None,
                self._deny_assignment(
                    "invalid_membership_id",
                    "Düzgün `membership_id` göndərilməyib.",
                    action_name=action_name,
                    target_role=target_role,
                ),
            )
        target_membership = (
            self.Membership.objects.select_related("role", "user", "organization")
            .filter(id=target_membership_uuid, is_active=True)
            .first()
        )
        if target_membership is None:
            return (
                None,
                self._deny_assignment(
                    "membership_not_found", "Üzvlük tapılmadı.", action_name=action_name, target_role=target_role
                ),
            )
        if target_membership.organization_id != self.org.id:
            return (
                None,
                self._deny_assignment(
                    "membership_outside_active_organization",
                    "Üzvlük yalnız aktiv təşkilat scope-u daxilində idarə oluna bilər.",
                    action_name=action_name,
                    target_membership=target_membership,
                    target_role=target_role,
                ),
            )
        denied_response = self._enforce_role_change_guards(
            action_name=action_name, target_membership=target_membership, target_role=target_role
        )
        if denied_response:
            return (None, denied_response)
        return (target_membership, None)
