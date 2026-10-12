"""`org.view` açarını bütün rollardan silir (sahib 2026-10-13: «org view lazım deyilsə çıxar») + oxu açarları.

Əlavə (sahib: «başqa tövsiyə olunan nə varsa et»): RİM əməkdaşına `workload.report`, `plan.view`,
`semester.view`; qəyyuma `workload.report` — hamısı YALNIZ-OXU icmallardır (bax
`default_roles_role_audit.ROLE_AUDIT_GRANTS`). Açar/wildcard/`*` varsa toxunulmur.

Rol auditinin sərtləşdirilmiş drift skanı (B13) göstərdi ki, `org.view` yalnız rol şablonlarında və demo seed
komandasında yazılıb — heç bir view/servis/şablon onu YOXLAMIR (təşkilata baxış aktiv üzvlüklə verilir).
Redaktorda «yalançı düymə» qalmasın deyə kataloqdan (`permissions.py`) və şablonlardan çıxarıldı; bu miqrasiya
mövcud tenantların rol sətirlərini eyni vəziyyətə gətirir. İdempotent. Geri dönüş: verilən oxu açarlarını götürür; `org.view` geri yazılmır (heç nəyi açmırdı).
"""

from django.db import migrations

_KEY = "org.view"
_GRANTS = {
    "rim_staff": ("workload.report", "plan.view", "semester.view"),
    "trustee": ("workload.report",),
}


def _covered(permissions, key):
    return key in permissions or f"{key.split('.', 1)[0]}.*" in permissions or "*" in permissions


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.all().iterator():
        before = list(role.permissions or [])
        permissions = [entry for entry in before if entry != _KEY]
        for key in _GRANTS.get(role.name, ()):
            if not _covered(permissions, key):
                permissions.append(key)
        if permissions != before:
            role.permissions = permissions
            role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name__in=list(_GRANTS)).iterator():
        granted = set(_GRANTS[role.name])
        permissions = [entry for entry in (role.permissions or []) if entry not in granted]
        if permissions != list(role.permissions or []):
            role.permissions = permissions
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [("organizations", "0062_notification_publish_key")]

    operations = [migrations.RunPython(forward, backward)]
