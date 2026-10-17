"""Qəyyumlar Şurası üzvü (`trustee`) — bütün OXU açarları (sahib 2026-10-17: «hər şeyi açıq edə bilərsən»).

Mövcud tenantların `trustee` rol sətirlərinə `default_roles_oversight.TRUSTEE_READ_ALL_2026_10_17` əlavə olunur
(yazma açarı yoxdur). İdempotent; açar / wildcard / `*` artıq varsa toxunulmur. Geri dönüş: yalnız bu miqrasiyanın
əlavə etdiyi açarlar götürülür.
"""

from django.db import migrations

_ROLE = "trustee"
_KEYS = (
    "analytics.view_unit",
    "exam.view",
    "grade.view",
    "group.view",
    "journal.view",
    "people.hr_analytics",
    "people.view_contacts",
    "people.view_demographics",
    "people.view_students",
    "people.view_teachers",
    "plan.view",
    "role.view",
    "semester.view",
    "student.records_view",
    "student.registry_view",
    "survey.results.view",
    "user.search",
)


def _covered(permissions, key):
    return key in permissions or f"{key.split('.', 1)[0]}.*" in permissions or "*" in permissions


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_ROLE).iterator():
        permissions = list(role.permissions or [])
        added = [key for key in _KEYS if not _covered(permissions, key)]
        if added:
            role.permissions = permissions + added
            role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_ROLE).iterator():
        permissions = [entry for entry in (role.permissions or []) if entry not in _KEYS]
        if permissions != list(role.permissions or []):
            role.permissions = permissions
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [("organizations", "0065_semester_view_dean_chair_only")]

    operations = [migrations.RunPython(forward, backward)]
