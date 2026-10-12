"""student_organization_management flow — dəvət göndər/geri al mixin-i."""

import logging

from django.db import transaction
from django.utils import timezone

from apps.notifications.models import MembershipRequestRoleType, StudentOrganizationRequestStatus
from apps.notifications.public import notify_user_invited_to_organization
from apps.organizations.models import Membership
from apps.organizations.public import create_audit_log, get_permission_scope

from ....models import UserProfile
from ..._helpers import (
    STUDENT_PENDING_INVITE_TITLE,
    _map_org_role_to_profile_role,
    _membership_request_role_label,
    _membership_request_role_type_for_profile_role,
    _pending_student_request_queryset,
    _profile_role_for_membership_request_type,
    _resolve_membership_role,
    _sync_profile_pending_request_snapshot,
)

logger = logging.getLogger(__name__)

# 2026-10-13 (rol auditi B8): dəvət / müraciət təsdiqi əvvəl YALNIZ `user_level ≥ 65` ilə açılırdı —
# `member.invite` yoxlanmırdı, dekan / dekan müavini / kafedra müdiri / imtahan mərkəzi rəhbəri təşkilata
# BÖLMƏSİZ (org-wide) üzv dəvət edir, tələbə/müəllim müraciətini təsdiqləyirdi. İndi açar real qapıdır və
# ƏHATƏ yoxlanılır: bu axın üzvlüyü həmişə `scope_unit=None` ilə yaradır (org-wide), ona görə yalnız
# org-wide `member.invite` əhatəsi (HR, rektor, prorektor, sahib) keçir; UNIT əhatəli aktor (dekan) rədd
# edilir. Uzaqlaşdırma ayrıca `member.remove` ilə qapılıdır (`_members.py`) — bu dəstdə deyil.
INVITE_PERMISSION = "member.invite"
INVITE_GATED_ACTIONS = frozenset(
    {
        "invite_student",
        "bulk_invite_students",
        "invite_teacher_staff",
        "bulk_invite_teacher_staff",
        "revoke_sent_invites",
        "revoke_teacher_staff_invites",
        "approve_requested_student",
        "add_student",
        "bulk_approve_requested_students",
        "approve_teacher_staff_request",
        "reject_teacher_staff_request",
    }
)
_INVITE_DENIED_MESSAGE = "Dəvət və müraciət təsdiqi üçün «member.invite» icazəsi tələb olunur."
_INVITE_OUT_OF_SCOPE_MESSAGE = (
    "Dəvət təşkilata bölməsiz üzvlük yaradır — bunun üçün bütün təşkilat əhatəli «member.invite» icazəsi lazımdır."
)


