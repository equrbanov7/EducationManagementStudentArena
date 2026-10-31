"""Dean and teaching office: scoped group and subgroup management."""

from django.db import migrations

KEY = "unit.group_manage"
ROLES = ("dean", "teaching_office_head", "teaching_office_staff")


def _roles(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    return apps.get_model("organizations", "Role").objects.filter(name__in=ROLES)


def forward(apps, schema_editor):
    for role in _roles(apps, schema_editor).iterator():
        permissions = list(role.permissions or [])
        if not any(key in permissions for key in (KEY, "unit.*", "*")):
            role.permissions = permissions + [KEY]
            role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    for role in _roles(apps, schema_editor).iterator():
        if KEY in (role.permissions or []):
            role.permissions = [key for key in role.permissions if key != KEY]
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("organizations", "0079_subject_appeal_read_access")]
    operations = [migrations.RunPython(forward, backward)]
