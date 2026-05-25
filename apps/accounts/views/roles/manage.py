"""
Manage-roles view.

Organization-scoped multi-role assignment: effective roles are derived from
memberships in the active organization. Behavior is identical to the
pre-refactor single-file implementation.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import pgettext_lazy

from apps.organizations.models import Membership

from ...models import ProfileRole, UserProfile
from .._helpers import (
    PROFILE_ROLE_LABELS,
    PROFILE_ROLE_NAMES,
    _assignable_profile_roles_for_user,
    _bind_active_role_context,
    _decorate_manage_role_profiles,
    _extract_profile_roles_for_user,
    _get_active_organization,
    _is_superadmin_user,
    _render_profile_section,
    _resolve_next_url,
    _sync_user_role_memberships,
)

User = get_user_model()


@login_required
def manage_roles(request):
    """
    Organization-scoped multi-role assignment view.
    Effective roles are derived from memberships in the active organization.
    """
    is_superadmin = _is_superadmin_user(request.user)
    if not is_superadmin and not getattr(request.user, "is_admin_level", False):
        messages.error(request, pgettext_lazy("accounts.manage_roles.message", "admin_only"))
        return redirect("home")

    user_org = _get_active_organization(request)
    if not user_org:
        messages.error(request, pgettext_lazy("accounts.manage_roles.message", "active_organization_not_found"))
        return redirect("accounts:profile")

    _bind_active_role_context(
        request.user,
        user_org,
        memberships=getattr(request, "org_memberships", []),
        permissions=getattr(request, "org_permissions", []),
    )
    actor_level = request.user._highest_role_level() if hasattr(request.user, "_highest_role_level") else 0
    assignable_roles = _assignable_profile_roles_for_user(request.user)
    assignable_role_names = {name for name, _ in assignable_roles}
    can_self_manage_extra_roles = is_superadmin or getattr(user_org, "owner_id", None) == request.user.id

    if request.method == "POST":
        user_id = request.POST.get("user_id")
        action = request.POST.get("action")  # "assign" or "remove"
        next_url = _resolve_next_url(request, reverse("accounts:manage_roles"))

        if not user_id:
            messages.error(request, pgettext_lazy("accounts.manage_roles.message", "user_not_selected"))
            return redirect(next_url)

        target_user = get_object_or_404(User, id=user_id)

        target_is_superadmin = target_user.is_superuser or getattr(target_user, "is_superadmin", False)
        target_has_membership = Membership.objects.filter(
            user=target_user,
            organization=user_org,
            is_active=True,
        ).exists()
        if not target_has_membership and not target_is_superadmin:
            messages.error(request, pgettext_lazy("accounts.manage_roles.message", "manage_only_own_org_users"))
            return redirect(next_url)

        _bind_active_role_context(target_user, user_org)
        target_level = target_user._highest_role_level() if hasattr(target_user, "_highest_role_level") else 0
        if target_user == request.user and not can_self_manage_extra_roles:
            messages.error(
                request, "Öz rol kombinasiyanızı dəyişmək üçün təşkilat sahibi və ya superadmin olmalısınız."
            )
            return redirect(next_url)
        if not is_superadmin and target_user != request.user and target_level >= actor_level:
            messages.error(
                request, pgettext_lazy("accounts.manage_roles.message", "insufficient_level_for_target_user")
            )
            return redirect(next_url)

        selected_role_names = set(request.POST.getlist("role_names"))
        single_role_name = (request.POST.get("role_name") or "").strip()
        if single_role_name:
            selected_role_names.add(single_role_name)

        if action == "remove":
            selected_role_names = {ProfileRole.MEMBER}
        if not selected_role_names:
            selected_role_names = {ProfileRole.MEMBER}

        invalid_roles = selected_role_names - PROFILE_ROLE_NAMES
        if invalid_roles:
            messages.error(request, pgettext_lazy("accounts.manage_roles.message", "invalid_roles_selected"))
            return redirect(next_url)

        disallowed_roles = selected_role_names - assignable_role_names
        if disallowed_roles:
            messages.error(request, pgettext_lazy("accounts.manage_roles.message", "not_allowed_to_assign_some_roles"))
            return redirect(next_url)

        current_roles = set(_extract_profile_roles_for_user(target_user))
        protected_roles = current_roles - assignable_role_names
        effective_roles = protected_roles | selected_role_names

        if not effective_roles:
            effective_roles = {ProfileRole.MEMBER}

        added_roles = effective_roles - current_roles
        removed_roles = current_roles - effective_roles

        target_profile, _ = UserProfile.objects.get_or_create(user=target_user)

        with transaction.atomic():
            final_memberships = _sync_user_role_memberships(
                target_user,
                user_org,
                effective_roles,
                actor=request.user,
                editable_role_names=assignable_role_names,
            )
            _bind_active_role_context(target_user, user_org, memberships=final_memberships)
            refreshed_roles = _extract_profile_roles_for_user(target_user)
            if not refreshed_roles:
                refreshed_roles = [ProfileRole.MEMBER]
            primary_role = max(refreshed_roles, key=lambda role_name: ProfileRole.LEVELS.get(role_name, 0))
            target_profile.role = primary_role
            target_profile.save(update_fields=["role", "updated_at"])

        assigned_labels = [PROFILE_ROLE_LABELS.get(role_name, role_name) for role_name in sorted(effective_roles)]
        added_labels = [PROFILE_ROLE_LABELS.get(role_name, role_name) for role_name in sorted(added_roles)]
        removed_labels = [PROFILE_ROLE_LABELS.get(role_name, role_name) for role_name in sorted(removed_roles)]
        diff_parts = []
        if added_labels:
            diff_parts.append("Əlavə edildi: " + ", ".join(added_labels))
        if removed_labels:
            diff_parts.append("Silindi: " + ", ".join(removed_labels))
        if not diff_parts:
            diff_parts.append("Dəyişiklik yoxdur.")

        messages.success(
            request,
            (
                pgettext_lazy("accounts.manage_roles.message", "roles_updated_for_user")
                % {"username": target_user.username, "roles": ", ".join(assigned_labels)}
            )
            + " "
            + " / ".join(diff_parts),
        )
        return redirect(next_url)

    profiles = (
        UserProfile.objects.filter(
            user__memberships__organization=user_org,
            user__memberships__is_active=True,
        )
        .select_related("user")
        .prefetch_related("user__memberships__role")
        .distinct()
    )

    # Include the requesting superadmin's own profile even if they have no formal membership
    if is_superadmin and not profiles.filter(user=request.user).exists():
        own_profile_qs = (
            UserProfile.objects.filter(user=request.user)
            .select_related("user")
            .prefetch_related("user__memberships__role")
            .distinct()
        )
        profiles = (profiles | own_profile_qs).distinct()

    # Search
    search = request.GET.get("search", "")
    if search:
        profiles = profiles.filter(
            Q(user__username__icontains=search)
            | Q(user__email__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
        )

    profiles_page = request.GET.get("manage_roles_page")
    profiles_page_obj = Paginator(profiles.order_by("user__username"), 12).get_page(profiles_page)
    _decorate_manage_role_profiles(
        profiles_page_obj.object_list,
        actor_level=actor_level,
        is_superadmin=is_superadmin,
        organization=user_org,
        actor_user=request.user,
    )

    return _render_profile_section(request, "manage-roles")
