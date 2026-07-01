"""student_organization_management flow — müraciət qəbul/rədd mixin-i."""

from django.db import transaction
from django.utils import timezone

from apps.notifications.models import StudentOrganizationRequest, StudentOrganizationRequestStatus
from apps.organizations.models import Membership
from apps.organizations.services import create_audit_log
from core.constants import OrganizationType

from ....models import ProfileRole
from ..._helpers import (
    STUDENT_PENDING_INVITE_TITLE,
    _close_other_pending_student_requests,
    _normalized_org_name,
    _pending_student_request_queryset,
    _set_student_org_request_status,
    _sync_profile_pending_request_snapshot,
)


class _RequestsMixin:
    """müraciət qəbul/rədd (StudentOrgManagementFlow MRO ilə istifadə edir)."""

    def _load_pending_request_for_user(self, target_user, *, include_auto_closed=False):
        statuses = [StudentOrganizationRequestStatus.PENDING]
        if include_auto_closed:
            statuses.append(StudentOrganizationRequestStatus.AUTO_CLOSED)
        return (
            _pending_student_request_queryset(user=target_user, organization=self.org, statuses=statuses)
            .order_by("-created_at")
            .first()
        )

    def _approve_requested_profile(self, target_profile):
        target_user = target_profile.user
        target_request = self._load_pending_request_for_user(target_user)
        if target_request is None:
            requested_org = target_profile.requested_organization
            requested_name = _normalized_org_name(target_profile.requested_organization_name)
            is_requested_for_org = (
                requested_org is not None
                and requested_org == self.org
                or (
                    requested_org is None and requested_name and (requested_name == _normalized_org_name(self.org.name))
                )
            )
            if not is_requested_for_org:
                return (False, "İstifadəçi bu təşkilatı seçməyib.")
            target_request = StudentOrganizationRequest.objects.create(
                user=target_user,
                organization=self.org,
                message=(target_profile.requested_organization_message or "").strip(),
                status=StudentOrganizationRequestStatus.PENDING,
            )
        if target_profile.organization and target_profile.organization != self.org:
            _set_student_org_request_status(
                request_obj=target_request,
                status=StudentOrganizationRequestStatus.AUTO_CLOSED,
                note=f"İstifadəçi artıq {target_profile.organization.name} təşkilatının üzvüdür.",
                responded_by=self.request.user,
            )
            _sync_profile_pending_request_snapshot(target_profile)
            return (False, "İstifadəçi başqa təşkilata bağlıdır.")
        if Membership.objects.filter(
            user=target_user, organization=self.org, is_active=False, title=STUDENT_PENDING_INVITE_TITLE
        ).exists():
            return (False, "Bu istifadəçi üçün dəvət göndərilib, əvvəlcə istifadəçi qəbul etməlidir.")
        if self.student_role is None:
            return (False, "Bu təşkilat üçün tələbə rolu tapılmadı.")
        target_membership = (
            Membership.objects.filter(user=target_user, organization=self.org)
            .select_related("role")
            .order_by("-is_active", "-is_primary", "-role__level")
            .first()
        )
        if target_membership and (not self.is_superadmin) and (target_membership.role.level >= self.user_level):
            return (False, "Yalnız öz səviyyənizdən aşağı istifadəçiləri idarə edə bilərsiniz.")
        with transaction.atomic():
            if target_membership:
                old_role = target_membership.role.name
                target_membership.role = self.student_role
                target_membership.assigned_by = self.request.user
                target_membership.is_active = True
                target_membership.is_primary = True
                target_membership.title = ""
                target_membership.save(
                    update_fields=["role", "assigned_by", "is_active", "is_primary", "title", "updated_at"]
                )
            else:
                old_role = ""
                target_membership = Membership.objects.create(
                    user=target_user,
                    organization=self.org,
                    role=self.student_role,
                    assigned_by=self.request.user,
                    is_primary=True,
                    is_active=True,
                    title="",
                )
            target_profile.organization = self.org
            target_profile.organization_type = self.org.org_type
            target_profile.role = ProfileRole.STUDENT
            target_profile.requested_organization = self.org
            target_profile.requested_organization_name = self.org.name
            target_profile.requested_organization_message = ""
            target_profile.student_university_name = self.org.name
            target_profile.student_school_identifier = (
                self.org.organization_identifier or self.org.license_identifier or ""
                if self.org.org_type == OrganizationType.SCHOOL
                else ""
            )
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
            _set_student_org_request_status(
                request_obj=target_request,
                status=StudentOrganizationRequestStatus.APPROVED,
                note="Təşkilat tərəfindən qəbul edildi.",
                responded_by=self.request.user,
            )
            now = timezone.now()
            _pending_student_request_queryset(
                user=target_user, organization=self.org, statuses=[StudentOrganizationRequestStatus.PENDING]
            ).exclude(id=target_request.id).update(
                status=StudentOrganizationRequestStatus.AUTO_CLOSED,
                resolution_note="Eyni təşkilat üzrə əvvəlki müraciət avtomatik bağlandı.",
                responded_by=self.request.user,
                responded_at=now,
                updated_at=now,
            )
            _close_other_pending_student_requests(
                user=target_user, accepted_organization=self.org, responded_by=self.request.user
            )
        create_audit_log(
            user=self.request.user,
            organization=self.org,
            action="update",
            resource_type="membership",
            resource_id=target_membership.id,
            resource_repr=str(target_membership),
            old_values={"role": old_role} if old_role else None,
            new_values={
                "role": self.student_role.name,
                "attached_user": target_user.username,
                "action": "approve_requested_student",
            },
            request=self.request,
        )
        return (True, "")

    def _reject_requested_profile(self, target_profile):
        target_request = self._load_pending_request_for_user(target_profile.user, include_auto_closed=True)
        if target_request is None:
            requested_org = target_profile.requested_organization
            requested_name = _normalized_org_name(target_profile.requested_organization_name)
            is_requested_for_org = (
                requested_org is not None
                and requested_org == self.org
                or (
                    requested_org is None and requested_name and (requested_name == _normalized_org_name(self.org.name))
                )
            )
            if not is_requested_for_org:
                return (False, "İstifadəçi bu təşkilata müraciət etməyib.")
            target_profile.requested_organization = None
            target_profile.requested_organization_name = ""
            target_profile.requested_organization_message = ""
            target_profile.save(
                update_fields=[
                    "requested_organization",
                    "requested_organization_name",
                    "requested_organization_message",
                    "updated_at",
                ]
            )
            return (True, "")
        _set_student_org_request_status(
            request_obj=target_request,
            status=StudentOrganizationRequestStatus.REJECTED,
            note="Müraciət təşkilat tərəfindən silindi.",
            responded_by=self.request.user,
        )
        _sync_profile_pending_request_snapshot(target_profile)
        return (True, "")
