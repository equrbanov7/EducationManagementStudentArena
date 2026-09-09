"""Profil «İcazələr» bölməsi — rol × icazə kataloqu.

2026-09-09 yenidən qurulub: rol seçimi artıq badge-lər yığını deyil, `ems_ui`
filtr panelindəki AXTARIŞLI select-dir; yuxarıda KPI sırası (rolun aktiv
icazəsi, kataloqun ölçüsü, delegasiya sayı), altda isə kateqoriya üzrə
qruplaşdırılmış icazə siyahısı var. Hər sətirdə həmin açarı DAŞIYAN DİGƏR
rollar da göstərilir — «bu icazə kimlərdədir?» sualı ekranı tərk etmədən
cavablanır.

Yazma axını (POST → `views/roles/permissions.py`) DƏYİŞMƏYİB: `add` / `remove` /
`bulk_add` / `bulk_remove` / `grant_delegation` / `revoke_delegation`.
"""

from django.utils.translation import pgettext

from apps.accounts.services.role_catalog import role_label

_CTX = "accounts.permission_editor"

#: Kateqoriya açarı → (başlıq, izah). Şablondakı uzun `if/elif` zənciri buraya
#: köçürüldü — kateqoriya artanda şablona toxunmaq lazım gəlmir.
CATEGORY_LABELS = {
    "organization": (pgettext(_CTX, "Təşkilat"), pgettext(_CTX, "Təşkilat ayarları və idarəetmə əməliyyatları")),
    "structure": (pgettext(_CTX, "Struktur"), pgettext(_CTX, "Fakültə, şöbə və struktur vahidləri")),
    "catalog": (pgettext(_CTX, "Akademik kataloq"), pgettext(_CTX, "İxtisas və fənn reyestrləri")),
    "members": (pgettext(_CTX, "Üzvlər"), pgettext(_CTX, "İstifadəçilər və üzvlüklə bağlı əməliyyatlar")),
    "roles": (pgettext(_CTX, "Rollar"), pgettext(_CTX, "Rol təyini və rol səviyyələri")),
    "courses": (pgettext(_CTX, "Kurslar"), pgettext(_CTX, "Kurs yaradılması və kurs idarəetməsi")),
    "grading": (pgettext(_CTX, "Qiymətləndirmə"), pgettext(_CTX, "Qiymətləndirmə və nəticə axınları")),
    "journal": (pgettext(_CTX, "Jurnal"), pgettext(_CTX, "Jurnal baxışı və sənədli düzəlişlər")),
    "groups": (pgettext(_CTX, "Qruplar"), pgettext(_CTX, "Tələbə qruplarının yaradılması və idarəsi")),
    "exams": (pgettext(_CTX, "İmtahanlar"), pgettext(_CTX, "İmtahan idarəetməsi və nəzarət")),
    "appeal": (pgettext(_CTX, "Apellyasiya"), pgettext(_CTX, "Apellyasiya müraciətləri")),
    "analytics": (pgettext(_CTX, "Analitika"), pgettext(_CTX, "Analitik hesabat və göstəricilər")),
    "qa": (pgettext(_CTX, "Keyfiyyət"), pgettext(_CTX, "Keyfiyyət yoxlaması əməliyyatları")),
    "audit": (pgettext(_CTX, "Audit jurnalı"), pgettext(_CTX, "Tarixçə və audit log baxışı")),
}


def _category_meta(category):
    title, subtitle = CATEGORY_LABELS.get(
        category, (category.replace("_", " ").title(), pgettext(_CTX, "Bu bölmə üçün icazələr"))
    )
    return {"key": category, "title": title, "subtitle": subtitle}


