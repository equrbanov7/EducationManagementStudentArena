"""Dekan müavini yalnız öz struktur əhatəsindəki müraciətləri emal edir."""

from django.db import migrations


def grant(apps, schema_editor):
    if schema_editor is not None and schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name="vice_dean"):
        permissions = list(role.permissions or [])
        if not any(key in permissions for key in ("application.handle", "application.*", "*")):
            Role.objects.filter(pk=role.pk).update(permissions=permissions + ["application.handle"])


def revoke(apps, schema_editor):
    if schema_editor is not None and schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name="vice_dean"):
        Role.objects.filter(pk=role.pk).update(
            permissions=[p for p in role.permissions or [] if p != "application.handle"]
        )


class Migration(migrations.Migration):
    dependencies = [("organizations", "0075_vice_rector_journal_view")]
    operations = [migrations.RunPython(grant, revoke)]
