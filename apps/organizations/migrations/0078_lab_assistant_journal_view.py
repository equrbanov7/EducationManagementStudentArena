"""Laborant öz UNIT əhatəsinin jurnallarını yalnız oxuya bilir.

Yazı/korrektor/admin/şəbəkə açarları və üzvlük scope-ları dəyişdirilmir.
Kafedra→fənn/yük xəritəsi siyahı və detalın mərkəzi journal.view qapısındadır.
"""

from django.db import migrations

_KEY = "journal.view"


def _bypass(schema_editor):
    if schema_editor is not None and schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def forward(apps, schema_editor):
    _bypass(schema_editor)
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name="lab_assistant").iterator():
        permissions = list(role.permissions or [])
        if any(key in permissions for key in (_KEY, "journal.*", "*")):
            continue
        role.permissions = permissions + [_KEY]
        role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    _bypass(schema_editor)
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name="lab_assistant").iterator():
        permissions = list(role.permissions or [])
        if _KEY in permissions:
            role.permissions = [key for key in permissions if key != _KEY]
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("organizations", "0077_lab_assistant_workload_distribution")]
    operations = [migrations.RunPython(forward, backward)]
