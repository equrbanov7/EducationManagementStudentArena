"""«Rolları idarə et» — bölmənin POST giriş nöqtəsi.

İKİ YAZI AXINI bir URL-dədir:

* YENİ (2026-09-09) — `grant_role` / `revoke_role`: təşkilatın öz `Role`
  kataloqundan bir rol verilir/geri alınır və şəxsin digər üzvlükləri
  toxunulmadan qalır. Məntiq `_multi_role.py`-dədir; ekran da bunu işlədir.
* KÖHNƏ — `assign` / `remove` + `role_names[]`: `ProfileRole` enum-u üzrə
  checkbox dəsti. Səth artıq render olunmur, amma endpoint SAXLANILIR (köhnə
  inteqrasiyalar + `tests/test_manage_roles_scope.py` reqressiya qapısı).

Hər iki axın EYNİ qapılardan keçir (`_gates.py`): `role.assign` /
`org.manage_members`, struktur əhatəsi və səviyyə müqayisəsi.

GET yalnız qabığı render edir — panelin məzmunu
`views/profile/_sections/manage_roles.py`-dədir.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import pgettext_lazy

from apps.accounts.policies.roles import resolve_membership_role
from apps.organizations.models import Membership

from ...models import ProfileRole, UserProfile
from .._helpers import (
    PROFILE_ROLE_LABELS,
    PROFILE_ROLE_NAMES,
    _assignable_profile_roles_for_user,
    _bind_active_role_context,
    _extract_profile_roles_for_user,
    _get_active_organization,
    _is_superadmin_user,
    _render_profile_section,
    _resolve_next_url,
    _sync_user_role_memberships,
)
from ._gates import ORG_WIDE_STAFF_ROLES, actor_is_unit_scoped, manage_roles_gate_error
from ._multi_role import handle_org_role_action

User = get_user_model()


# Qapılar (`role.assign`/`org.manage_members` + struktur əhatəsi, org-əhatəli
# rol siyahısı) ORTAQ `_gates` modulundadır — köhnə checkbox axını ilə yeni
# «rol ver / geri al» axını EYNİ qapıdan keçir. Adlar geriyə uyğunluq üçün
# burada da görünür (köhnə import yolları qırılmasın).
_actor_is_unit_scoped = actor_is_unit_scoped
_manage_roles_gate_error = manage_roles_gate_error


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

        # Yeni səth: TƏŞKİLAT rolunun verilməsi / geri alınması (`organizations.Role`).
        # Köhnə checkbox axını (`assign`/`remove`) aşağıda olduğu kimi qalır.
        org_role_response = handle_org_role_action(
            request,
            organization=user_org,
            is_superadmin=is_superadmin,
            actor_level=actor_level,
            next_url=next_url,
        )
        if org_role_response is not None:
            return org_role_response

        if not user_id:
            messages.error(request, pgettext_lazy("accounts.manage_roles.message", "user_not_selected"))
            return redirect(next_url)

        target_user = get_object_or_404(User, id=user_id)

        # QA 2026-09-05 PEOPLE-RBAC-08: bu legacy səth yalnız səviyyəyə baxırdı — dekan
        # başqa fakültənin müəlliminə org-səviyyəli rol (HR, İmtahan Mərkəzi) verə bilirdi.
        # Rol təyinatı axını ilə EYNİ qapı: `role.assign`/`org.manage_members` + struktur əhatəsi.
        gate_error = _manage_roles_gate_error(request, user_org, target_user, is_superadmin=is_superadmin)
        if gate_error is not None:
            messages.error(request, gate_error)
            return redirect(next_url)

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
        if not is_superadmin and _actor_is_unit_scoped(request.user, user_org):
            org_wide = selected_role_names & ORG_WIDE_STAFF_ROLES
            if org_wide:
                messages.error(
                    request, pgettext_lazy("accounts.manage_roles.message", "not_allowed_to_assign_some_roles")
                )
                return redirect(next_url)
        # Təşkilatda qarşılığı olmayan rol adı üçün heç nə yazılmır (əvvəl səssizcə
        # ən aşağı rol yaranırdı — PEOPLE-RBAC-09).
        unresolved = [name for name in sorted(selected_role_names) if resolve_membership_role(user_org, name) is None]
        if unresolved:
            messages.error(
                request,
                pgettext_lazy("accounts.manage_roles.message", "role_not_defined_in_organization")
                % {"roles": ", ".join(str(PROFILE_ROLE_LABELS.get(name, name)) for name in unresolved)},
            )
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

        # DİQQƏT: rol etiketləri `pgettext_lazy` proxy-siləri qaytarır (ProfileRole.CHOICES).
        # `", ".join(...)` proxy qəbul etmir və mesaj audit JSONField-inə də düşür —
        # ona görə burada dərhal `str()` ilə həll olunur (bax `roles.display_name`).
        assigned_labels = [str(PROFILE_ROLE_LABELS.get(role_name, role_name)) for role_name in sorted(effective_roles)]
        added_labels = [str(PROFILE_ROLE_LABELS.get(role_name, role_name)) for role_name in sorted(added_roles)]
        removed_labels = [str(PROFILE_ROLE_LABELS.get(role_name, role_name)) for role_name in sorted(removed_roles)]
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

    # GET: panelin BÜTÜN məzmununu bölmə qurucusu qurur
    # (`views/profile/_sections/manage_roles.py`) — reyestr, KPI, filtr və
    # dialoqlar. Əvvəl burada ikinci, PARALEL siyahı (köhnə `UserProfile`
    # səhifələməsi + `_decorate_manage_role_profiles`) da qurulurdu; yeni
    # şablon ondan heç nə oxumur, ona görə həmin sorğular ÇIXARILDI.
    return _render_profile_section(request, "manage-roles")
