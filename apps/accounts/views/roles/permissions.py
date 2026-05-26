"""
Permission-editor view.

Organization-scoped role permission editor with add/remove enforcement
(grantable-permission checks, lower-role-only restriction). Behavior is
identical to the pre-refactor single-file implementation.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext_lazy

from .._helpers import (
    _collect_actor_permissions,
    _ensure_profile_admin_membership,
    _get_active_organization,
    _is_superadmin_user,
    _permission_is_grantable,
    _render_profile_section,
)

User = get_user_model()


@login_required
def permission_editor(request):
    """Organization-scoped permission editor with add/remove enforcement."""
    from apps.organizations.models import Role
    from apps.organizations.permissions import get_all_permissions, has_permission
    from apps.organizations.services import create_audit_log, get_user_org_role_level

    org = _get_active_organization(request)
    if not org:
        messages.error(request, pgettext_lazy("accounts.permission_editor.message", "active_organization_not_found"))
        return redirect("accounts:profile")

    _ensure_profile_admin_membership(request.user, org)

    is_superadmin = _is_superadmin_user(request.user)
    user_level = 999 if is_superadmin else get_user_org_role_level(request.user, org)
    actor_permissions, grantable_permissions = _collect_actor_permissions(request.user, org)

    can_manage_permissions = is_superadmin or has_permission(list(actor_permissions), "role.assign")
    if not is_superadmin and not can_manage_permissions:
        messages.error(request, pgettext_lazy("accounts.permission_editor.message", "role_assign_permission_required"))
        return redirect("accounts:profile")

    roles = Role.objects.filter(organization=org, is_active=True).order_by("-level")
    if not is_superadmin:
        roles = roles.filter(level__lt=user_level)

    selected_role = None
    selected_role_id = request.GET.get("role")
    if request.method == "POST":
        selected_role_id = request.POST.get("role_id")
        action = request.POST.get("action")
        selected_role = get_object_or_404(Role, id=selected_role_id, organization=org, is_active=True)
        next_url = (request.POST.get("next") or "").strip()

        if not is_superadmin and selected_role.level >= user_level:
            messages.error(
                request, pgettext_lazy("accounts.permission_editor.message", "manage_lower_role_permissions_only")
            )
            return redirect(f"{request.path}?role={selected_role.id}")

        all_permissions = set(get_all_permissions())
        role_permissions = list(selected_role.permissions or [])
        role_permissions_set = set(role_permissions)
        old_permissions = sorted(role_permissions_set)
        result_message = ""

        if next_url and not url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            next_url = ""

        def _safe_redirect():
            return redirect(next_url or f"{request.path}?role={selected_role.id}")

        if action in {"add", "remove"}:
            selected_permission = request.POST.get("permission")
            if selected_permission not in all_permissions:
                messages.error(
                    request, pgettext_lazy("accounts.permission_editor.message", "invalid_permission_selection")
                )
                return _safe_redirect()

            if action == "add":
                if (
                    not _permission_is_grantable(selected_permission, actor_permissions, grantable_permissions)
                    and not is_superadmin
                ):
                    messages.error(
                        request,
                        pgettext_lazy(
                            "accounts.permission_editor.message", "grant_only_owned_or_grantable_permissions"
                        ),
                    )
                    return _safe_redirect()
                role_permissions_set.add(selected_permission)
                result_message = pgettext_lazy("accounts.permission_editor.message", "permission_added") % {
                    "permission": selected_permission
                }
            else:
                role_permissions_set.discard(selected_permission)
                result_message = pgettext_lazy("accounts.permission_editor.message", "permission_removed") % {
                    "permission": selected_permission
                }
        elif action in {"bulk_add", "bulk_remove"}:
            selected_permissions = [perm for perm in request.POST.getlist("permissions") if perm]
            selected_permissions = list(dict.fromkeys(selected_permissions))
            if not selected_permissions:
                messages.error(request, "Əməliyyat üçün ən azı bir permission seçin.")
                return _safe_redirect()

            invalid_permissions = [perm for perm in selected_permissions if perm not in all_permissions]
            if invalid_permissions:
                messages.error(
                    request, pgettext_lazy("accounts.permission_editor.message", "invalid_permission_selection")
                )
                return _safe_redirect()

            if action == "bulk_add":
                if not is_superadmin:
                    not_grantable = [
                        perm
                        for perm in selected_permissions
                        if not _permission_is_grantable(perm, actor_permissions, grantable_permissions)
                    ]
                    if not_grantable:
                        messages.error(
                            request,
                            pgettext_lazy(
                                "accounts.permission_editor.message", "grant_only_owned_or_grantable_permissions"
                            ),
                        )
                        return _safe_redirect()

                before_count = len(role_permissions_set)
                role_permissions_set.update(selected_permissions)
                changed_count = len(role_permissions_set) - before_count
                result_message = f"{changed_count} permission əlavə edildi."
            else:
                before_count = len(role_permissions_set)
                role_permissions_set.difference_update(selected_permissions)
                changed_count = before_count - len(role_permissions_set)
                result_message = f"{changed_count} permission silindi."
        else:
            messages.error(request, pgettext_lazy("accounts.permission_editor.message", "unknown_action"))
            return _safe_redirect()

        if sorted(role_permissions_set) == old_permissions:
            messages.success(request, result_message)
            return _safe_redirect()

        selected_role.permissions = sorted(role_permissions_set)
        selected_role.save(update_fields=["permissions", "updated_at"])

        create_audit_log(
            user=request.user,
            organization=org,
            action="update",
            resource_type="role",
            resource_id=selected_role.id,
            resource_repr=selected_role.display_name,
            old_values={"permissions": old_permissions},
            new_values={"permissions": selected_role.permissions},
            request=request,
        )

        messages.success(request, result_message)
        return _safe_redirect()

    if selected_role_id:
        selected_role = roles.filter(id=selected_role_id).first()
    if selected_role is None:
        selected_role = roles.first()

    return _render_profile_section(request, "permission-editor")
