"""Dekan müavini (`vice_dean`) rolunu mövcud universitetlərə əkir (2026-09-06).

Səviyyə cədvəlində (`core/constants.py`) vardı, rol kataloqunda yox idi.
0042 (rim_staff) ilə EYNİ naxış: rol varsa TOXUNULMUR, yalnız şablonda olub
sətirdə olmayan açarlar əlavə edilir. Geri dönüş üzvü OLMAYAN rolu silir.
"""

from django.db import migrations

_ROLE_NAME = "vice_dean"


def _specs():
    from apps.organizations.default_roles_vice_dean import VICE_DEAN_ROLES

    return [dict(spec) for spec in VICE_DEAN_ROLES]


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

    for role in Role.objects.filter(name=_ROLE_NAME).iterator():
        if Membership.objects.filter(role=role).exists():
            continue
        role.delete()


class Migration(migrations.Migration):

    dependencies = [("organizations", "0043_org_unit_is_service_unit")]

    operations = [migrations.RunPython(forward, backward)]
