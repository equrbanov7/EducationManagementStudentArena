"""
Mövcud university təşkilatlarına yeni idarəetmə rollarını əlavə edir:
exam_center (imtahan mərkəzi), hr, lead_student.

Yalnız çatışmayan rollar yaradılır — mövcud (o cümlədən manual
redaktə olunmuş) rollara toxunulmur, ona görə təhlükəsiz və idempotentdir.
"""

from django.db import migrations


def seed_university_roles(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    Role = apps.get_model("organizations", "Role")

    # default_roles.py-dəki UNIVERSITY şablonları ilə sinxron saxlanılır.
    # (Migration daxilində import etmirik ki, gələcək şablon dəyişiklikləri
    # tarixi migrationun davranışını dəyişməsin.)
    new_roles = [
        {
            "name": "exam_center",
            "display_name": "Exam Center",
            "level": 85,
            "scope_type": "organization",
            "permissions": [
                "org.view",
                "unit.view",
                "member.view",
                "course.view",
                "exam.*",
                "grade.view",
                "grade.publish",
                "appeal.respond",
                "appeal.decide",
                "appeal.create",
                "qa.*",
                "analytics.view_all",
                "audit.view",
            ],
            "description": "Exam center managing exam lifecycle, monitoring, results and appeals",
        },
        {
            "name": "hr",
            "display_name": "HR",
            "level": 65,
            "scope_type": "organization",
            "permissions": [
                "org.view",
                "unit.view",
                "member.view",
                "member.invite",
                "member.edit",
                "member.remove",
                "role.view",
                "role.assign",
                "analytics.view_unit",
                "audit.view",
            ],
            "description": "HR managing staff, positions and faculty/department assignments",
        },
        {
            "name": "lead_student",
            "display_name": "Lead Student",
            "level": 30,
            "scope_type": "unit",
            "permissions": [
                "course.view",
                "exam.view",
                "appeal.create",
                "member.view",
                "analytics.view_own",
            ],
            "description": "Lead student with limited group-level visibility",
        },
    ]

    university_orgs = Organization.objects.filter(org_type="university")
    for org in university_orgs.iterator():
        existing_names = set(Role.objects.filter(organization=org).values_list("name", flat=True))
        to_create = [
            Role(
                organization=org,
                name=template["name"],
                display_name=template["display_name"],
                level=template["level"],
                scope_type=template["scope_type"],
                permissions=template["permissions"],
                description=template["description"],
                is_system=True,
                is_active=True,
            )
            for template in new_roles
            if template["name"] not in existing_names
        ]
        if to_create:
            Role.objects.bulk_create(to_create)


def unseed_university_roles(apps, schema_editor):
    """Yalnız bu migration-ın yaratdığı istifadə olunmayan rolları silir."""
    Role = apps.get_model("organizations", "Role")
    Role.objects.filter(
        name__in=["exam_center", "hr", "lead_student"],
        is_system=True,
        memberships__isnull=True,
        organization__org_type="university",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0008_backfill_appeal_permissions"),
    ]

    operations = [
        migrations.RunPython(seed_university_roles, unseed_university_roles),
    ]
