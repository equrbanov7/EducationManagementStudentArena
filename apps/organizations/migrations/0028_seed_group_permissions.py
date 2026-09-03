"""Mövcud rollara `group.view` / `group.manage` icazələrini geriyə-doldur.

DAVRANIŞ QORUNMASI: qrup yaratma qapısı (apps/exams/views/teacher/groups.py)
əvvəllər `has_role(org_owner) OR has_role(org_admin)` idi. `org_admin` aliası
rol ADINA və SƏVİYYƏSİNƏ görə hesablanır (core/roles.py
`ProfileRole.aliases_for_membership_role`):

* ad ADMIN_EQUIVALENT_ROLE_NAMES-dədirsə (normallaşdırmadan sonra), VƏ YA
* level >= 80-dirsə,
* və ad ADMIN_ALIAS_EXEMPT_ROLE_NAMES-də DEYİLSƏ (imtahan mərkəzi rolları, hr).

Qapı permission-əsaslı (`group.manage`) olduğundan bu migration MƏHZ HƏMİN
çoxluğa (is_system və custom rollar daxil) yeni açarları əlavə edir — heç kim
əvvəl edə bildiyini itirmir, heç kim yeni imkan qazanmır. `*` icazəli rollar
onsuz da əhatələnir. Yeni təşkilatlar açarları default_roles.py-dan alır.

QEYD: siyahılar core/roles.py-dan DONDURULMUŞ surətdir — data migration zamanla
sabit qalmalıdır (canlı import gələcək kod dəyişikliyində migrationun tarixi
davranışını dəyişərdi).
"""

from django.db import migrations

_GROUP_PERMS = ("group.view", "group.manage")

# core/roles.py ProfileRole.ROLE_NAME_NORMALIZATION (2026-08 snapshot).
_ROLE_NAME_NORMALIZATION = {
    "deputy_director": "vice_director",
    "chair_head": "department_head",
    "section_head": "department_head",
}

# core/roles.py ProfileRole.ADMIN_EQUIVALENT_ROLE_NAMES (2026-08 snapshot).
_ADMIN_EQUIVALENT_ROLE_NAMES = {
    "org_admin",
    "org_owner",
    "rector",
    "vice_rector",
    "dean",
    "vice_dean",
    "department_head",
    "director",
    "vice_director",
    "manager",
    "senior_instructor",
}

# core/roles.py ProfileRole.ADMIN_ALIAS_EXEMPT_ROLE_NAMES (2026-08 snapshot).
_ADMIN_ALIAS_EXEMPT_ROLE_NAMES = {"exam_center", "exam_center_head", "exam_center_staff", "hr"}

_ORG_ADMIN_LEVEL = 80


def _normalized_name(role_name):
    normalized = (role_name or "").strip().lower()
    return _ROLE_NAME_NORMALIZATION.get(normalized, normalized)


def _role_had_group_access(role):
    """Rol əvvəlki `has_role(org_admin/org_owner)` qapısından keçirdimi?"""
    normalized = _normalized_name(role.name)
    if normalized in _ADMIN_ALIAS_EXEMPT_ROLE_NAMES:
        return False
    return normalized in _ADMIN_EQUIVALENT_ROLE_NAMES or (role.level or 0) >= _ORG_ADMIN_LEVEL


def seed_group_permissions(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.all().iterator():
        permissions = list(role.permissions or [])
        if "*" in permissions:
            continue
        if not _role_had_group_access(role):
            continue
        to_add = [perm for perm in _GROUP_PERMS if perm not in permissions]
        if not to_add:
            continue
        role.permissions = permissions + to_add
        role.save(update_fields=["permissions", "updated_at"])


def remove_group_permissions(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.all().iterator():
        permissions = list(role.permissions or [])
        if not _role_had_group_access(role):
            continue
        remaining = [perm for perm in permissions if perm not in _GROUP_PERMS]
        if remaining == permissions:
            continue
        role.permissions = remaining
        role.save(update_fields=["permissions", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0027_seed_grade_approval_permissions"),
    ]

    operations = [
        migrations.RunPython(seed_group_permissions, remove_group_permissions),
    ]
