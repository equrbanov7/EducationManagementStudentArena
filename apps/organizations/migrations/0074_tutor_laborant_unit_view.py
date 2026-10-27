"""Tyutor / proqram koordinatoru / laborant (+ qəyyum) — kafedranın sillabus və dərs materialına OXU (sahib 2026-10-27).

Sahib: «tyutor və laborantlar müəllimlərin keçilmiş dərs yükünə baxa bilsin, əlavə olaraq özlərinə aid olan
kafedra sillabusa, dərs materialı varsa ona baxmaq olsun». Şablon: ``permissions_unit_view.UNIT_VIEW_GRANTS``;
dəyərlər burada SƏTİR-SƏTİR köçürülüb (miqrasiya şablonu import etmir — sonrakı şablon dəyişikliyi tarixi addımı
dəyişməsin). Koordinator tyutorla paritet qrupundadır (``ROLE_PARITY_GROUPS``) — dəstlər bərabər qalır.

Açar, ``<prefiks>.*`` wildcard-ı və ya ``*`` artıq varsa toxunulmur. İDEMPOTENT. Geri dönüş yalnız YENİ açarı
(``subject_folder.view_unit``) götürür — ``syllabus.view`` tenantda əl ilə də verilmiş ola bilər, ona toxunulmur.
"""

from django.db import migrations

_NEW_KEY = "subject_folder.view_unit"
_KEYS = ("syllabus.view", _NEW_KEY)
_ROLES = ("tutor", "program_coordinator", "lab_assistant")
#: Qəyyum «hər şeyi görür» (sahib 2026-10-17) — yalnız YENİ oxu açarı (sillabus onda artıq var).
_TRUSTEE = "trustee"


def _covered(permissions, key):
    return key in permissions or f"{key.split('.', 1)[0]}.*" in permissions or "*" in permissions


def _bypass(schema_editor):
    if schema_editor is not None and schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    _bypass(schema_editor)
    for role in Role.objects.filter(name__in=_ROLES + (_TRUSTEE,)).iterator():
        permissions = list(role.permissions or [])
        keys = (_NEW_KEY,) if role.name == _TRUSTEE else _KEYS
        missing = [key for key in keys if not _covered(permissions, key)]
        if missing:
            role.permissions = permissions + missing
            role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    _bypass(schema_editor)
    for role in Role.objects.filter(name__in=_ROLES + (_TRUSTEE,)).iterator():
        permissions = list(role.permissions or [])
        if _NEW_KEY in permissions:
            role.permissions = [entry for entry in permissions if entry != _NEW_KEY]
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [("organizations", "0073_grade_event_attempt_purge_exception")]

    operations = [migrations.RunPython(forward, backward)]
