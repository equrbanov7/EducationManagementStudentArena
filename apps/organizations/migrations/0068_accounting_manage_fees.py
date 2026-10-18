"""`accounting.manage_fees` — «Təhsil haqqı cədvəli» açarı (sahib 2026-10-19: 25% məbləği illik haqqa görə).

Şablon: ``default_roles_accounting.py`` (``accountant`` + ``ikt_rehber``). Dəyərlər SƏTİR-SƏTİR köçürülüb
(miqrasiya şablonu import etmir). Açar, onun ``accounting.*`` wildcard-ı və ya ``*`` artıq varsa toxunulmur.
İDEMPOTENT. Geri dönüş yalnız bu açarı götürür.
"""

from django.db import migrations

_KEY = "accounting.manage_fees"
_ROLES = ("accountant", "ikt_rehber")


def _covered(permissions):
    return _KEY in permissions or "accounting.*" in permissions or "*" in permissions


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name__in=_ROLES).iterator():
        permissions = list(role.permissions or [])
        if not _covered(permissions):
            role.permissions = permissions + [_KEY]
            role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name__in=_ROLES).iterator():
        permissions = [entry for entry in (role.permissions or []) if entry != _KEY]
        if permissions != list(role.permissions or []):
            role.permissions = permissions
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [("organizations", "0067_accounting_retake_permissions")]

    operations = [migrations.RunPython(forward, backward)]
