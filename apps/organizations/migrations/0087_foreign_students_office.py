"""«Əcnəbi tələbələrlə iş şöbəsi» rolları + əcnəbi qrupları əhatəsi MÖVCUD universitetlərə — sahib 2026-11-25.

Sahib: «Beynəlxalq şöbə əməkdaşı rolu olsun … əcnəbi qruplarını görsün, 5 ədəddi bizdə; qrupla tələbə əlavə etmək,
dondurmaq, uzaqlaşdırmaq olsun; tələbəni sistemə əlavə etmək də olsun … elə bil proqram koordinatorunun».
Şablon: ``default_roles_foreign_office``; canlı qarşılıq: ``foreign_office_sync`` (əmr ``sync_foreign_students_office``).

1. ROLLAR: yoxdursa yaradılır; varsa çatışmayan açar əlavə olunur (``*`` toxunulmur). Dəst burada DONDURULUB.
2. ƏHATƏ: adında «əcnəbi» olan akademik OLMAYAN bölmədəki aktiv ``admin_unit_head`` → ``foreign_students_head``,
   ``member`` → ``foreign_students_staff``; hər birinə hər aktiv əcnəbi QRUPU (``group`` tipli, adında «əcnəbi») üçün
   ayrıca UNIT üzvlüyü. Köhnə şöbə üzvlüyü QALIR. Heç nə silinmir.

Geri dönüş: bu rolların qrup üzvlükləri passivləşdirilir (silinmir); rol sətirləri yerində qalır.
"""

from django.db import migrations

_HEAD = "foreign_students_head"
_STAFF = "foreign_students_staff"

_PERMISSIONS = [
    "member.view",
    "course.view",
    "exam.view",
    "appeal.create",
    "people.view_students",
    "people.view_contacts",
    "people.view_demographics",
    "people.manage_academic",
    "group.manage",
    "unit.view",
    "unit.group_manage",
    "student.assign_group",
    "student.records_view",
    "student.registry_view",
    "journal.roster",
    "journal.reassign",
    "journal.lab_groups",
    "journal.level_cohorts",
    "catalog.view",
    "plan.view",
    "schedule.view",
    "schedule.manage",
    "syllabus.view",
    "subject_folder.view_unit",
    "analytics.view_unit",
    "student.movement",
    "user.import",
    "journal.view",
    "grade.view",
    "application.create",
]

ROLE_SPECS = [
    {
        "name": _HEAD,
        "display_name": "Əcnəbi tələbələrlə iş şöbəsinin müdiri",
        "level": 55,
        "description": "Foreign students office head — full student circle limited to the foreign-student groups",
    },
    {
        "name": _STAFF,
        "display_name": "Əcnəbi tələbələrlə iş şöbəsinin əməkdaşı",
        "level": 50,
        "description": "Foreign students office staff — full student circle limited to the foreign-student groups",
    },
]

DEPARTMENT_ROLE_MAP = {"admin_unit_head": _HEAD, "member": _STAFF}
ACADEMIC_UNIT_TYPES = frozenset({"faculty", "chair", "specialty", "group", "deanery"})
_KEYWORD = "əcnəbi"


def _fold(text) -> str:
    value = str(text or "")
    for source, target in (("İ", "i"), ("I", "i"), ("ı", "i"), ("Ə", "ə")):
        value = value.replace(source, target)
    return value.lower()


def _bypass(schema_editor):
    if schema_editor is not None and schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def _ensure_roles(Role, organization) -> dict:
    roles = {}
    for spec in ROLE_SPECS:
        role = Role.objects.filter(organization=organization, name=spec["name"]).first()
        if role is None:
            role = Role.objects.create(
                organization=organization,
                name=spec["name"],
                display_name=spec["display_name"],
                description=spec["description"],
                level=spec["level"],
                scope_type="unit",
                permissions=list(_PERMISSIONS),
                is_system=True,
                is_active=True,
            )
        else:
            permissions = list(role.permissions or [])
            missing = [key for key in _PERMISSIONS if key not in permissions]
            if missing and "*" not in permissions:
                role.permissions = permissions + missing
                role.save(update_fields=["permissions"])
        roles[spec["name"]] = role
    return roles


def forward(apps, schema_editor):
    _bypass(schema_editor)
    Membership = apps.get_model("organizations", "Membership")
    Organization = apps.get_model("organizations", "Organization")
    OrgUnit = apps.get_model("organizations", "OrgUnit")
    Role = apps.get_model("organizations", "Role")
    for organization in Organization.objects.filter(org_type="university").iterator():
        roles = _ensure_roles(Role, organization)
        groups = [
            unit
            for unit in OrgUnit.objects.filter(organization=organization, unit_type="group", is_active=True)
            if _KEYWORD in _fold(unit.name)
        ]
        people = {}
        for membership in Membership.objects.filter(
            organization=organization,
            is_active=True,
            role__name__in=list(DEPARTMENT_ROLE_MAP),
            scope_unit__isnull=False,
            scope_unit__is_active=True,
        ).select_related("role", "scope_unit"):
            unit = membership.scope_unit
            if unit.unit_type in ACADEMIC_UNIT_TYPES or _KEYWORD not in _fold(unit.name):
                continue
            if people.get(membership.user_id) == _HEAD:
                continue
            people[membership.user_id] = DEPARTMENT_ROLE_MAP[membership.role.name]
        for user_id, role_name in people.items():
            for group in groups:
                row, created = Membership.objects.get_or_create(
                    user_id=user_id,
                    organization=organization,
                    role=roles[role_name],
                    scope_unit=group,
                    defaults={"is_active": True, "is_primary": False},
                )
                if not created and not row.is_active:
                    row.is_active = True
                    row.save(update_fields=["is_active"])


def backward(apps, schema_editor):
    _bypass(schema_editor)
    Membership = apps.get_model("organizations", "Membership")
    Membership.objects.filter(role__name__in=[_HEAD, _STAFF], is_active=True).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [("organizations", "0086_tutor_group_circle")]
    operations = [migrations.RunPython(forward, backward)]