def _holders_map(roles, selected_role_id):
    """`{icazə açarı: [rol etiketləri]}` — hansı rolun hansı açarı daşıdığı."""
    holders = {}
    wildcard = []
    for role in roles:
        label = role_label(role)
        permissions = role.permissions or []
        if "*" in permissions:
            wildcard.append(label)
            continue
        for permission in permissions:
            if permission.startswith("grant:"):
                continue
            if str(role.id) == str(selected_role_id):
                continue
            holders.setdefault(permission, []).append(label)
    return holders, wildcard


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
    from apps.organizations.public import PERMISSION_CATEGORIES

    # `pe_role` — yeni filtr paneli; `role` köhnə dərin keçidlər (bildiriş
    # linkləri: `?section=permission-editor&role=<id>`) üçün saxlanılır.
    selected_permission_role_id = request.GET.get("pe_role") or request.GET.get("role")
    section.update(
        {
            "organization": management_org,
            "permission_categories": PERMISSION_CATEGORIES,
            "actor_permissions": sorted(management_actor_permissions),
            "grantable_permissions": sorted(management_grantable_permissions),
            "can_manage_permissions": management_can_assign_roles,
            "has_access": management_org is not None,
            "action_url": None,
        }
    )

    if management_org is None:
        section["access_denied_message"] = pgettext(_CTX, "Aktiv təşkilat tapılmadı.")
        return section
    if not capabilities["is_superadmin"] and not management_can_assign_roles:
        section["access_denied_message"] = pgettext(
            _CTX, "Permission idarəetməsi üçün `role.assign` səlahiyyəti tələb olunur."
        )
        return section

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

    role_list = list(roles)
    section["role_choices"] = [
        {"value": str(role.id), "label": f"{role_label(role)} ({role.level})"} for role in role_list
    ]
    section["subtitle"] = pgettext(
        _CTX,
        "Rolun hansı funksiyaları aça biləcəyini buradan idarə edin. Açarlar bölmələr üzrə qruplaşdırılıb; "
        "hər sətir həmin icazənin başqa hansı rollarda olduğunu da göstərir.",
    )

    if selected_permission_role is None:
        section["kpi_tiles"] = []
        section["filter_fields"] = []
        section["modules"] = []
        section["access_denied_message"] = pgettext(_CTX, "Bu təşkilatda idarə edə biləcəyiniz rol yoxdur.")
        return section

    from apps.organizations.public import is_grant_entry, strip_grant_prefix

    role_permissions = list(selected_permission_role.permissions or [])
    delegated = {strip_grant_prefix(perm) for perm in role_permissions if is_grant_entry(perm)}
    section["delegated_permissions"] = delegated

    active_keys = {perm for perm in role_permissions if not is_grant_entry(perm)}
    has_wildcard = "*" in active_keys
    holders, wildcard_roles = _holders_map(role_list, selected_permission_role.id)

    total_keys = 0
    modules = []
    for category, permissions in PERMISSION_CATEGORIES.items():
        meta = _category_meta(category)
        rows = []
        for permission in permissions:
            total_keys += 1
            is_active = has_wildcard or permission in active_keys
            rows.append(
                {
                    "key": permission,
                    "is_active": is_active,
                    "is_delegated": permission in delegated,
                    "holders": holders.get(permission, []) + wildcard_roles,
                }
            )
        meta["rows"] = rows
        meta["active_count"] = sum(1 for row in rows if row["is_active"])
        meta["total"] = len(rows)
        modules.append(meta)
    section["modules"] = modules

    active_count = total_keys if has_wildcard else len(active_keys & _flatten(PERMISSION_CATEGORIES))
    section["kpi_tiles"] = [
        {
            "label": pgettext(_CTX, "Seçilmiş rol"),
            "value": role_label(selected_permission_role),
            "tone": "primary",
            "note": pgettext(_CTX, "səviyyə %(level)d") % {"level": selected_permission_role.level},
        },
        {
            "label": pgettext(_CTX, "Aktiv icazə"),
            "value": active_count,
            "note": pgettext(_CTX, "%(total)d açardan") % {"total": total_keys},
        },
        {"label": pgettext(_CTX, "Kateqoriya"), "value": len(modules)},
        {
            "label": pgettext(_CTX, "Delegasiya"),
            "value": len(delegated),
            "tone": "accent-warning" if delegated else None,
            "note": pgettext(_CTX, "aşağı rollara paylana bilir"),
        },
        {"label": pgettext(_CTX, "İdarə edilə bilən rol"), "value": len(role_list)},
    ]
    section["filter_fields"] = [
        {
            "name": "pe_role",
            "label": pgettext(_CTX, "Rol"),
            "kind": "select",
            "options": section["role_choices"],
            "value": str(selected_permission_role.id),
            "searchable": True,
            "wide": True,
        }
    ]
    section["active_count"] = active_count
    section["total_keys"] = total_keys
    return section


def _flatten(categories):
    keys = set()
    for permissions in categories.values():
        keys.update(permissions)
    return keys