class _InvitesMixin:
    """dəvət göndər/geri al (StudentOrgManagementFlow MRO ilə istifadə edir)."""

    def _invite_gate_error(self):
        """`None` = əməl icazəlidir; əks halda istifadəçiyə göstəriləcək mesaj (B8, fail-closed).

        * superadmin / təşkilat sahibi → icazəli;
        * `member.invite` əhatəsi ORG-WIDE (ORGANIZATION rolu) → icazəli;
        * UNIT əhatəli `member.invite` (dekan öz fakültəsi) → RƏDD: bu axında vahid yoxdur, dəvət org-wide-dır;
        * açar yalnız COURSE rolundan gəlirsə (müəllimə delegasiya, `teacher_student_only`) → köhnə dar qayda
          qalır: əməllər `run()`-da açara görə süzülüb və rol tipi TƏLƏBƏyə məcburi çevrilib.
        """
        actor = self.request.user
        if self.is_superadmin or getattr(self.org, "owner_id", None) == actor.id:
            return None
        scope = get_permission_scope(actor, self.org, INVITE_PERMISSION, request=self.request)
        if scope.is_org_wide:
            return None
        if scope.is_unit_scoped:
            return _INVITE_OUT_OF_SCOPE_MESSAGE
        if getattr(self, "teacher_student_only", False):
            return None
        return _INVITE_DENIED_MESSAGE

    def _invite_user_for_role(self, target_user, role_type):
        from core.rls import bypass_rls as _bypass_rls

        with _bypass_rls():
            target_profile, _ = UserProfile.objects.get_or_create(user=target_user)
        target_profile_role = _profile_role_for_membership_request_type(role_type)
        target_role_label = _membership_request_role_label(role_type).lower()
        with _bypass_rls():
            membership_role = _resolve_membership_role(self.org, target_profile_role)
        if membership_role is None:
            return (False, "Bu təşkilat üçün uyğun rol tapılmadı.")
        if target_profile.organization and target_profile.organization != self.org:
            return (False, "İstifadəçi başqa təşkilata bağlıdır.")
        if target_profile.organization == self.org:
            return (False, "İstifadəçi artıq bu təşkilatdadır.")
        with _bypass_rls():
            existing_invite = Membership.objects.filter(
                user=target_user, organization=self.org, is_active=False, title=STUDENT_PENDING_INVITE_TITLE
            ).first()
            if existing_invite:
                return (False, "Bu istifadəçi üçün artıq dəvət göndərilib.")
            existing_active = Membership.objects.filter(
                user=target_user, organization=self.org, role=membership_role, scope_unit=None, is_active=True
            ).exists()
            if existing_active:
                return (False, "İstifadəçi artıq bu təşkilatdadır.")
            reusable_membership = (
                Membership.objects.filter(
                    user=target_user, organization=self.org, role=membership_role, scope_unit=None
                )
                .order_by("-updated_at")
                .first()
            )
            with transaction.atomic():
                if reusable_membership is not None:
                    invite_membership = reusable_membership
                    invite_membership.role = membership_role
                    invite_membership.assigned_by = self.request.user
                    invite_membership.is_primary = False
                    invite_membership.is_active = False
                    invite_membership.title = STUDENT_PENDING_INVITE_TITLE
                    invite_membership.save(
                        update_fields=["role", "assigned_by", "is_primary", "is_active", "title", "updated_at"]
                    )
                else:
                    invite_membership = Membership.objects.create(
                        user=target_user,
                        organization=self.org,
                        role=membership_role,
                        scope_unit=None,
                        assigned_by=self.request.user,
                        is_primary=False,
                        is_active=False,
                        title=STUDENT_PENDING_INVITE_TITLE,
                    )
                target_profile.requested_organization = self.org
                target_profile.requested_organization_name = self.org.name
                target_profile.requested_organization_message = ""
                target_profile.save(
                    update_fields=[
                        "requested_organization",
                        "requested_organization_name",
                        "requested_organization_message",
                        "updated_at",
                    ]
                )
                now = timezone.now()
                _pending_student_request_queryset(
                    user=target_user, organization=self.org, statuses=[StudentOrganizationRequestStatus.PENDING]
                ).filter(role_type=role_type).update(
                    status=StudentOrganizationRequestStatus.AUTO_CLOSED,
                    resolution_note="Təşkilat dəvəti göndərildiyi üçün müraciət bağlandı.",
                    responded_by=self.request.user,
                    responded_at=now,
                    updated_at=now,
                )
        create_audit_log(
            user=self.request.user,
            organization=self.org,
            action="create",
            resource_type="membership_invite",
            resource_id=invite_membership.id,
            resource_repr=f"{target_user.username} pending invite",
            old_values=None,
            new_values={
                "action": f"invite_{target_role_label}",
                "invited_user": target_user.username,
                "role": membership_role.name,
            },
            request=self.request,
        )
        try:
            notify_user_invited_to_organization(
                invited_user=target_user,
                organization=self.org,
                invited_by=self.request.user,
                role_label=target_role_label,
            )
        except Exception:
            logger.exception("Failed to send invite notification to %s", target_user.username)
        return (True, "")

    def _invite_student_user(self, target_user):
        return self._invite_user_for_role(target_user, MembershipRequestRoleType.STUDENT)

    def _revoke_sent_invite_for_user(self, target_user, role_type=None):
        target_profile, _ = UserProfile.objects.get_or_create(user=target_user)
        invite_queryset = Membership.objects.filter(
            user=target_user, organization=self.org, is_active=False, title=STUDENT_PENDING_INVITE_TITLE
        ).select_related("role")
        if role_type is not None:
            target_profile_role = _profile_role_for_membership_request_type(role_type)
            invite_queryset = invite_queryset.filter(role=_resolve_membership_role(self.org, target_profile_role))
        invite_membership = invite_queryset.first()
        if invite_membership is None:
            return (False, "Geri çəkiləcək aktiv dəvət tapılmadı.")
        invite_id = str(invite_membership.id)
        mapped_role_type = role_type or _membership_request_role_type_for_profile_role(
            _map_org_role_to_profile_role(invite_membership.role)
        )
        with transaction.atomic():
            invite_membership.delete()
            now = timezone.now()
            _pending_student_request_queryset(
                user=target_user, organization=self.org, statuses=[StudentOrganizationRequestStatus.PENDING]
            ).filter(role_type=mapped_role_type).update(
                status=StudentOrganizationRequestStatus.CANCELLED,
                resolution_note="Təşkilat dəvəti geri çəkildiyi üçün müraciət ləğv edildi.",
                responded_by=self.request.user,
                responded_at=now,
                updated_at=now,
            )
            _sync_profile_pending_request_snapshot(target_profile)
        create_audit_log(
            user=self.request.user,
            organization=self.org,
            action="delete",
            resource_type="membership_invite",
            resource_id=invite_id,
            resource_repr=f"{target_user.username} invite revoked",
            old_values={"status": "pending"},
            new_values={"status": "revoked_by_org"},
            request=self.request,
        )
        return (True, "")
