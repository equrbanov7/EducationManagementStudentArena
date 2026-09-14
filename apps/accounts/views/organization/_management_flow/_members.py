"""student_organization_management flow — üzv çıxarılması mixin-i."""

import logging

from django.db import transaction

from apps.notifications.public import notify_member_removed_from_organization
from apps.organizations.models import Membership
from apps.organizations.public import EMPTY_SCOPE, ORG_WIDE_SCOPE, create_audit_log, get_permission_scope
from core.constants import OrganizationType
from core.permissions import has_permission

from ....models import ProfileRole, UserProfile
from ..._helpers import _collect_actor_permissions, _map_org_role_to_profile_role

logger = logging.getLogger(__name__)

# Uzaqlaşdırma açarları (audit `access` 2026-09-13, F-03/F-06). Kataloqdakı
# `member.remove` əvvəl KODDA HEÇ YERDƏ yoxlanmırdı — qapı yalnız `user_level ≥ 65`
# idi, ona görə imtahan mərkəzi rəhbəri (85, açarsız) müəllim və HR üzvlüyünü
# deaktiv edə bilirdi. İndi açar real qapıdır; `member.student_manage` isə
# müəllimə DELEGASİYA ilə verilən dar açardır — yalnız tələbə üzvlüyü.
REMOVE_PERMISSION = "member.remove"
STUDENT_MANAGE_PERMISSION = "member.student_manage"
_STUDENT_PROFILE_ROLES = frozenset({ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT})
_REMOVE_DENIED_MESSAGE = "Üzvü uzaqlaşdırmaq üçün «member.remove» icazəsi tələb olunur."
_REMOVE_OUT_OF_SCOPE_MESSAGE = "Bu istifadəçi sizin struktur əhatənizdən kənardadır."


class _MembersMixin:
    """üzv çıxarılması (StudentOrgManagementFlow MRO ilə istifadə edir)."""

    def _removal_scope(self, *, student_target):
        """Aktorun uzaqlaşdırma ƏHATƏSİ — açara görə, fail-closed (F-03/F-04).

        * superadmin / təşkilat sahibi → org-wide;
        * `member.remove` daşıyan üzvlük → `get_permission_scope` nəticəsi
          (ORGANIZATION rolu → org-wide; UNIT rolu → öz alt-ağacı — dekan
          yalnız öz fakültəsi, F-04);
        * hədəf TƏLƏBƏDİRSƏ `member.student_manage` (delegasiya daxil,
          `_collect_actor_permissions`) → org-wide: bu, müəllimə verilən kurs-
          səviyyəli delegasiyadır, COURSE rolunun struktur əhatəsi olmur;
        * heç biri yoxdursa → `EMPTY_SCOPE` (rədd).
        """
        actor = self.request.user
        if self.is_superadmin or getattr(self.org, "owner_id", None) == actor.id:
            return ORG_WIDE_SCOPE
        scope = get_permission_scope(actor, self.org, REMOVE_PERMISSION, request=self.request)
        if scope.has_structure_access:
            return scope
        if student_target:
            actor_perms, _ = _collect_actor_permissions(actor, self.org, request=self.request)
            if has_permission(list(actor_perms), STUDENT_MANAGE_PERMISSION):
                return ORG_WIDE_SCOPE
        return EMPTY_SCOPE

    def _target_inside_scope(self, scope, active_memberships):
        """Hədəfin BÜTÜN aktiv üzvlükləri aktor alt-ağacındadırmı (F-04).

        `scope_unit`-siz üzvlük unit-scope aktor üçün «aidiyyəti müəyyən deyil»
        deməkdir → rədd (`user_scope_covers_unit` ilə eyni fail-closed qayda).
        """
        if scope.is_org_wide:
            return True
        if not scope.is_unit_scoped or not active_memberships:
            return False
        unit_ids = {membership.scope_unit_id for membership in active_memberships}
        if None in unit_ids:
            return False
        from apps.organizations.models import OrgUnit

        covered = OrgUnit.objects.filter(scope.unit_subtree_q()).filter(organization=self.org, pk__in=unit_ids).count()
        return covered == len(unit_ids)

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
        # F-03/F-04 (2026-09-13): səviyyə iyerarxiyası KİFAYƏT DEYİL — açar +
        # struktur əhatəsi də tələb olunur (zondlar M01/M02/M03 bunsuz keçirdi).
        scope = self._removal_scope(student_target=effective_profile_role in _STUDENT_PROFILE_ROLES)
        if not scope.has_structure_access:
            return (False, _REMOVE_DENIED_MESSAGE)
        if not self._target_inside_scope(scope, active_memberships):
            return (False, _REMOVE_OUT_OF_SCOPE_MESSAGE)
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
