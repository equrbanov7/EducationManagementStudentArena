"""Mövcud universitet təşkilatlarına "İKT Rəhbəri" (ikt_rehber) rolunu əlavə et.

Yeni təşkilatlar bu rolu post_save signal-ı (default_roles) ilə alır; bu migration
onu ARTIQ mövcud olan universitetlərə geriyə-doldurur. Rol jurnal düzəliş
(journal.correct) icazəsinə malikdir → 2 saat/bitmiş-semestr limitlərini sənədli
düzəlişlə keçir; bütün əməllər audit olunur.
"""

from django.db import migrations

_IKT_REHBER = {
    "name": "ikt_rehber",
    "display_name": "İKT Rəhbəri",
    "level": 88,
    "permissions": [
        "org.view",
        "org.edit",
        "unit.*",
        "member.*",
        "course.*",
        "exam.*",
        "grade.*",
        "journal.correct",
        "appeal.respond",
        "appeal.decide",
        "qa.*",
        "analytics.view_all",
        "audit.view",
    ],
    "description": (
        "ICT manager — documented journal-correction override (bypasses edit-window & "
        "closed semesters), full exam-centre + structure access; every action audited"
    ),
}


def seed_ikt_rehber(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    Role = apps.get_model("organizations", "Role")
    # scope_type "organization" — RoleScopeType.ORGANIZATION dəyəri.
    for org in Organization.objects.filter(org_type="university"):
        Role.objects.get_or_create(
            organization=org,
            name=_IKT_REHBER["name"],
            defaults={
                "display_name": _IKT_REHBER["display_name"],
                "level": _IKT_REHBER["level"],
                "scope_type": "organization",
                "permissions": _IKT_REHBER["permissions"],
                "description": _IKT_REHBER["description"],
                "is_system": True,
                "is_active": True,
            },
        )


def remove_ikt_rehber(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    Role.objects.filter(name="ikt_rehber", is_system=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0025_rls_org_functional_indexes"),
    ]

    operations = [
        migrations.RunPython(seed_ikt_rehber, remove_ikt_rehber),
    ]
