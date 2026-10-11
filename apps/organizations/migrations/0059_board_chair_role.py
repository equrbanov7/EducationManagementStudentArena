"""«Qəyyumlar Şurasının sədri» (`board_chair`) rolu + Hüseynqulu Bağırovun ona keçirilməsi (sahib 2026-10-11).

Sahib: «Hüseynqulu Bağırovu hər şeydən yuxarı qoy — superadmin qədər olmasa da, rektor kimi hər şeyə
əlaqəsi olsun və siyahının başına qaldır». Rolun izahı ``default_roles_oversight.py``-dadır
(`*`, səviyyə 110 — rektordan yuxarı, superadmin DEYİL).

1. Hər universitet təşkilatında rol yoxdursa yaradılır (0045 naxışı; varsa TOXUNULMUR) — İDEMPOTENT.
2. ``huseynqulu.bagirov`` istifadəçisinin həmin təşkilatdakı AKTİV ``trustee`` üzvlüyü ``board_chair``-ə
   keçirilir (vahidi — «Qəyyumlar şurası» — və digər sahələr qalır; siyahıda iki sətir yaranmasın deyə
   yeni üzvlük YARADILMIR). İstifadəçi və ya üzvlük yoxdursa heç nə edilmir (test/klon bazaları).

Geri dönüş: həmin üzvlük yenidən ``trustee`` olur; üzvü qalmayan ``board_chair`` rolu silinir.
"""

from django.db import migrations

_ROLE = "board_chair"
_FROM_ROLE = "trustee"
_USERNAME = "huseynqulu.bagirov"


def _spec():
    from apps.organizations.default_roles_oversight import OVERSIGHT_ROLES

    return next(dict(spec) for spec in OVERSIGHT_ROLES if spec["name"] == _ROLE)


def forward(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    Role = apps.get_model("organizations", "Role")
    Membership = apps.get_model("organizations", "Membership")
    spec = _spec()

    for organization in Organization.objects.filter(org_type="university").iterator():
        role = Role.objects.filter(organization=organization, name=_ROLE).first()
        if role is None:
            role = Role.objects.create(
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
        Membership.objects.filter(
            organization=organization,
            is_active=True,
            role__organization=organization,
            role__name=_FROM_ROLE,
            user__username=_USERNAME,
        ).update(role=role)


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    Membership = apps.get_model("organizations", "Membership")
    for role in Role.objects.filter(name=_ROLE).iterator():
        trustee = Role.objects.filter(organization_id=role.organization_id, name=_FROM_ROLE).first()
        if trustee is not None:
            Membership.objects.filter(role=role, user__username=_USERNAME).update(role=trustee)
        if not Membership.objects.filter(role=role).exists():
            role.delete()


class Migration(migrations.Migration):

    dependencies = [("organizations", "0058_hr_analytics_permission")]

    operations = [migrations.RunPython(forward, backward)]
