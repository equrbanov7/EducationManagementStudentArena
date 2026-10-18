"""«Mühasib» (`accountant`) rolu + `accounting.view` / `retake.*` açarları (sahib 2026-10-18).

Şablon və izah: ``default_roles_accounting.py`` / ``permissions_accounting.py``. Dəyərlər burada SƏTİR-SƏTİR
köçürülüb (miqrasiya şablonu import etmir — sonrakı şablon dəyişikliyi tarixi addımı dəyişməsin).

1. Hər universitet təşkilatında ``accountant`` rolu yoxdursa yaradılır (0059 naxışı; varsa TOXUNULMUR).
2. Mövcud rol sətirlərinə açarlar əlavə olunur: ``accounting.view`` → `ikt_rehber`, `trustee`;
   ``retake.manage`` → `dean`, `vice_dean`, `teaching_office_head`, `teaching_office_staff`, `ikt_rehber`.
   Açar, onun ``<prefiks>.*`` wildcard-ı və ya ``*`` artıq varsa toxunulmur. İDEMPOTENT.

Geri dönüş: yalnız bu miqrasiyanın əlavə etdiyi açarlar götürülür; üzvü olmayan ``accountant`` rolu silinir
(üzvü varsa rol qalır — təyinat itməsin).
"""

from django.db import migrations

_ROLE = "accountant"
_ROLE_SPEC = {
    "display_name": "Mühasib",
    "description": "Accountant — monthly held teaching hours vs plan (read-only) and retake payment checks",
    "level": 58,
    "scope_type": "organization",
    "permissions": [
        "accounting.view",
        "retake.payment_verify",
        "application.create",
    ],
}
_GRANTS = {
    "ikt_rehber": ("accounting.view", "retake.manage"),
    "trustee": ("accounting.view",),
    "dean": ("retake.manage",),
    "vice_dean": ("retake.manage",),
    "teaching_office_head": ("retake.manage",),
    "teaching_office_staff": ("retake.manage",),
}


def _covered(permissions, key):
    return key in permissions or f"{key.split('.', 1)[0]}.*" in permissions or "*" in permissions


def forward(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    Role = apps.get_model("organizations", "Role")
    for organization in Organization.objects.filter(org_type="university").iterator():
        if not Role.objects.filter(organization=organization, name=_ROLE).exists():
            Role.objects.create(
                organization=organization,
                name=_ROLE,
                display_name=_ROLE_SPEC["display_name"],
                description=_ROLE_SPEC["description"],
                level=_ROLE_SPEC["level"],
                scope_type=_ROLE_SPEC["scope_type"],
                permissions=list(_ROLE_SPEC["permissions"]),
                is_system=True,
                is_active=True,
            )
    for role in Role.objects.filter(name__in=list(_GRANTS)).iterator():
        permissions = list(role.permissions or [])
        added = [key for key in _GRANTS[role.name] if not _covered(permissions, key)]
        if added:
            role.permissions = permissions + added
            role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    Membership = apps.get_model("organizations", "Membership")
    for role in Role.objects.filter(name__in=list(_GRANTS)).iterator():
        granted = set(_GRANTS[role.name])
        permissions = [entry for entry in (role.permissions or []) if entry not in granted]
        if permissions != list(role.permissions or []):
            role.permissions = permissions
            role.save(update_fields=["permissions"])
    for role in Role.objects.filter(name=_ROLE).iterator():
        if not Membership.objects.filter(role=role).exists():
            role.delete()


class Migration(migrations.Migration):

    dependencies = [("organizations", "0066_trustee_read_all")]

    operations = [migrations.RunPython(forward, backward)]
