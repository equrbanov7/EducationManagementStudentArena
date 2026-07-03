"""
Student organization join-request view.

Lets applicants (students, teachers, staff) submit or clear requests to join
an organization. Behavior is identical to the pre-refactor implementation.
"""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from apps.notifications.models import (
    StudentOrganizationRequest,
    StudentOrganizationRequestStatus,
)
from apps.notifications.public import notify_org_admins_of_new_request
from core.constants import OrganizationType

from ...models import UserProfile
from .._helpers import (
    STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH,
    STUDENT_PENDING_INVITE_TITLE,
    _membership_request_role_label,
    _membership_request_role_type_for_profile_role,
    _pending_student_request_queryset,
    _render_profile_section,
    _resolve_next_url,
    _role_capabilities,
    _set_student_org_request_status,
    _sync_profile_pending_request_snapshot,
)

User = get_user_model()
logger = logging.getLogger(__name__)


@login_required
def student_organization_request(request):
    """Allow applicants to send or clear organization join requests."""
    from apps.organizations.models import Membership, Organization
    from core.rls import bypass_rls

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    capabilities = _role_capabilities(request.user, profile)
    request_role_type = _membership_request_role_type_for_profile_role(profile.role)
    request_role_label = _membership_request_role_label(request_role_type).lower()
    default_next = f"{reverse('accounts:profile')}?section=student-organization-request"
    if request.method == "POST":
        action = (request.POST.get("action") or "submit_request").strip().lower()
        next_url = _resolve_next_url(request, default_next)

        if action == "clear_request":
            request_id = (request.POST.get("request_id") or "").strip()
            target_request = None
            # The student may not have an active org context yet, so RLS
            # would hide StudentOrganizationRequest rows.  Bypass RLS.
            with bypass_rls():
                if request_id:
                    target_request = (
                        _pending_student_request_queryset(
                            user=request.user,
                            statuses=[StudentOrganizationRequestStatus.PENDING],
                        )
                        .filter(id=request_id)
                        .select_related("organization")
                        .first()
                    )
                else:
                    organization_id = (request.POST.get("organization_id") or "").strip()
                    if organization_id:
                        target_request = (
                            _pending_student_request_queryset(
                                user=request.user,
                                statuses=[StudentOrganizationRequestStatus.PENDING],
                            )
                            .filter(organization_id=organization_id)
                            .select_related("organization")
                            .first()
                        )

            if target_request is None:
                messages.error(request, pgettext("accounts.org.message", "Ləğv ediləcək aktiv müraciət tapılmadı."))
                return redirect(next_url)

            _set_student_org_request_status(
                request_obj=target_request,
                status=StudentOrganizationRequestStatus.CANCELLED,
                note="Müraciət istifadəçi tərəfindən ləğv edildi.",
                responded_by=request.user,
            )
            _sync_profile_pending_request_snapshot(profile)
            messages.success(
                request,
                pgettext("accounts.org.message", "{org} üçün müraciət ləğv edildi.").format(
                    org=target_request.organization.name
                ),
            )
            return redirect(next_url)

        if "student-organization-request" not in capabilities["allowed_sections"]:
            messages.error(
                request,
                pgettext(
                    "accounts.org.message",
                    "Bu bölmə yalnız tələbə, müəllim və staff hesabları üçün aktivdir.",
                ),
            )
            return redirect("accounts:profile")

        if action == "submit_request":
            if profile.organization_id:
                messages.error(
                    request,
                    pgettext(
                        "accounts.org.message",
                        "Hazırda təşkilata bağlısınız. Yeni müraciət üçün əvvəlcə çıxış edin.",
                    ),
                )
                return redirect(next_url)

            organization_id = (request.POST.get("organization_id") or "").strip()
            if not organization_id:
                messages.error(request, pgettext("accounts.org.message", "Müraciət üçün bir təşkilat seçin."))
                return redirect(next_url)

            target_org = (
                Organization.objects.filter(
                    id=organization_id,
                    is_active=True,
                    status="active",
                )
                .exclude(org_type=OrganizationType.INDIVIDUAL)
                .first()
            )
            if target_org is None:
                messages.error(
                    request, pgettext("accounts.org.message", "Seçilən təşkilat tapılmadı və ya aktiv deyil.")
                )
                return redirect(next_url)

            # The student may not belong to any org yet, so RLS would
            # block Membership and StudentOrganizationRequest queries.
            with bypass_rls():
                existing_pending_invite = Membership.objects.filter(
                    user=request.user,
                    organization=target_org,
                    is_active=False,
                    title=STUDENT_PENDING_INVITE_TITLE,
                ).exists()
            if existing_pending_invite:
                messages.info(
                    request,
                    pgettext(
                        "accounts.org.message",
                        "Bu təşkilatdan sizə artıq dəvət göndərilib. Profildə qəbul edə bilərsiniz.",
                    ),
                )
                return redirect(next_url)

            request_message = (request.POST.get("request_message") or "").strip()
            if len(request_message) > STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH:
                messages.error(
                    request,
                    pgettext("accounts.org.message", "Müraciət mesajı maksimum {max} simvol ola bilər.").format(
                        max=STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH
                    ),
                )
                return redirect(next_url)

            with bypass_rls():
                existing_pending = (
                    _pending_student_request_queryset(
                        user=request.user,
                        organization=target_org,
                        statuses=[StudentOrganizationRequestStatus.PENDING],
                    )
                    .filter(role_type=request_role_type)
                    .order_by("-created_at")
                    .first()
                )
                if existing_pending:
                    existing_pending.message = request_message
                    existing_pending.resolution_note = ""
                    existing_pending.responded_by = None
                    existing_pending.responded_at = None
                    existing_pending.save(
                        update_fields=[
                            "message",
                            "resolution_note",
                            "responded_by",
                            "responded_at",
                            "updated_at",
                        ]
                    )
                    target_request = existing_pending
                else:
                    target_request = StudentOrganizationRequest.objects.create(
                        user=request.user,
                        organization=target_org,
                        role_type=request_role_type,
                        message=request_message,
                        status=StudentOrganizationRequestStatus.PENDING,
                    )
                    try:
                        notify_org_admins_of_new_request(request_obj=target_request)
                    except Exception:
                        logger.exception("Failed to send new request notification")

                # Keep one pending row per user+organization for cleaner history and UI.
                duplicate_pending = (
                    _pending_student_request_queryset(
                        user=request.user,
                        organization=target_org,
                        statuses=[StudentOrganizationRequestStatus.PENDING],
                    )
                    .filter(role_type=request_role_type)
                    .exclude(id=target_request.id)
                )
                if duplicate_pending.exists():
                    now = timezone.now()
                    duplicate_pending.update(
                        status=StudentOrganizationRequestStatus.CANCELLED,
                        resolution_note="Yeni müraciət göndərildiyi üçün əvvəlki pending bağlandı.",
                        responded_by=request.user,
                        responded_at=now,
                        updated_at=now,
                    )

            profile.requested_organization = target_org
            profile.requested_organization_name = target_org.name
            profile.requested_organization_message = request_message
            profile.organization_type = target_org.org_type
            profile.save(
                update_fields=[
                    "requested_organization",
                    "requested_organization_name",
                    "requested_organization_message",
                    "organization_type",
                    "updated_at",
                ]
            )
            _sync_profile_pending_request_snapshot(profile)

            messages.success(
                request,
                pgettext(
                    "accounts.org.message", "{org} üçün {role} müraciətiniz göndərildi və təsdiq gözləyir."
                ).format(org=target_org.name, role=request_role_label),
            )
            return redirect(next_url)

        messages.error(request, pgettext("accounts.org.message", "Naməlum əməliyyat."))
        return redirect(next_url)

    if "student-organization-request" not in capabilities["allowed_sections"]:
        messages.error(
            request,
            pgettext(
                "accounts.org.message",
                "Bu bölmə yalnız tələbə, müəllim və staff hesabları üçün aktivdir.",
            ),
        )
        return redirect("accounts:profile")

    return _render_profile_section(request, "student-organization-request")
