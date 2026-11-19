"""Tyutor / proqram koordinatoru — «qrup dövrəsi» açarları (sahib 2026-11-19).

Sahib: «tyutora özəllik olaraq rol ver ki qrupa tələbə əlavə etmək, qruplardan tələbə köçürmək, qrup yaratmaq …
bütün bu circle-i edə bilsin». Şablon: ``permissions_tutor_circle.TUTOR_CIRCLE_GRANTS``; dəyərlər burada SƏTİR-SƏTİR
köçürülüb (miqrasiya şablonu import etmir — sonrakı şablon dəyişikliyi tarixi addımı dəyişməsin). Koordinator
tyutorla paritet qrupundadır (``ROLE_PARITY_GROUPS``) — dəstlər bərabər qalır.

Açar, ``<prefiks>.*`` wildcard-ı və ya ``*`` artıq varsa toxunulmur. İDEMPOTENT. Geri dönüş yalnız iki YENİ açarı
(``journal.lab_groups``, ``journal.level_cohorts``) götürür — qalanları tenantda əl ilə də verilmiş ola bilər.
"""

from django.db import migrations

_NEW_KEYS = ("journal.lab_groups", "journal.level_cohorts")
_KEYS = (
    "student.records_view",
    "people.view_contacts",
    "people.view_demographics",
    "journal.reassign",
) + _NEW_KEYS
_ROLES = ("tutor", "program_coordinator")


def _covered(permissions, key):
    return key in permissions or f"{key.split('.', 1)[0]}.*" in permissions or "*" in permissions


def _bypass(schema_editor):
    if schema_editor is not None and schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    _bypass(schema_editor)
    for role in Role.objects.filter(name__in=_ROLES).iterator():
        permissions = list(role.permissions or [])
        missing = [key for key in _KEYS if not _covered(permissions, key)]
        if missing:
            role.permissions = permissions + missing
            role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    _bypass(schema_editor)
    for role in Role.objects.filter(name__in=_ROLES).iterator():
        permissions = list(role.permissions or [])
        kept = [entry for entry in permissions if entry not in _NEW_KEYS]
        if kept != permissions:
            role.permissions = kept
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [("organizations", "0085_monitoring_roles")]

    operations = [migrations.RunPython(forward, backward)]
