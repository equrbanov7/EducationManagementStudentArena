"""Proqram koordinatoruna qrup yaratma / tələbə təyinatı açarları (2026-09-07).

SAHİBİN QƏRARI: «proqram koordinatorunun yeni qrup yaratmaq icazəsi olsun,
ora tələbə əlavə etmək, qrupunu dəyişmək kimi». Seed xəritələri
(``default_roles_university`` / ``default_roles_student_services``) yeni tenant
üçün yeniləndi; bu migrasiya MÖVCUD tenantların ``program_coordinator`` roluna
eyni açarları idempotent əkir (0041 ilə eyni üsul). Rol yaradılmır.

Geri dönüş yalnız bu üç açarı çıxarır.
"""

from django.db import migrations

_ROLE = "program_coordinator"
_KEYS = ("group.manage", "unit.view", "student.assign_group")
_WILDCARD = "*"


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_ROLE).iterator():
        permissions = list(role.permissions or [])
        if _WILDCARD in permissions:
            continue
        changed = False
        for key in _KEYS:
            prefix_wildcard = f"{key.split('.', 1)[0]}.*"
            if key in permissions or prefix_wildcard in permissions:
                continue
            permissions.append(key)
            changed = True
        if changed:
            role.permissions = permissions
            role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_ROLE).iterator():
        permissions = [key for key in (role.permissions or []) if key not in _KEYS]
        if permissions != list(role.permissions or []):
            role.permissions = permissions
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("organizations", "0046_merge_exam_center_into_head")]

    operations = [migrations.RunPython(forward, backward)]
