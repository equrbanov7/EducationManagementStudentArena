"""Qəyyum (`trustee`) və inzibati şöbə müdiri (`admin_unit_head`) rollarını əkir.

Sahib qərarı, 2026-09-06: heyət siyahısında bu iki vəzifə qrupunun sistemdə
qarşılığı yox idi. Səlahiyyət dəstlərinin izahı `default_roles_oversight.py`-dadır
(qəyyum üçün SIFIR yazma açarı; səviyyə 78 — 80-dən aşağı, çünki 80+ implicit
``org_admin`` aliası gətirir).

0042/0044 ilə EYNİ naxış: rol varsa TOXUNULMUR, yalnız şablonda olub sətirdə
olmayan açarlar əlavə edilir. İdempotentdir. Geri dönüş üzvü OLMAYAN rolu silir.
"""

from django.db import migrations

_ROLE_NAMES = ("trustee", "admin_unit_head")


def _specs():
    from apps.organizations.default_roles_oversight import OVERSIGHT_ROLES

    return [dict(spec) for spec in OVERSIGHT_ROLES]


def forward(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    Role = apps.get_model("organizations", "Role")

    for organization in Organization.objects.filter(org_type="university").iterator():
        for spec in _specs():
            role = Role.objects.filter(organization=organization, name=spec["name"]).first()
            if role is None:
                Role.objects.create(
                    organization=organization,
                    name=spec["name"],
                    display_name=spec["display_name"],
                    description=spec.get("description", ""),
                    level=spec["level"],
                    scope_type=spec["scope_type"],
                    permissions=list(spec["permissions"]),
                    is_system=True,
                    is_active=True,
                )
                continue
            permissions = list(role.permissions or [])
            if "*" in permissions:
                continue
            missing = [key for key in spec["permissions"] if key not in permissions]
            if missing:
                role.permissions = permissions + missing
                role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Membership = apps.get_model("organizations", "Membership")
    Role = apps.get_model("organizations", "Role")

    for role in Role.objects.filter(name__in=_ROLE_NAMES).iterator():
        if Membership.objects.filter(role=role).exists():
            continue
        role.delete()


class Migration(migrations.Migration):

    dependencies = [("organizations", "0044_seed_vice_dean_role")]

    operations = [migrations.RunPython(forward, backward)]
