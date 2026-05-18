"""
Role management views: manage roles, role assignment, permission editor.
"""

from uuid import UUID

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext_lazy

from apps.notifications.models import StudentOrganizationRequestStatus
from apps.organizations.models import Membership

from ..models import ProfileRole, UserProfile
from ._helpers import (
    PROFILE_ROLE_LABELS,
    PROFILE_ROLE_NAMES,
    ROLE_ASSIGNMENT_OPERATION_TOKEN_MAX_AGE_SECONDS,
    ROLE_ASSIGNMENT_OPERATION_TOKEN_SALT,
    _append_query_params,
    _assignable_profile_roles_for_user,
    _bind_active_role_context,
    _close_other_pending_student_requests,
    _collect_actor_permissions,
    _decorate_manage_role_profiles,
    _ensure_profile_admin_membership,
    _extract_profile_roles_for_user,
    _get_active_organization,
    _is_superadmin_user,
    _map_org_role_to_profile_role,
    _normalized_org_name,
    _pending_student_request_queryset,
    _permission_is_grantable,
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

    return redirect(reverse("accounts:profile") + "?section=manage-roles")


@login_required
def role_assignment(request):
    """Organization-scoped role assignment UI with strict server-side permission checks."""
    from apps.organizations.models import Membership, Role
    from apps.organizations.permissions import has_permission
    from apps.organizations.services import create_audit_log, get_user_org_role_level

    org = _get_active_organization(request)
    if not org:
        messages.error(request, pgettext_lazy("accounts.role_assignment.message", "active_organization_not_found"))
        return redirect("accounts:profile")

    _ensure_profile_admin_membership(request.user, org)

    is_superadmin = _is_superadmin_user(request.user)
    actor_memberships = Membership.objects.filter(user=request.user, organization=org, is_active=True).select_related(
        "role"
    )
    actor_primary_membership = actor_memberships.order_by("-role__level").first()
    actor_primary_level = (
        999 if is_superadmin else (actor_primary_membership.role.level if actor_primary_membership else 0)
    )
    actor_permissions, _ = _collect_actor_permissions(request.user, org)
    actor_permission_list = list(actor_permissions)
    can_manage_members = (
        is_superadmin
        or has_permission(actor_permission_list, "role.assign")
        or has_permission(actor_permission_list, "org.manage_members")
    )
    can_assign_owner_roles = is_superadmin or has_permission(actor_permission_list, "org.owner.assign")
    can_assign_admin_roles = (
        is_superadmin or can_assign_owner_roles or has_permission(actor_permission_list, "org.admin.assign")
    )

    def _parse_uuid(raw_value):
        try:
            return UUID(str(raw_value))
        except (TypeError, ValueError, AttributeError):
            return None

    def _is_owner_role(role):
        if role is None:
            return False
        role_name = (role.name or "").strip().lower()
        return role.level >= 100 or "owner" in role_name or role_name in {"rector", "director", "manager"}

    def _is_admin_role(role):
        if role is None:
            return False
        role_name = (role.name or "").strip().lower()
        return (
            _is_owner_role(role)
            or role.level >= ProfileRole.LEVELS.get(ProfileRole.ORG_ADMIN, 80)
            or "admin" in role_name
        )

    def _owner_membership_queryset():
        return Membership.objects.filter(
            organization=org,
            is_active=True,
            role__is_active=True,
        ).filter(
            Q(role__level__gte=100)
            | Q(role__name__icontains="owner")
            | Q(role__name__iexact="rector")
            | Q(role__name__iexact="director")
            | Q(role__name__iexact="manager")
        )

    def _wants_json_response():
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return True
        accepted = request.headers.get("Accept", "")
        return "application/json" in accepted.lower()

    def _resolve_request_id():
        raw_request_id = (
            getattr(request, "request_id", None)
            or request.META.get("HTTP_X_REQUEST_ID")
            or request.META.get("HTTP_X_CORRELATION_ID")
        )
        return str(raw_request_id).strip() if raw_request_id else ""

    def _build_role_assignment_audit_values(
        *,
        status,
        action_name,
        target_role=None,
        target_membership=None,
        target_user=None,
        old_role=None,
        reason_code="",
        extra=None,
    ):
        resolved_target_user = target_user or (target_membership.user if target_membership is not None else None)
        resolved_old_role = old_role or (target_membership.role if target_membership is not None else None)

        values = {
            "status": status,
            "action_type": action_name or request.POST.get("action", ""),
            "actor_user_id": str(request.user.id),
            "org_id": str(org.id),
            "target_user_id": str(resolved_target_user.id) if resolved_target_user is not None else "",
            "membership_id": str(target_membership.id) if target_membership is not None else "",
            "old_role_id": str(resolved_old_role.id) if resolved_old_role is not None else "",
            "old_role_name": (resolved_old_role.display_name if resolved_old_role is not None else ""),
            "new_role_id": str(target_role.id) if target_role is not None else "",
            "new_role_name": (target_role.display_name if target_role is not None else ""),
            "reason_code": reason_code or "",
            "request_id": _resolve_request_id(),
        }
        if extra:
            values.update(extra)
        return values

    def _deny_assignment(
        reason_code,
        reason_message,
        *,
        status=403,
        action_name=None,
        target_membership=None,
        target_user=None,
        target_role=None,
        extra=None,
        force_json=False,
    ):
        resource_type = "role_assignment"
        resource_id = ""
        resource_repr = action_name or (request.POST.get("action", "") if request.method == "POST" else "")

        if target_membership is not None:
            resource_type = "membership"
            resource_id = str(target_membership.id)
            resource_repr = str(target_membership)
        elif target_user is not None:
            resource_type = "user"
            resource_id = str(target_user.id)
            resource_repr = target_user.username

        denied_values = _build_role_assignment_audit_values(
            status="denied",
            action_name=action_name,
            target_role=target_role,
            target_membership=target_membership,
            target_user=target_user,
            old_role=(target_membership.role if target_membership is not None else None),
            reason_code=reason_code,
            extra={
                "action": action_name or request.POST.get("action", ""),
                "active_organization_id": str(org.id),
                "requested_membership_id": request.POST.get("membership_id"),
                "requested_user_id": request.POST.get("user_id"),
                "requested_role_id": request.POST.get("role_id"),
                "reason": reason_message,
            },
        )
        if target_role is not None:
            denied_values["requested_role_name"] = target_role.name
            denied_values["requested_role_level"] = target_role.level
        if extra:
            denied_values.update(extra)

        create_audit_log(
            user=request.user,
            organization=org,
            action="update",
            resource_type=resource_type,
            resource_id=resource_id,
            resource_repr=resource_repr,
            old_values=None,
            new_values=denied_values,
            reason=reason_message,
            request=request,
        )

        if force_json or _wants_json_response():
            payload = {
                "success": False,
                "reason_code": reason_code,
                "message": reason_message,
            }
            if extra:
                payload["details"] = extra
            return JsonResponse(payload, status=status)

        if status == 403:
            return HttpResponseForbidden(reason_message)
        return HttpResponse(reason_message, status=status)

    def _validate_operation_token(*, action_name, target_role, target_membership=None, target_user=None):
        raw_token = (request.POST.get("operation_token") or "").strip()
        if not raw_token:
            return None

        try:
            operation_signer = TimestampSigner(salt=ROLE_ASSIGNMENT_OPERATION_TOKEN_SALT)
            payload = operation_signer.unsign_object(
                raw_token,
                max_age=ROLE_ASSIGNMENT_OPERATION_TOKEN_MAX_AGE_SECONDS,
            )
        except SignatureExpired:
            return _deny_assignment(
                "operation_token_expired",
                "Əməliyyat tokeninin vaxtı bitib. Yenidən təsdiqləyin.",
                status=409,
                action_name=action_name,
                target_membership=target_membership,
                target_user=target_user,
                target_role=target_role,
            )
        except BadSignature:
            return _deny_assignment(
                "operation_token_invalid",
                "Əməliyyat tokeni etibarsızdır.",
                action_name=action_name,
                target_membership=target_membership,
                target_user=target_user,
                target_role=target_role,
            )

        expected_target_id = str(target_membership.id if target_membership is not None else target_user.id)
        if (
            str(payload.get("actor_user_id")) != str(request.user.id)
            or str(payload.get("organization_id")) != str(org.id)
            or str(payload.get("target_action")) != str(action_name)
            or str(payload.get("target_id")) != expected_target_id
            or str(payload.get("role_id")) != str(target_role.id)
        ):
            return _deny_assignment(
                "operation_token_mismatch",
                "Təsdiq tokeni seçilmiş əməliyyatla uyğun gəlmir.",
                action_name=action_name,
                target_membership=target_membership,
                target_user=target_user,
                target_role=target_role,
            )

        return None

    def _enforce_role_change_guards(*, action_name, target_membership, target_role):
        if target_membership.user_id == request.user.id:
            return _deny_assignment(
                "self_role_change_forbidden",
                "Öz rolunuzu dəyişdirə bilməzsiniz.",
                action_name=action_name,
                target_membership=target_membership,
                target_role=target_role,
            )

        target_primary_level = get_user_org_role_level(target_membership.user, org)
        if not is_superadmin and target_primary_level >= actor_primary_level:
            return _deny_assignment(
                "target_level_not_lower_than_actor",
                "Yalnız sizdən aşağı səviyyəli üzvlərin rolunu dəyişə bilərsiniz.",
                action_name=action_name,
                target_membership=target_membership,
                target_role=target_role,
                extra={"target_primary_level": target_primary_level, "actor_primary_level": actor_primary_level},
            )

        if not is_superadmin and target_role.level >= actor_primary_level:
            return _deny_assignment(
                "requested_role_not_lower_than_actor",
                "Yalnız sizdən aşağı səviyyəli rolları təyin edə bilərsiniz.",
                action_name=action_name,
                target_membership=target_membership,
                target_role=target_role,
                extra={"actor_primary_level": actor_primary_level},
            )

        if (_is_owner_role(target_membership.role) or _is_owner_role(target_role)) and not can_assign_owner_roles:
            return _deny_assignment(
                "owner_role_assignment_permission_required",
                "`org.owner.assign` icazəsi olmadan owner səviyyəli rol təyini/dəyişimi qadağandır.",
                action_name=action_name,
                target_membership=target_membership,
                target_role=target_role,
            )

        if (
            (_is_admin_role(target_membership.role) or _is_admin_role(target_role))
            and not _is_owner_role(target_membership.role)
            and not _is_owner_role(target_role)
            and not can_assign_admin_roles
        ):
            return _deny_assignment(
                "admin_role_assignment_permission_required",
                "`org.admin.assign` icazəsi olmadan admin səviyyəli rol təyini/dəyişimi qadağandır.",
                action_name=action_name,
                target_membership=target_membership,
                target_role=target_role,
            )

        if _is_owner_role(target_membership.role) and not _is_owner_role(target_role):
            has_other_owner = _owner_membership_queryset().exclude(id=target_membership.id).exists()
            if not has_other_owner:
                return _deny_assignment(
                    "last_owner_must_remain",
                    "Təşkilatda ən az bir owner qalmalıdır.",
                    status=409,
                    action_name=action_name,
                    target_membership=target_membership,
                    target_role=target_role,
                )

        return None

    def _resolve_target_role(*, action_name, role_id):
        target_role_uuid = _parse_uuid(role_id)
        if target_role_uuid is None:
            return None, _deny_assignment("invalid_role_id", "Düzgün `role_id` göndərilməyib.", action_name=action_name)

        target_role = Role.objects.filter(id=target_role_uuid, is_active=True).first()
        if target_role is None:
            return None, _deny_assignment("role_not_found", "Rol tapılmadı və ya deaktivdir.", action_name=action_name)

        if target_role.organization_id != org.id:
            return None, _deny_assignment(
                "role_outside_active_organization",
                "Rol yalnız aktiv təşkilat scope-u daxilində təyin oluna bilər.",
                action_name=action_name,
                target_role=target_role,
            )

        return target_role, None

    def _resolve_attach_target(*, action_name, target_role):
        user_id = request.POST.get("user_id")
        try:
            target_user_id = int(str(user_id))
        except (TypeError, ValueError):
            return (
                None,
                None,
                None,
                _deny_assignment(
                    "invalid_user_id",
                    "Düzgün `user_id` göndərilməyib.",
                    action_name=action_name,
                    target_role=target_role,
                ),
            )

        target_user = User.objects.filter(id=target_user_id, is_active=True).first()
        if target_user is None:
            return (
                None,
                None,
                None,
                _deny_assignment(
                    "target_user_not_found",
                    "İstifadəçi tapılmadı.",
                    action_name=action_name,
                    target_role=target_role,
                ),
            )

        if target_user.id == request.user.id:
            return (
                None,
                None,
                None,
                _deny_assignment(
                    "self_role_change_forbidden",
                    "Öz rolunuzu dəyişdirə bilməzsiniz.",
                    action_name=action_name,
                    target_user=target_user,
                    target_role=target_role,
                ),
            )

        target_profile, _ = UserProfile.objects.get_or_create(user=target_user)

        if target_profile.organization and target_profile.organization != org:
            return (
                None,
                None,
                None,
                _deny_assignment(
                    "user_bound_to_other_org",
                    "İstifadəçi başqa təşkilata bağlıdır.",
                    action_name=action_name,
                    target_user=target_user,
                    target_role=target_role,
                ),
            )

        if Membership.objects.filter(user=target_user, is_active=True).exclude(organization=org).exists():
            return (
                None,
                None,
                None,
                _deny_assignment(
                    "user_has_membership_in_other_org",
                    "İstifadəçi başqa təşkilat üzvlüyünə malikdir.",
                    action_name=action_name,
                    target_user=target_user,
                    target_role=target_role,
                ),
            )

        target_primary_level = get_user_org_role_level(target_user, org)
        if not is_superadmin and target_primary_level >= actor_primary_level:
            return (
                None,
                None,
                None,
                _deny_assignment(
                    "target_level_not_lower_than_actor",
                    "Yalnız sizdən aşağı səviyyəli üzvlərin rolunu dəyişə bilərsiniz.",
                    action_name=action_name,
                    target_user=target_user,
                    target_role=target_role,
                    extra={"target_primary_level": target_primary_level, "actor_primary_level": actor_primary_level},
                ),
            )

        if not is_superadmin and target_role.level >= actor_primary_level:
            return (
                None,
                None,
                None,
                _deny_assignment(
                    "requested_role_not_lower_than_actor",
                    "Yalnız sizdən aşağı səviyyəli rolları təyin edə bilərsiniz.",
                    action_name=action_name,
                    target_user=target_user,
                    target_role=target_role,
                    extra={"actor_primary_level": actor_primary_level},
                ),
            )

        if _is_owner_role(target_role) and not can_assign_owner_roles:
            return (
                None,
                None,
                None,
                _deny_assignment(
                    "owner_role_assignment_permission_required",
                    "`org.owner.assign` icazəsi olmadan owner səviyyəli rol təyin etmək olmaz.",
                    action_name=action_name,
                    target_user=target_user,
                    target_role=target_role,
                ),
            )

        if _is_admin_role(target_role) and not _is_owner_role(target_role) and not can_assign_admin_roles:
            return (
                None,
                None,
                None,
                _deny_assignment(
                    "admin_role_assignment_permission_required",
                    "`org.admin.assign` icazəsi olmadan admin səviyyəli rol təyin etmək olmaz.",
                    action_name=action_name,
                    target_user=target_user,
                    target_role=target_role,
                ),
            )

        if not is_superadmin:
            is_requested_for_org = _pending_student_request_queryset(
                user=target_user,
                organization=org,
                statuses=[StudentOrganizationRequestStatus.PENDING],
            ).exists()
            if not is_requested_for_org:
                requested_org = target_profile.requested_organization
                requested_name = _normalized_org_name(target_profile.requested_organization_name)
                is_requested_for_org = (requested_org is not None and requested_org == org) or (
                    requested_org is None and requested_name and requested_name == _normalized_org_name(org.name)
                )
            if not is_requested_for_org:
                signup_mismatch_message = pgettext_lazy(
                    "accounts.role_assignment.message",
                    "user_did_not_select_this_org_on_signup",
                )
                if _wants_json_response() or request.POST.get("action") == "prepare_operation":
                    return (
                        None,
                        None,
                        None,
                        _deny_assignment(
                            "user_did_not_select_this_org_on_signup",
                            signup_mismatch_message,
                            action_name=action_name,
                            target_user=target_user,
                            target_role=target_role,
                        ),
                    )
                create_audit_log(
                    user=request.user,
                    organization=org,
                    action="update",
                    resource_type="user",
                    resource_id=target_user.id,
                    resource_repr=target_user.username,
                    old_values=None,
                    new_values=_build_role_assignment_audit_values(
                        status="denied",
                        action_name=action_name,
                        target_role=target_role,
                        target_user=target_user,
                        reason_code="user_did_not_select_this_org_on_signup",
                        extra={
                            "requested_membership_id": request.POST.get("membership_id"),
                            "requested_user_id": request.POST.get("user_id"),
                            "requested_role_id": request.POST.get("role_id"),
                            "reason": str(signup_mismatch_message),
                        },
                    ),
                    reason=str(signup_mismatch_message),
                    request=request,
                )
                messages.error(request, signup_mismatch_message)
                return None, None, None, redirect(next_url)

        existing_membership = (
            Membership.objects.filter(user=target_user, organization=org)
            .select_related("role", "organization", "user")
            .first()
        )
        if existing_membership is not None:
            denied_response = _enforce_role_change_guards(
                action_name=action_name,
                target_membership=existing_membership,
                target_role=target_role,
            )
            if denied_response:
                return None, None, None, denied_response

        return target_user, target_profile, existing_membership, None

    def _resolve_update_target(*, action_name, target_role):
        membership_id = request.POST.get("membership_id")
        target_membership_uuid = _parse_uuid(membership_id)
        if target_membership_uuid is None:
            return None, _deny_assignment(
                "invalid_membership_id",
                "Düzgün `membership_id` göndərilməyib.",
                action_name=action_name,
                target_role=target_role,
            )

        target_membership = (
            Membership.objects.select_related("role", "user", "organization")
            .filter(id=target_membership_uuid, is_active=True)
            .first()
        )
        if target_membership is None:
            return None, _deny_assignment(
                "membership_not_found",
                "Üzvlük tapılmadı.",
                action_name=action_name,
                target_role=target_role,
            )

        if target_membership.organization_id != org.id:
            return None, _deny_assignment(
                "membership_outside_active_organization",
                "Üzvlük yalnız aktiv təşkilat scope-u daxilində idarə oluna bilər.",
                action_name=action_name,
                target_membership=target_membership,
                target_role=target_role,
            )

        denied_response = _enforce_role_change_guards(
            action_name=action_name,
            target_membership=target_membership,
            target_role=target_role,
        )
        if denied_response:
            return None, denied_response

        return target_membership, None

    def _build_operation_token(*, action_name, target_role, target_membership=None, target_user=None):
        if target_membership is None and target_user is None:
            return None

        target_id = str(target_membership.id if target_membership is not None else target_user.id)
        payload = {
            "actor_user_id": str(request.user.id),
            "organization_id": str(org.id),
            "target_action": action_name,
            "target_id": target_id,
            "role_id": str(target_role.id),
        }
        operation_signer = TimestampSigner(salt=ROLE_ASSIGNMENT_OPERATION_TOKEN_SALT)
        return operation_signer.sign_object(payload)

    # Keep legacy minimum-level gate for accessing the assignment endpoint.
    # Actual assignment authorization is enforced by explicit permission checks below.
    if not is_superadmin and actor_primary_level < 50:
        messages.error(request, pgettext_lazy("accounts.role_assignment.message", "teacher_or_higher_only"))
        return redirect("accounts:profile")

    search = request.GET.get("q", request.GET.get("search", ""))
    unassigned_search = request.GET.get("unassigned_search", "")
    profile_section_url = _append_query_params(
        reverse("accounts:profile"),
        section="role-assignment",
        q=search,
        unassigned_search=unassigned_search,
        role_members_page=request.GET.get("role_members_page", ""),
        role_pending_page=request.GET.get("role_pending_page", ""),
    )

    if request.method != "POST":
        return redirect(profile_section_url)

    if request.method == "POST":
        action = request.POST.get("action", "update_member")
        next_url = _resolve_next_url(request, profile_section_url)
        requested_action = action
        role_id = request.POST.get("role_id")

        if action == "prepare_operation":
            requested_action = (request.POST.get("target_action") or "").strip()
            role_id = request.POST.get("new_role_id") or role_id

        if requested_action not in {"attach_user", "update_member"}:
            return _deny_assignment("unknown_action", "Bilinməyən əməliyyat.", action_name=requested_action or action)

        if not is_superadmin and actor_primary_membership is None:
            return _deny_assignment(
                "actor_not_member_of_active_organization",
                "Aktiv təşkilatda üzvlük tapılmadı.",
                action_name=requested_action,
            )

        if not can_manage_members:
            return _deny_assignment(
                "missing_member_management_permission",
                "`role.assign` və ya `org.manage_members` icazəsi tələb olunur.",
                action_name=requested_action,
            )

        target_role, role_error = _resolve_target_role(action_name=requested_action, role_id=role_id)
        if role_error:
            return role_error

        target_membership = None
        target_user = None
        target_profile = None
        existing_membership = None

        if requested_action == "attach_user":
            target_user, target_profile, existing_membership, attach_error = _resolve_attach_target(
                action_name=requested_action,
                target_role=target_role,
            )
            if attach_error:
                return attach_error
        else:
            target_membership, membership_error = _resolve_update_target(
                action_name=requested_action,
                target_role=target_role,
            )
            if membership_error:
                return membership_error

        if action == "prepare_operation":
            operation_token = _build_operation_token(
                action_name=requested_action,
                target_role=target_role,
                target_membership=target_membership,
                target_user=target_user,
            )
            old_role_label = (
                target_membership.role.display_name
                if target_membership is not None
                else (existing_membership.role.display_name if existing_membership is not None else "Üzvlük yoxdur")
            )
            return JsonResponse(
                {
                    "success": True,
                    "operation_token": operation_token,
                    "expires_in_seconds": ROLE_ASSIGNMENT_OPERATION_TOKEN_MAX_AGE_SECONDS,
                    "action": requested_action,
                    "target": {
                        "organization_id": str(org.id),
                        "target_id": str(target_membership.id if target_membership is not None else target_user.id),
                        "old_role": old_role_label,
                        "new_role": target_role.display_name,
                    },
                }
            )

        token_error = _validate_operation_token(
            action_name=requested_action,
            target_role=target_role,
            target_membership=target_membership,
            target_user=target_user,
        )
        if token_error:
            return token_error

        if requested_action == "attach_user":
            attach_old_role = existing_membership.role if existing_membership is not None else None
            membership, created = Membership.objects.get_or_create(
                user=target_user,
                organization=org,
                defaults={
                    "role": target_role,
                    "assigned_by": request.user,
                    "is_primary": True,
                    "is_active": True,
                },
            )
            if not created:
                denied_response = _enforce_role_change_guards(
                    action_name=requested_action,
                    target_membership=membership,
                    target_role=target_role,
                )
                if denied_response:
                    return denied_response
                membership.role = target_role
                membership.assigned_by = request.user
                membership.is_active = True
                membership.save(update_fields=["role", "assigned_by", "is_active", "updated_at"])

            target_profile.organization = org
            target_profile.organization_type = org.org_type
            target_profile.role = _map_org_role_to_profile_role(target_role)
            target_profile.requested_organization = org
            target_profile.requested_organization_name = org.name
            target_profile.requested_organization_message = ""
            target_profile.save(
                update_fields=[
                    "organization",
                    "organization_type",
                    "role",
                    "requested_organization",
                    "requested_organization_name",
                    "requested_organization_message",
                    "updated_at",
                ]
            )

            now = timezone.now()
            _pending_student_request_queryset(
                user=target_user,
                organization=org,
                statuses=[StudentOrganizationRequestStatus.PENDING],
            ).update(
                status=StudentOrganizationRequestStatus.APPROVED,
                resolution_note="Təşkilat tərəfindən qəbul edildi.",
                responded_by=request.user,
                responded_at=now,
                updated_at=now,
            )
            _close_other_pending_student_requests(
                user=target_user,
                accepted_organization=org,
                responded_by=request.user,
            )

            create_audit_log(
                user=request.user,
                organization=org,
                action="update",
                resource_type="membership",
                resource_id=membership.id,
                resource_repr=str(membership),
                old_values={
                    "old_role_id": str(attach_old_role.id) if attach_old_role is not None else "",
                    "old_role_name": (attach_old_role.display_name if attach_old_role is not None else ""),
                },
                new_values=_build_role_assignment_audit_values(
                    status="success",
                    action_name=requested_action,
                    target_role=target_role,
                    target_membership=membership,
                    target_user=target_user,
                    old_role=attach_old_role,
                    reason_code="",
                    extra={"attached_user": target_user.username},
                ),
                request=request,
            )

            success_message = f"Uğurla əlavə edildi: {target_user.username} → {target_role.display_name}."
            if _wants_json_response():
                return JsonResponse({"success": True, "message": success_message, "redirect_url": next_url})

            messages.success(request, success_message)
            return redirect(next_url)

        # Default action: update existing org membership
        old_role = target_membership.role
        target_membership.role = target_role
        target_membership.assigned_by = request.user
        target_membership.save(update_fields=["role", "assigned_by", "updated_at"])

        target_profile, _ = UserProfile.objects.get_or_create(user=target_membership.user)
        target_profile.role = _map_org_role_to_profile_role(target_role)
        target_profile.organization = org
        target_profile.organization_type = org.org_type
        target_profile.requested_organization = org
        target_profile.requested_organization_name = org.name
        target_profile.requested_organization_message = ""
        target_profile.save(
            update_fields=[
                "role",
                "organization",
                "organization_type",
                "requested_organization",
                "requested_organization_name",
                "requested_organization_message",
                "updated_at",
            ]
        )

        now = timezone.now()
        _pending_student_request_queryset(
            user=target_membership.user,
            organization=org,
            statuses=[StudentOrganizationRequestStatus.PENDING],
        ).update(
            status=StudentOrganizationRequestStatus.APPROVED,
            resolution_note="Üzvlük aktiv olduğuna görə müraciət bağlandı.",
            responded_by=request.user,
            responded_at=now,
            updated_at=now,
        )
        _close_other_pending_student_requests(
            user=target_membership.user,
            accepted_organization=org,
            responded_by=request.user,
        )

        create_audit_log(
            user=request.user,
            organization=org,
            action="update",
            resource_type="membership",
            resource_id=target_membership.id,
            resource_repr=str(target_membership),
            old_values={
                "old_role_id": str(old_role.id) if old_role is not None else "",
                "old_role_name": (old_role.display_name if old_role is not None else ""),
            },
            new_values=_build_role_assignment_audit_values(
                status="success",
                action_name=requested_action,
                target_role=target_role,
                target_membership=target_membership,
                target_user=target_membership.user,
                old_role=old_role,
            ),
            request=request,
        )

        success_message = f"Uğurla yeniləndi: {target_membership.user.username} → {target_role.display_name}."
        if _wants_json_response():
            return JsonResponse({"success": True, "message": success_message, "redirect_url": next_url})

        messages.success(request, success_message)
        return redirect(next_url)

    return redirect(profile_section_url)


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

    return redirect(reverse("accounts:profile") + "?section=permission-editor")
