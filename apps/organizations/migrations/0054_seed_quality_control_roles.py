"""Keyfiyyətə nəzarət rollarını + anonim sorğu açarlarını MÖVCUD universitetlərə əkir.

Sahib tələbi, 2026-09-25 (anonim müəllim qiymətləndirmə sorğusu). Yeni
təşkilatlar eyni dəsti ``default_roles_university`` → ``default_roles_quality``
şablonundan (signal ilə) alır; bu miqrasiya köhnə tenantları eyni vəziyyətə
gətirir. 0042/0045 ilə EYNİ naxış: rol varsa TOXUNULMUR, yalnız çatışmayan açar
əlavə olunur; ``*`` daşıyan rol (rektor, RİM rəhbəri) onsuz da əhatəlidir.

Spesifikasiya QƏSDƏN burada DONDURULUB (canlı şablon import edilmir): şablon
sonra dəyişsə də bu miqrasiyanın nəticəsi dəyişmir. Paritet testi:
``apps/surveys/tests/test_roles_seed.py``. İdempotentdir; geri dönüş üzvü
OLMAYAN rolu silir və verilmiş ``survey.*`` açarlarını geri götürür.
"""

from django.db import migrations

_RESULTS = "survey.results.view"
_MANAGE = "survey.manage"

_SHARED = [
    "org.view",
    "unit.view",
    "member.view",
    "catalog.view",
    "course.view",
    "analytics.view_all",
    _RESULTS,
]

ROLE_SPECS = [
    {
        "name": "quality_control_head",
        "display_name": "Keyfiyyətə nəzarət şöbəsinin rəhbəri",
        "level": 70,
        "scope_type": "organization",
        "permissions": [*_SHARED, _MANAGE, "application.create"],
        "description": "Quality assurance head — anonymous teaching-evaluation results and survey campaigns",
    },
    {
        "name": "quality_control_staff",
        "display_name": "Keyfiyyətə nəzarət əməkdaşı",
        "level": 60,
        "scope_type": "organization",
        "permissions": [*_SHARED, "application.create"],
        "description": "Quality assurance staff — anonymous teaching-evaluation results (read-only)",
    },
]

#: Mövcud rollara verilən açarlar (şablonun ``SURVEY_GRANTS`` xəritəsi ilə eyni).
GRANTS = {
    "chair_head": (_RESULTS,),
    "teaching_office_head": (_RESULTS,),
    "teaching_office_staff": (_RESULTS,),
    "vice_rector": (_RESULTS,),
}


def forward(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    Role = apps.get_model("organizations", "Role")

    for organization in Organization.objects.filter(org_type="university").iterator():
        for spec in ROLE_SPECS:
            role = Role.objects.filter(organization=organization, name=spec["name"]).first()
            if role is None:
                Role.objects.create(
                    organization=organization,
                    name=spec["name"],
                    display_name=spec["display_name"],
                    description=spec["description"],
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

    for role in Role.objects.filter(name__in=list(GRANTS)).iterator():
        permissions = list(role.permissions or [])
        if "*" in permissions or "survey.*" in permissions:
            continue
        missing = [key for key in GRANTS[role.name] if key not in permissions]
        if missing:
            role.permissions = permissions + missing
            role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Membership = apps.get_model("organizations", "Membership")
    Role = apps.get_model("organizations", "Role")

    for role in Role.objects.filter(name__in=[spec["name"] for spec in ROLE_SPECS]).iterator():
        if Membership.objects.filter(role=role).exists():
            continue
        role.delete()
    for role in Role.objects.filter(name__in=list(GRANTS)).iterator():
        permissions = list(role.permissions or [])
        remaining = [key for key in permissions if key not in (_RESULTS, _MANAGE)]
        if len(remaining) != len(permissions):
            role.permissions = remaining
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [("organizations", "0053_rim_full_permissions")]

    operations = [migrations.RunPython(forward, backward)]
