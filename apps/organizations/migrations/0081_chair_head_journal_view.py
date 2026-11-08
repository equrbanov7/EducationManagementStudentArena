"""Kafedra müdiri öz kafedrasının jurnallarını yalnız oxuya bilir (sahib 2026-11-07).

Sahib: «Təşkilat Admini deyil, Kafedra müdiridir … öz kafedrasında olan müəllimlərin jurnallarına baxış olsun».
UNIT əhatəli ``journal.view`` kafedra kökündə kafedranın açılışlarını verir (``journal_scope.journal_view_q``).
Yazı/korrektor/admin açarları və üzvlük scope-ları dəyişdirilmir. ``0078_lab_assistant_journal_view`` naxışı.
"""

from django.db import migrations

_KEY = "journal.view"


def _bypass(schema_editor):
    if schema_editor is not None and schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def forward(apps, schema_editor):
    _bypass(schema_editor)
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name="chair_head").iterator():
        permissions = list(role.permissions or [])
        if any(key in permissions for key in (_KEY, "journal.*", "*")):
            continue
        role.permissions = permissions + [_KEY]
        role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    _bypass(schema_editor)
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name="chair_head").iterator():
        permissions = list(role.permissions or [])
        if _KEY in permissions:
            role.permissions = [key for key in permissions if key != _KEY]
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("organizations", "0080_dean_subgroup_management")]
    operations = [migrations.RunPython(forward, backward)]
