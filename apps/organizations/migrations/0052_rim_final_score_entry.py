"""Sahibin qərarı (2026-09-14): RİM rəhbəri (`ikt_rehber`) kağız imtahan ballarını
köçürə bilsin — `final_score.entry` açarı (`exam.*` wildcard-ına daxil deyil).

Mövcud tenantlarda `ikt_rehber` adlı rollara açar əlavə olunur (`*` daşıyan
rollar toxunulmur); geri alma yalnız bu miqrasiyanın əlavə etdiyi açarı çıxarır.
"""

from django.db import migrations

_ROLE_NAME = "ikt_rehber"
_KEY = "final_score.entry"


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_ROLE_NAME).iterator():
        permissions = list(role.permissions or [])
        if "*" in permissions or _KEY in permissions:
            continue
        permissions.append(_KEY)
        role.permissions = permissions
        role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_ROLE_NAME).iterator():
        permissions = list(role.permissions or [])
        if _KEY not in permissions:
            continue
        role.permissions = [entry for entry in permissions if entry != _KEY]
        role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("organizations", "0051_permission_catalog_drift")]

    operations = [migrations.RunPython(forward, backward)]
