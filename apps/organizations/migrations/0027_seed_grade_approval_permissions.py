"""Grant the explicit chair-step permission to existing system chair roles."""

from django.db import migrations

PERMISSION = "grade.approve_chair"


def add_permission(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name="chair_head", is_system=True).iterator():
        permissions = list(role.permissions or [])
        if PERMISSION not in permissions:
            permissions.append(PERMISSION)
            role.permissions = permissions
            role.save(update_fields=["permissions"])


def remove_permission(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name="chair_head", is_system=True).iterator():
        permissions = [item for item in (role.permissions or []) if item != PERMISSION]
        role.permissions = permissions
        role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("organizations", "0026_seed_ikt_rehber_role")]

    operations = [migrations.RunPython(add_permission, remove_permission)]
