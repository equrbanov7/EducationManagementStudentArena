"""student_organization_management flow — üzv çıxarılması mixin-i."""

import logging

from django.db import transaction

from apps.notifications.services import notify_member_removed_from_organization
from apps.organizations.models import Membership
from apps.organizations.services import create_audit_log
from core.constants import OrganizationType

from ....models import ProfileRole, UserProfile
from ..._helpers import _map_org_role_to_profile_role

logger = logging.getLogger(__name__)


class _MembersMixin:
    """üzv çıxarılması (StudentOrgManagementFlow MRO ilə istifadə edir)."""

    def _remove_org_member(self, target_user, *, remove_reason=""):
        from core.rls import bypass_rls as _bypass_rls

        removable_profile_roles = {
            ProfileRole.STUDENT,
            ProfileRole.LEAD_STUDENT,
            ProfileRole.TEACHER,
            ProfileRole.ASSISTANT_TEACHER,
            ProfileRole.MEMBER,
            ProfileRole.HR,
        }
        with _bypass_rls():
            target_profile, _ = UserProfile.objects.get_or_create(user=target_user)
            active_memberships = list(
                Membership.objects.filter(user=target_user, organization=self.org, is_active=True).select_related(
                    "role"
                )
            )
        if not active_memberships and target_profile.organization != self.org:
            return (False, "İstifadəçi bu təşkilata bağlı deyil.")
        effective_profile_role = None
        if active_memberships:
            top_membership = max(active_memberships, key=lambda membership: getattr(membership.role, "level", 0))
            effective_profile_role = _map_org_role_to_profile_role(top_membership.role)
        elif target_profile.role in removable_profile_roles:
            effective_profile_role = target_profile.role
        if effective_profile_role not in removable_profile_roles:
            return (False, "Yalnız tələbə, müəllim və staff istifadəçilər bu bölmədən uzaqlaşdırıla bilər.")
        if getattr(self.org, "owner_id", None) == target_user.id:
            return (False, "Təşkilat sahibi bu bölmədən uzaqlaşdırıla bilməz.")
        highest_target_level = max([membership.role.level for membership in active_memberships], default=0)
        if not self.is_superadmin and highest_target_level >= self.user_level:
            return (False, "Yalnız öz səviyyənizdən aşağı istifadəçiləri idarə edə bilərsiniz.")
        with _bypass_rls():
            with transaction.atomic():
                if active_memberships:
                    membership_ids = [membership.id for membership in active_memberships]
                    Membership.objects.filter(id__in=membership_ids).update(is_active=False, is_primary=False)
                fallback_membership = (
                    Membership.objects.filter(user=target_user, is_active=True)
                    .exclude(organization=self.org)
                    .select_related("organization", "role")
                    .order_by("-is_primary", "-role__level")
                    .first()
                )
                if fallback_membership:
                    target_profile.organization = fallback_membership.organization
                    target_profile.organization_type = fallback_membership.organization.org_type
                    target_profile.role = _map_org_role_to_profile_role(fallback_membership.role)
                else:
                    target_profile.organization = None
                    target_profile.organization_type = OrganizationType.INDIVIDUAL
                    target_profile.role = effective_profile_role or target_profile.role
                target_profile.requested_organization = None
                target_profile.requested_organization_name = ""
                target_profile.requested_organization_message = ""
                target_profile.student_university_name = ""
                target_profile.student_school_identifier = ""
                target_profile.save(
                    update_fields=[
                        "organization",
                        "organization_type",
                        "role",
                        "requested_organization",
                        "requested_organization_name",
                        "requested_organization_message",
                        "student_university_name",
                        "student_school_identifier",
                        "updated_at",
                    ]
                )
            create_audit_log(
                user=self.request.user,
                organization=self.org,
                action="update",
                resource_type="membership",
                resource_id=target_user.id,
                resource_repr=f"{target_user.username} removed from {self.org.name}",
                old_values={"organization": self.org.name},
                new_values={"organization": "", "action": "remove_member"},
                reason=self.remove_reason or None,
                request=self.request,
            )
            try:
                notify_member_removed_from_organization(
                    removed_user=target_user,
                    organization=self.org,
                    removed_by=self.request.user,
                    reason=self.remove_reason,
                )
            except Exception:
                logger.exception(
                    "Failed to send removal notification for user %s from org %s", target_user.username, self.org.name
                )
        return (True, "")
