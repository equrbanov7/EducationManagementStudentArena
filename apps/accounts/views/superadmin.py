"""
Superadmin views for organization oversight.
"""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.notifications.models import NotificationType
from apps.notifications.services import create_notification
from apps.organizations.models import Organization

from ._helpers import (
    _append_query_params,
    _build_user_organization_access_rows,
    _get_active_organization,
    _is_superadmin_user,
    _resolve_next_url,
)

logger = logging.getLogger(__name__)
User = get_user_model()


def _notify_org_owner_of_approval(org, approved_by, *, approved: bool, reason: str = ""):
    """Send an in-app notification to the organization owner about approval outcome."""
    try:
        if approved:
            title = f"Təşkilatınız təsdiqləndi: {org.name}"
            message = (
                f'"{org.name}" təşkilatı superadmin tərəfindən təsdiqləndi. '
                "İndi bütün funksiyalardan istifadə edə bilərsiniz."
            )
        else:
            title = f"Təşkilat müraciəti rədd edildi: {org.name}"
            message = f'"{org.name}" təşkilatı superadmin tərəfindən rədd edildi.'
            if reason:
                message += f" Səbəb: {reason}"

        create_notification(
            recipient=org.owner,
            title=title,
            message=message,
            link=reverse("accounts:profile"),
            notification_type=NotificationType.APPROVAL,
        )
    except Exception:
        logger.exception(
            "Failed to send org approval notification to owner %s for org %s",
            org.owner_id,
            org.pk,
        )


def _notify_superadmins_of_pending_org(org):
    """Notify all superadmin users that a new organization is awaiting approval."""
    try:
        superadmins = list(User.objects.filter(is_superuser=True, is_active=True))
        if not superadmins:
            return

        link = _append_query_params(
            reverse("accounts:profile"),
            section="superadmin-organizations",
        )
        title = f"Yeni təşkilat müraciəti: {org.name}"
        message = f'"{org.name}" adlı yeni təşkilat superadmin təsdiqi gözləyir. ' f"Növ: {org.get_org_type_display()}."

        for superadmin in superadmins:
            create_notification(
                recipient=superadmin,
                title=title,
                message=message,
                link=link,
                notification_type=NotificationType.APPROVAL,
            )
    except Exception:
        logger.exception("Failed to send pending-org notifications for org %s", org.pk)


@login_required
def superadmin_organizations(request):
    """
    Superadmin-only view showing all organizations with filtering, search and bulk operations.
    """
    if not _is_superadmin_user(request.user):
        from django.http import HttpResponseForbidden

        return HttpResponseForbidden("Bu bölməyə yalnız superadminlər daxil ola bilər.")

    profile_next_url = _append_query_params(
        reverse("accounts:profile"),
        section="superadmin-organizations",
    )
    fallback_next_url = reverse("accounts:superadmin_organizations")

    if request.method == "POST":
        organization = get_object_or_404(Organization, id=request.POST.get("organization_id"))
        action = request.POST.get("action")
        reason = (request.POST.get("reason") or "").strip()
        next_url = _resolve_next_url(request, fallback_next_url)

        if action == "approve":
            # Approve a pending organization: set status to active.
            if organization.status != "pending":
                messages.warning(request, "Bu təşkilat artıq gözləmə vəziyyətində deyil.")
            else:
                organization.status = "active"
                organization.is_active = True
                organization.save(update_fields=["status", "is_active", "updated_at"])
                _notify_org_owner_of_approval(organization, request.user, approved=True)
                messages.success(
                    request,
                    f'"{organization.name}" təşkilatı uğurla təsdiqləndi.',
                )

        elif action == "reject":
            # Reject and deactivate a pending organization.
            if organization.status not in {"pending", "active"}:
                messages.warning(request, "Bu əməliyyat mövcud vəziyyətdə tətbiq oluna bilməz.")
            else:
                organization.status = "suspended"
                organization.is_active = False
                organization.suspended_at = timezone.now()
                organization.suspension_reason = reason or "Superadmin tərəfindən rədd edildi."
                organization.save(
                    update_fields=[
                        "status",
                        "is_active",
                        "suspended_at",
                        "suspension_reason",
                        "updated_at",
                    ]
                )
                _notify_org_owner_of_approval(organization, request.user, approved=False, reason=reason)
                messages.success(
                    request,
                    f'"{organization.name}" təşkilatı rədd edildi.',
                )

        elif action == "suspend":
            organization.status = "suspended"
            organization.is_active = False
            organization.suspended_at = timezone.now()
            organization.suspension_reason = reason
            organization.save(
                update_fields=[
                    "status",
                    "is_active",
                    "suspended_at",
                    "suspension_reason",
                    "updated_at",
                ]
            )
            messages.success(
                request,
                pgettext_lazy("accounts.superadmin_orgs.message", "organization_suspended")
                % {"organization_name": organization.name},
            )
        elif action == "unsuspend":
            organization.status = "active"
            organization.is_active = True
            organization.suspended_at = None
            organization.suspension_reason = ""
            organization.save(
                update_fields=[
                    "status",
                    "is_active",
                    "suspended_at",
                    "suspension_reason",
                    "updated_at",
                ]
            )
            messages.success(
                request,
                pgettext_lazy("accounts.superadmin_orgs.message", "organization_unsuspended")
                % {"organization_name": organization.name},
            )
        else:
            messages.error(request, pgettext_lazy("accounts.superadmin_orgs.message", "unknown_action"))

        return redirect(next_url)

    search_query = request.GET.get("search", "").strip()
    org_type_filter = request.GET.get("org_type", "").strip().lower()
    status_filter = request.GET.get("status", "").strip().lower()

    organizations = (
        Organization.objects.filter(owner__is_active=True)
        .select_related("owner")
        .annotate(active_member_count=Count("memberships", filter=Q(memberships__is_active=True)))
        .order_by("-created_at")
    )

    if search_query:
        organizations = organizations.filter(
            Q(name__icontains=search_query)
            | Q(slug__icontains=search_query)
            | Q(organization_identifier__icontains=search_query)
            | Q(license_identifier__icontains=search_query)
            | Q(owner__username__icontains=search_query)
            | Q(owner__email__icontains=search_query)
        )

    if org_type_filter:
        organizations = organizations.filter(org_type=org_type_filter)

    if status_filter == "active":
        organizations = organizations.filter(is_active=True, status="active")
    elif status_filter == "pending":
        organizations = organizations.filter(status="pending")
    elif status_filter == "suspended":
        organizations = organizations.filter(status="suspended")
    elif status_filter == "inactive":
        organizations = organizations.filter(is_active=False)

    # Always annotate pending count for the badge in navigation.
    pending_count = Organization.objects.filter(status="pending", owner__is_active=True).count()

    paginator = Paginator(organizations, 20)
    page_number = request.GET.get("page")
    organizations_page = paginator.get_page(page_number)

    context = {
        "organizations": organizations_page,
        "organization_access_rows": _build_user_organization_access_rows(
            request.user,
            active_organization=_get_active_organization(request),
            include_active_superadmin_org=True,
            profile_section="superadmin-organizations",
        ),
        "search_query": search_query,
        "org_type_filter": org_type_filter,
        "status_filter": status_filter,
        "pending_count": pending_count,
        "post_next_url": profile_next_url,
    }
    return render(request, "accounts/superadmin_organizations.html", context)
