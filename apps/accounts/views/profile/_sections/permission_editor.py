"""Profil "permission-editor" bölməsi üçün context-fragment qurucusu.

Bütün importlar inline-dır (köhnə blokla eyni). `section` dict-ini doldurub qaytarır.
"""


def build_permission_editor_section(
    request,
    section,
    *,
    management_org,
    management_actor_permissions,
    management_grantable_permissions,
    management_can_assign_roles,
    management_user_level,
    capabilities,
):
    from apps.organizations.models import Role
    from apps.organizations.permissions import PERMISSION_CATEGORIES

    selected_permission_role_id = request.GET.get("role")
    section.update(
        {
            "organization": management_org,
            "permission_categories": PERMISSION_CATEGORIES,
            "actor_permissions": sorted(management_actor_permissions),
            "grantable_permissions": sorted(management_grantable_permissions),
            "can_manage_permissions": management_can_assign_roles,
        }
    )

    if management_org is None:
        section["access_denied_message"] = "Aktiv təşkilat tapılmadı."
    elif not capabilities["is_superadmin"] and not management_can_assign_roles:
        section["access_denied_message"] = "Permission idarəetməsi üçün `role.assign` səlahiyyəti tələb olunur."
    else:
        roles = Role.objects.filter(organization=management_org, is_active=True).order_by("-level")
        if not capabilities["is_superadmin"]:
            roles = roles.filter(level__lt=management_user_level)

        selected_permission_role = None
        if selected_permission_role_id:
            selected_permission_role = roles.filter(id=selected_permission_role_id).first()
        if selected_permission_role is None:
            selected_permission_role = roles.first()

        section["roles"] = roles
        section["selected_role"] = selected_permission_role

        # Delegasiya olunmuş icazələr (grant:<perm> girişlərinin suffix-ləri) —
        # template-də "Delegasiya" toggle-ının vəziyyətini göstərmək üçün.
        if selected_permission_role is not None:
            from apps.organizations.permissions import is_grant_entry, strip_grant_prefix

            section["delegated_permissions"] = {
                strip_grant_prefix(perm)
                for perm in (selected_permission_role.permissions or [])
                if is_grant_entry(perm)
            }

    return section
