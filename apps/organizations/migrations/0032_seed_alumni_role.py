"""Mövcud universitet təşkilatlarına «Məzun / arxiv» (``alumni``) rolunu əlavə et.

Yeni təşkilatlar bu rolu ``default_roles`` post_save axını ilə alır; bu migration
onu ARTIQ mövcud universitetlərə geriyə-doldurur.

Rol İCAZƏ VERMİR (``permissions=[]``) — o, yalnız
``registrar_guard_active_member`` trigger-inin tələb etdiyi AKTİV üzvlüyü
təmin edir ki, məzun/xaric tələbənin tarixi jurnal və qiymət sətirləri köçə
bilsin. Girişi bağlayan qapı ``UserProfile.access_state='archived'``-dir
(bax ``apps/accounts/services/identity_archive.py``).
"""

from django.db import migrations

_ALUMNI = {
    "name": "alumni",
    "display_name": "Məzun / arxiv",
    "level": 5,
    "permissions": [],
    "description": "Archived alumni/released student — no access, historical records only",
}


def seed_alumni(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    Role = apps.get_model("organizations", "Role")
    # scope_type "unit" — RoleScopeType.UNIT dəyəri.
    for org in Organization.objects.filter(org_type="university"):
        Role.objects.get_or_create(
            organization=org,
            name=_ALUMNI["name"],
            defaults={
                "display_name": _ALUMNI["display_name"],
                "level": _ALUMNI["level"],
                "scope_type": "unit",
                "permissions": _ALUMNI["permissions"],
                "description": _ALUMNI["description"],
                "is_system": True,
                "is_active": True,
            },
        )


def remove_alumni(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    Role.objects.filter(name="alumni", is_system=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0031_seed_exam_score_entry_permission"),
    ]

    operations = [
        migrations.RunPython(seed_alumni, remove_alumni),
    ]
