"""Tədris şöbəsi rolları — struktur və kataloq sahibi (dizayn handoff, Mərhələ 1).

``default_roles_university`` modul ölçü büdcəsinə (SOFT_CAP=600) yaxınlaşdığı üçün
bu iki rol AYRI faylda saxlanılır və oradan ``UNIVERSITY_ROLES``-a əlavə olunur —
seed axını, migration və testlər üçün fərq yoxdur (eyni siyahıdır).

⚠️ MƏCBURİ QOŞMA: ``teaching_office_head`` səviyyəsi **85 ≥ 80** olduğu üçün
``core.roles.ProfileRole.ADMIN_ALIAS_EXEMPT_ROLE_NAMES`` dəstinə əlavə edilib.
Əks halda ``aliases_for_membership_role`` ona implicit ``org_admin`` aliası verər
və rol bütün tenant idarəetmə səthini (üzv/rol/təşkilat ayarları) alardı —
halbuki onun səlahiyyəti struktur + kataloqdur. Bax
``apps/organizations/tests/test_teaching_office_roles.py``.
"""

from core.constants import RoleScopeType

#: Tədris şöbəsinin ORTAQ səthi — struktur ağacı, ixtisas və fənn kataloqu.
#: Rəhbər və əməkdaş EYNİ ekranları görür; fərq təsdiq/təyinat açarlarındadır.
_TEACHING_OFFICE_SHARED = [
    "org.view",
    # Struktur ağacı (ekran 01) + kafedra profili (ekran 02).
    #
    # ⚠️ PREFİKS QAYDASI: `structure.*` LEGACY sayılır və
    # `test_permissions.DefaultRolesCanonicalPermissionTest` onu bloklayır —
    # kanonik ailə `unit.*`-dır. Ona görə handoff-un «structure.view / manage /
    # assign_head» açarları burada `unit.view` / `unit.tree_manage` /
    # `unit.assign_head` kimi yazılır (məna eynidir).
    #
    # `unit.create` / `unit.edit` mövcud fakültə-kafedra CRUD səthini (org-faculties
    # / org-kafedras) açır; `unit.tree_manage` isə AĞAC əməllərini (alt bölmə
    # yaratmaq, adını dəyişmək, arxivləmək) — ayrı saxlanılır ki, «kafedra yarada
    # bilən» rol avtomatik «ağacı arxivləyən» olmasın.
    "unit.view",
    "unit.create",
    "unit.edit",
    "unit.tree_manage",
    # Kataloq (ekran 03 «İxtisaslar» + ekran 04 «Fənn kataloqu»).
    "catalog.view",
    "catalog.manage",
    # Kafedra profilində müəllim/yük göstəriciləri oxunur.
    "member.view",
    "course.view",
    "workload.view",
    "people.view_teachers",
    "analytics.view_all",
]

TEACHING_OFFICE_ROLES = [
    {
        "name": "teaching_office_head",
        "display_name": "Tədris şöbəsinin rəhbəri",
        "level": 85,
        "scope_type": RoleScopeType.ORGANIZATION,
        "permissions": [
            *_TEACHING_OFFICE_SHARED,
            # Rəhbərə xas: bölmə rəhbərinin təyini (səbəb audit-ə yazılır).
            "unit.assign_head",
            "audit.view",
        ],
        "description": "Teaching office head — owner of the structure tree and the academic catalogue",
    },
    {
        "name": "teaching_office_staff",
        "display_name": "Tədris şöbəsi əməkdaşı",
        "level": 60,
        "scope_type": RoleScopeType.ORGANIZATION,
        # Eyni səth, təsdiq/təyinat səlahiyyəti YOX: `unit.assign_head`
        # QƏSDƏN verilmir (rəhbər təyini şöbə rəhbərinin qərarıdır).
        "permissions": list(_TEACHING_OFFICE_SHARED),
        "description": "Teaching office staff — same surface, no head-assignment authority",
    },
]

#: Mövcud rollara verilən YENİ struktur/kataloq açarları (rol yaradılmır —
#: yalnız açar əlavə olunur). Dekan/kafedra müdiri/koordinator OXUYUR; RİM
#: operator olduğu üçün idarə də edir. Rektorda `*` var — siyahıda yoxdur.
TEACHING_OFFICE_GRANTS: dict[str, tuple[str, ...]] = {
    "dean": ("unit.view", "catalog.view"),
    "chair_head": ("unit.view", "catalog.view"),
    "program_coordinator": ("unit.view", "catalog.view"),
    "ikt_rehber": ("unit.view", "unit.tree_manage", "unit.assign_head", "catalog.view", "catalog.manage"),
    "vice_rector": ("unit.view", "unit.tree_manage", "unit.assign_head", "catalog.view", "catalog.manage"),
}


def apply_teaching_office_grants(roles):
    """``TEACHING_OFFICE_GRANTS``-i rol siyahısına idempotent tətbiq edir."""
    for role in roles:
        wanted = TEACHING_OFFICE_GRANTS.get(role.get("name"))
        if not wanted:
            continue
        permissions = role.setdefault("permissions", [])
        if "*" in permissions:
            continue
        for permission in wanted:
            prefix_wildcard = f"{permission.split('.', 1)[0]}.*"
            if permission in permissions or prefix_wildcard in permissions:
                continue
            permissions.append(permission)
    return roles


__all__ = [
    "TEACHING_OFFICE_ROLES",
    "TEACHING_OFFICE_GRANTS",
    "apply_teaching_office_grants",
]
