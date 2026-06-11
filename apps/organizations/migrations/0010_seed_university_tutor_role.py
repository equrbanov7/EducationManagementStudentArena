"""
Mövcud university təşkilatlarına `tutor` (tyutor) rolunu əlavə edir.

Tyutor — tələbə qruplarına akademik dəstək rolu: öz unit alt-ağacındakı
tələbələri, kursları və qrup statistikasını görür; imtahan yaratmır,
qiymət vermir, üzv idarə etmir. Yalnız çatışmayan rol yaradılır (idempotent).
"""

from django.db import migrations

TUTOR_TEMPLATE = {
    "name": "tutor",
    "display_name": "Tutor",
    "level": 40,
    "scope_type": "unit",
    "permissions": [
        "member.view",
        "course.view",
        "exam.view",
        "analytics.view_unit",
        # default_roles._augment_with_appeal_permissions ilə eyni qayda:
        # exam.view olan rola appeal.create verilir.
        "appeal.create",
    ],
    "description": "Tutor providing academic guidance to student groups within their unit",
}


def seed_tutor_role(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    Role = apps.get_model("organizations", "Role")

    for org in Organization.objects.filter(org_type="university").iterator():
        if not Role.objects.filter(organization=org, name=TUTOR_TEMPLATE["name"]).exists():
            Role.objects.create(
                organization=org,
                name=TUTOR_TEMPLATE["name"],
                display_name=TUTOR_TEMPLATE["display_name"],
                level=TUTOR_TEMPLATE["level"],
                scope_type=TUTOR_TEMPLATE["scope_type"],
                permissions=TUTOR_TEMPLATE["permissions"],
                description=TUTOR_TEMPLATE["description"],
                is_system=True,
                is_active=True,
            )


def unseed_tutor_role(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    Role.objects.filter(
        name="tutor",
        is_system=True,
        memberships__isnull=True,
        organization__org_type="university",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0009_seed_university_management_roles"),
    ]

    operations = [
        migrations.RunPython(seed_tutor_role, unseed_tutor_role),
    ]
