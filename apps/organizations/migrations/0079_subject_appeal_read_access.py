"""Chair manager and laboratory assistant: scoped read-only subject appeals."""

from django.db import migrations

KEY = "appeal.view_subject"
ROLES = ("chair_head", "lab_assistant")


def _roles(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    return apps.get_model("organizations", "Role").objects.filter(name__in=ROLES)


def forward(apps, schema_editor):
    for role in _roles(apps, schema_editor).iterator():
        permissions = list(role.permissions or [])
        if not any(key in permissions for key in (KEY, "appeal.*", "*")):
            role.permissions = permissions + [KEY]
            role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    for role in _roles(apps, schema_editor).iterator():
        if KEY in (role.permissions or []):
            role.permissions = [key for key in role.permissions if key != KEY]
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("organizations", "0078_lab_assistant_journal_view")]
    operations = [migrations.RunPython(forward, backward)]
