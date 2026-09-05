"""RİM (Rəqəmsal İnkişaf Mərkəzi) əməkdaşı rolunu əkir — sahib tələbi, 2026-09-06.

`ikt_rehber` (88) mərkəzin RƏHBƏRİDİR; əməkdaşlar üçün məhdud səlahiyyətli
ayrıca sistem rolu (`rim_staff`, 60) hər universitet tipli təşkilatda yaradılır.
Rol artıq varsa TOXUNULMUR — yalnız şablonda olub, sətirdə olmayan açarlar
əlavə edilir (0039 ilə eyni naxış). İdempotentdir.

Geri dönüş yalnız üzvü OLMAYAN rolu silir (üzvlük itməsin).
"""

from django.db import migrations

_ROLE_NAME = "rim_staff"


def _role_specs():
    from apps.organizations.default_roles_rim import RIM_STAFF_ROLES

    return [dict(spec) for spec in RIM_STAFF_ROLES]


def forward(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    Role = apps.get_model("organizations", "Role")

    for organization in Organization.objects.filter(org_type="university").iterator():
        for spec in _role_specs():
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

    dependencies = [("organizations", "0041_seed_stage2_permissions")]

    operations = [migrations.RunPython(forward, backward)]
