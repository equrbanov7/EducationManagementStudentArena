"""«Fəndən azad etmə» (``student.credit_recognition``) — RİM əməkdaşına da (sahib 2026-11-27).

Sahib: fəndən azad etməni (səbəb + sənəd + bal) RİM rəhbəri, RİM işçisi və dekanlıq etsin. Rəhbər, dekan, dekan
müavini və tədris şöbəsi açarı 0072-dən daşıyır; bu addım yalnız ``rim_staff`` rolunu əlavə edir (şablon:
``default_roles_student_services.STUDENT_SERVICES_GRANTS``). Açar, ``student.*`` və ya ``*`` artıq varsa
toxunulmur. İDEMPOTENT; geri dönüş yalnız bu açarı götürür.
"""

from django.db import migrations

_KEY = "student.credit_recognition"
_ROLES = ("rim_staff",)


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

    dependencies = [("organizations", "0087_foreign_students_office")]

    operations = [migrations.RunPython(forward, backward)]
