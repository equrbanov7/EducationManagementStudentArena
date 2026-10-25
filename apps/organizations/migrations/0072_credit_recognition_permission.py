"""«Xarici nəticənin tanınması» açarı — ``student.credit_recognition`` (sahib 2026-10-25).

Sahib: «Tələbə Erasmus-da və ya başqa universitetdə fənn keçmiş ola bilər — akademik nəticəni göstərə bilər və
o fəndən AZAD oluna». Açar dekanlıq / tədris şöbəsi / RİM-ə verilir (``retake.manage`` ilə EYNİ dəst — 0067);
rektorda ``*`` var. Şablon: ``default_roles_student_services.STUDENT_SERVICES_GRANTS``; dəyərlər burada
SƏTİR-SƏTİR köçürülüb (miqrasiya şablonu import etmir — sonrakı şablon dəyişikliyi tarixi addımı dəyişməsin).

Açar, ``student.*`` wildcard-ı və ya ``*`` artıq varsa toxunulmur. İDEMPOTENT. Geri dönüş yalnız bu açarı götürür.
"""

from django.db import migrations

_KEY = "student.credit_recognition"
_ROLES = ("ikt_rehber", "dean", "vice_dean", "teaching_office_head", "teaching_office_staff")


def _covered(permissions):
    return _KEY in permissions or "student.*" in permissions or "*" in permissions


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
        permissions = list(role.permissions or [])
        if _KEY in permissions:
            role.permissions = [entry for entry in permissions if entry != _KEY]
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [("organizations", "0071_grade_event_trial_purge_exception")]

    operations = [migrations.RunPython(forward, backward)]
