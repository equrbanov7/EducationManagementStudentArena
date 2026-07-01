"""Profil "manage-roles" bölməsi üçün context-fragment qurucusu."""

from django.core.paginator import Paginator
from django.db.models import Q
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.accounts.views._helpers.formatting import _append_query_params, _query_string
from apps.accounts.views._helpers.rbac import (
    _assignable_profile_roles_for_user,
    _decorate_manage_role_profiles,
)
from apps.accounts.views._helpers.tenant import _bind_active_role_context, _get_active_organization


def build_manage_roles_section(request, section, *, capabilities):
    """Köhnə inline bloku ilə eyni: `section` dict-ini doldurub qaytarır."""
    manage_roles_search = request.GET.get("manage_roles_search", "")
    manage_roles_org = _get_active_organization(request)
    _bind_active_role_context(
        request.user,
        manage_roles_org,
        memberships=getattr(request, "org_memberships", []),
        permissions=getattr(request, "org_permissions", []),
    )
    manage_roles_user_level = request.user._highest_role_level() if hasattr(request.user, "_highest_role_level") else 0
    assignable_roles = _assignable_profile_roles_for_user(request.user)
    section.update(
        {
            "search_query": manage_roles_search,
            "organization": manage_roles_org,
            "assignable_roles": assignable_roles,
            "post_next_url": _append_query_params(
                reverse("accounts:profile"),
                section="manage-roles",
                manage_roles_search=manage_roles_search,
            ),
        }
    )

    if manage_roles_org is None:
        section["access_denied_message"] = "Rol idarəetməsi üçün aktiv təşkilat tapılmadı."
        manage_role_profiles = UserProfile.objects.none()
    else:
        manage_role_profiles = (
            UserProfile.objects.filter(
                user__memberships__organization=manage_roles_org,
                user__memberships__is_active=True,
            )
            .select_related("user")
            .prefetch_related("user__memberships__role")
            .distinct()
        )

        # Include the requesting superadmin's own profile even without a formal membership
        if capabilities["is_superadmin"] and not manage_role_profiles.filter(user=request.user).exists():
            own_profile_qs = (
                UserProfile.objects.filter(user=request.user)
                .select_related("user")
                .prefetch_related("user__memberships__role")
                .distinct()
            )
            manage_role_profiles = (manage_role_profiles | own_profile_qs).distinct()

    if manage_roles_search:
        manage_role_profiles = manage_role_profiles.filter(
            Q(user__username__icontains=manage_roles_search)
            | Q(user__email__icontains=manage_roles_search)
            | Q(user__first_name__icontains=manage_roles_search)
            | Q(user__last_name__icontains=manage_roles_search)
        )

    manage_roles_page = request.GET.get("manage_roles_page")
    manage_roles_page_obj = Paginator(manage_role_profiles.order_by("user__username"), 12).get_page(manage_roles_page)
    _decorate_manage_role_profiles(
        manage_roles_page_obj.object_list,
        actor_level=manage_roles_user_level,
        is_superadmin=capabilities["is_superadmin"],
        organization=manage_roles_org,
        actor_user=request.user,
    )

    section["profiles"] = manage_roles_page_obj
    section["profiles_pagination_query"] = _query_string(
        section="manage-roles",
        manage_roles_search=manage_roles_search,
    )

    return section
