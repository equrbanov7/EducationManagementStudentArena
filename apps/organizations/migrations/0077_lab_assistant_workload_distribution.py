"""Laborant — öz kafedrasının «Yük bölgüsü»nə baxış + redaktə (sahib 2026-10-29).

Şablon: ``permissions_lab_workload.LAB_WORKLOAD_GRANTS``; dəyərlər burada SƏTİR-SƏTİR köçürülüb (miqrasiya şablonu
import etmir — sonrakı şablon dəyişikliyi tarixi addımı dəyişməsin). Açar, ``workload.*`` və ya ``*`` artıq varsa
toxunulmur. İDEMPOTENT. Geri dönüş yalnız ``workload.manage`` / ``workload.distribute``-u götürür
(``workload.view`` laborantda əvvəldən var idi).
"""

from django.db import migrations

_ROLE = "lab_assistant"
_KEYS = ("workload.view", "workload.manage", "workload.distribute")
_REVERTED = ("workload.manage", "workload.distribute")


def _covered(permissions, key):
    return key in permissions or f"{key.split('.', 1)[0]}.*" in permissions or "*" in permissions


def _bypass(schema_editor):
    if schema_editor is not None and schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    _bypass(schema_editor)
    for role in Role.objects.filter(name=_ROLE).iterator():
        permissions = list(role.permissions or [])
        missing = [key for key in _KEYS if not _covered(permissions, key)]
        if missing:
            role.permissions = permissions + missing
            role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    _bypass(schema_editor)
    for role in Role.objects.filter(name=_ROLE).iterator():
        permissions = list(role.permissions or [])
        kept = [entry for entry in permissions if entry not in _REVERTED]
        if kept != permissions:
            role.permissions = kept
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [("organizations", "0076_vice_dean_application_handle")]

    operations = [migrations.RunPython(forward, backward)]
