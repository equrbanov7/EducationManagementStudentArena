"""Profil "role-assignment" bölməsi üçün context-fragment qurucusu."""

from django.core.paginator import Paginator
from django.db.models import Q
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.accounts.views._helpers.formatting import _append_query_params, _query_string
from apps.accounts.views._helpers.membership import _pending_student_request_queryset
from apps.notifications.models import StudentOrganizationRequestStatus


def build_role_assignment_section(
    request,
    section,
    *,
    management_org,
    management_can_assign_roles,
    management_min_level_ok,
    management_user_level,
    capabilities,
):
    """Köhnə inline bloku ilə eyni: `section` dict-ini doldurub qaytarır."""
    from apps.organizations.models import Membership, Role

    role_assignment_search = request.GET.get("q", request.GET.get("search", ""))
    role_assignment_unassigned_search = request.GET.get("unassigned_search", "")
    section.update(
        {
            "organization": management_org,
            "search_query": role_assignment_search,
            "unassigned_search_query": role_assignment_unassigned_search,
            "can_assign_roles": management_can_assign_roles,
            "post_next_url": _append_query_params(
                reverse("accounts:profile"),
                section="role-assignment",
                q=role_assignment_search,
                unassigned_search=role_assignment_unassigned_search,
                role_members_page=request.GET.get("role_members_page", ""),
                role_pending_page=request.GET.get("role_pending_page", ""),
            ),
        }
    )

    if management_org is None:
        section["access_denied_message"] = "Aktiv təşkilat tapılmadı."
    elif not management_min_level_ok:
        section["access_denied_message"] = "Bu bölmə üçün minimum müəllim və ya daha yüksək səviyyə tələb olunur."
    else:
        members = (
            Membership.objects.filter(organization=management_org, is_active=True)
            .select_related("user", "role")
            .order_by("-role__level", "user__username")
        )
        if not capabilities["is_superadmin"]:
            members = members.filter(role__level__lt=management_user_level)

        assignable_roles = Role.objects.filter(organization=management_org, is_active=True).order_by("-level")
        if not capabilities["is_superadmin"]:
            assignable_roles = assignable_roles.filter(level__lt=management_user_level)

        if role_assignment_search:
            members = members.filter(
                Q(user__username__icontains=role_assignment_search)
                | Q(user__email__icontains=role_assignment_search)
                | Q(user__first_name__icontains=role_assignment_search)
                | Q(user__last_name__icontains=role_assignment_search)
            )

        unassigned_users = UserProfile.objects.filter(user__is_active=True, organization__isnull=True).select_related(
            "user",
            "requested_organization",
        )
        if not capabilities["is_superadmin"]:
            pending_request_user_ids = _pending_student_request_queryset(
                organization=management_org,
                statuses=[StudentOrganizationRequestStatus.PENDING],
            ).values_list("user_id", flat=True)
            unassigned_users = unassigned_users.filter(
                Q(user_id__in=pending_request_user_ids)
                | Q(requested_organization=management_org)
                | Q(
                    requested_organization__isnull=True,
                    requested_organization_name__iexact=management_org.name,
                )
            )
        if role_assignment_unassigned_search:
            unassigned_users = unassigned_users.filter(
                Q(user__username__icontains=role_assignment_unassigned_search)
                | Q(user__email__icontains=role_assignment_unassigned_search)
                | Q(user__first_name__icontains=role_assignment_unassigned_search)
                | Q(user__last_name__icontains=role_assignment_unassigned_search)
            )

        role_assignment_members_page = request.GET.get("role_members_page")
        role_assignment_members_page_obj = Paginator(members, 12).get_page(role_assignment_members_page)

        role_assignment_pending_page = request.GET.get("role_pending_page")
        role_assignment_pending_page_obj = Paginator(unassigned_users.order_by("user__username"), 12).get_page(
            role_assignment_pending_page
        )

        section["members"] = role_assignment_members_page_obj
        section["assignable_roles"] = assignable_roles
        section["unassigned_users"] = role_assignment_pending_page_obj
        section["members_pagination_query"] = _query_string(
            section="role-assignment",
            q=role_assignment_search,
            unassigned_search=role_assignment_unassigned_search,
        )
        section["unassigned_pagination_query"] = _query_string(
            section="role-assignment",
            q=role_assignment_search,
            unassigned_search=role_assignment_unassigned_search,
        )

    return section
