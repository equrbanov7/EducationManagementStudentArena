"""
Student organization invitation action view.

Lets a user accept or reject a pending organization invitation. Behavior is
identical to the pre-refactor implementation.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone

from apps.notifications.models import StudentOrganizationRequestStatus
from core.constants import OrganizationType

from ...models import UserProfile
from .._helpers import (
    STUDENT_PENDING_INVITE_TITLE,
    _close_other_pending_student_requests,
    _map_org_role_to_profile_role,
    _membership_request_role_label,
    _membership_request_role_type_for_profile_role,
    _pending_student_request_queryset,
    _profile_role_for_membership_request_type,
    _resolve_membership_role,
    _resolve_next_url,
)

User = get_user_model()


@login_required
def student_org_invitation_action(request):
    """Allow students to accept or reject pending organization invitations."""
    from apps.organizations.models import Membership
    from apps.organizations.services import create_audit_log
    from core.rls import bypass_rls

    if request.method != "POST":
        return redirect(f"{reverse('accounts:profile')}?section=student-organization-request")

    invite_id = request.POST.get("invite_id")
    action = (request.POST.get("action") or "").strip().lower()
    back_url = _resolve_next_url(request, f"{reverse('accounts:profile')}?section=student-organization-request")

    # The user may not have an active org context yet (they are looking to
    # join one), so the Membership table RLS would hide the invite row.
    # Bypass RLS for the lookup and all subsequent membership/request writes.
    with bypass_rls():
        invite_membership = get_object_or_404(
            Membership.objects.select_related("organization", "role", "assigned_by"),
            id=invite_id,
            user=request.user,
            is_active=False,
            title=STUDENT_PENDING_INVITE_TITLE,
        )

        invite_profile_role = _map_org_role_to_profile_role(getattr(invite_membership, "role", None))
        invite_role_type = _membership_request_role_type_for_profile_role(invite_profile_role)
        invite_role_label = _membership_request_role_label(invite_role_type).lower()

        if action == "accept":
            organization = invite_membership.organization
            if organization.is_suspended:
                messages.error(request, "Təşkilat hazırda aktiv deyil.")
                return redirect(back_url)

            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            if profile.organization and profile.organization != organization:
                messages.error(request, "Əvvəlcə mövcud təşkilatdan çıxın, sonra yeni dəvəti qəbul edin.")
                return redirect(back_url)

            membership_role = invite_membership.role or _resolve_membership_role(
                organization,
                _profile_role_for_membership_request_type(invite_role_type),
            )
            if membership_role is None:
                messages.error(request, "Təşkilatda uyğun üzvlük rolu tapılmadı.")
                return redirect(back_url)

            with transaction.atomic():
                invite_membership.role = membership_role
                invite_membership.is_active = True
                invite_membership.is_primary = True
                invite_membership.title = ""
                invite_membership.save(
                    update_fields=[
                        "role",
                        "is_active",
                        "is_primary",
                        "title",
                        "updated_at",
                    ]
                )

                profile.organization = organization
                profile.organization_type = organization.org_type
                profile.role = _profile_role_for_membership_request_type(invite_role_type)
                profile.requested_organization = organization
                profile.requested_organization_name = organization.name
                profile.requested_organization_message = ""
                profile.student_university_name = organization.name
                profile.student_school_identifier = (
                    organization.organization_identifier or organization.license_identifier or ""
                    if organization.org_type == OrganizationType.SCHOOL
                    else ""
                )
                profile.save(
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

                now = timezone.now()
                _pending_student_request_queryset(
                    user=request.user,
                    organization=organization,
                    statuses=[StudentOrganizationRequestStatus.PENDING],
                ).filter(role_type=invite_role_type).update(
                    status=StudentOrganizationRequestStatus.APPROVED,
                    resolution_note="Dəvət qəbul edildiyi üçün üzvlük aktivləşdi.",
                    responded_by=request.user,
                    responded_at=now,
                    updated_at=now,
                )
                _close_other_pending_student_requests(
                    user=request.user,
                    accepted_organization=organization,
                    responded_by=request.user,
                )

            request.session["active_organization"] = organization.slug
            create_audit_log(
                user=request.user,
                organization=organization,
                action="update",
                resource_type="membership_invite",
                resource_id=invite_membership.id,
                resource_repr=f"{request.user.username} accepted invite",
                old_values={"status": "pending"},
                new_values={"status": "accepted"},
                request=request,
            )
            messages.success(request, f"{organization.name} təşkilatına {invite_role_label} kimi qoşuldunuz.")
            return redirect(back_url)

        if action == "reject":
            organization = invite_membership.organization
            invite_membership.delete()
            create_audit_log(
                user=request.user,
                organization=organization,
                action="delete",
                resource_type="membership_invite",
                resource_id=invite_id,
                resource_repr=f"{request.user.username} rejected invite",
                old_values={"status": "pending"},
                new_values={"status": "rejected"},
                request=request,
            )
            messages.info(request, f"{organization.name} tərəfindən göndərilən {invite_role_label} dəvəti rədd edildi.")
            return redirect(back_url)

    messages.error(request, "Naməlum əməliyyat.")
    return redirect(back_url)
