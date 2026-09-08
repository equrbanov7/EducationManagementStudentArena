"""Laborant → «Keçilmiş dərslər» nəzarət görünüşü (2026-09-08).

SAHİBİN QƏRARI: «bu hissə laborantlarda da olsun, aid olduğu kafedraya aid,
müəllimlərin yükünə baxa bilsin». Şablon (``default_roles_university``) yeni
tenant üçün yeniləndi; bu miqrasiya MÖVCUD tenantların ``lab_assistant`` roluna
(a) oxu-only ``journal.lessons_unit`` açarını idempotent əkir (0047 üsulu) və
(b) rolu UNIT-əhatəli edir ki, üzvlüyün ``scope_unit``-i (kafedra) görünüş
sahəsi olsun — COURSE əhatəli rolda struktur alt-ağacı heç vaxt açılmır.

Geri dönüş açarı çıxarır və əhatəni COURSE-a qaytarır. Rol yaradılmır.
"""

from django.db import migrations

_ROLE = "lab_assistant"
_KEY = "journal.lessons_unit"
_WILDCARD = "*"


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_ROLE).iterator():
        permissions = list(role.permissions or [])
        fields = []
        if _WILDCARD not in permissions and _KEY not in permissions and "journal.*" not in permissions:
            permissions.append(_KEY)
            role.permissions = permissions
            fields.append("permissions")
        if role.scope_type == "course":
            role.scope_type = "unit"
            fields.append("scope_type")
        if fields:
            role.save(update_fields=fields)


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_ROLE).iterator():
        permissions = [key for key in (role.permissions or []) if key != _KEY]
        fields = []
        if permissions != list(role.permissions or []):
            role.permissions = permissions
            fields.append("permissions")
        if role.scope_type == "unit":
            role.scope_type = "course"
            fields.append("scope_type")
        if fields:
            role.save(update_fields=fields)


class Migration(migrations.Migration):
    dependencies = [("organizations", "0047_program_coordinator_group_grants")]

    operations = [migrations.RunPython(forward, backward)]
