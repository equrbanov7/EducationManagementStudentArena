"""Monitorinq şöbəsi rolları (``monitoring_head`` / ``monitoring_staff``) MÖVCUD universitetlərə — sahib 2026-11-19.

Sahib: «Monitorinq şöbəsinə jurnallara, sillabuslara, fənn qovluqlarına FULL baxmaq icazəsi ver. Dərs cədvəlinə,
cədvəl idarəetməsinə baxmaq icazəsi olsun … Keçilmiş dərslərə və s.» Yeni təşkilatlar eyni dəsti
``default_roles_monitoring`` şablonundan (signal ilə) alır; bu miqrasiya köhnə tenantları eyni vəziyyətə gətirir.

1. ROLLAR (0054 naxışı): rol yoxdursa yaradılır; varsa yalnız çatışmayan açar əlavə olunur (``*`` toxunulmur).
   Spesifikasiya QƏSDƏN burada DONDURULUB — paritet testi: ``organizations/tests/test_monitoring_roles_2026_11_19``.
2. ÜZVLÜKLƏR: bölməsinin adında «monitorinq» olan AKTİV üzvlüklər köçürülür — ``admin_unit_head`` →
   ``monitoring_head``, ``member`` → ``monitoring_staff``. ``scope_unit`` üzvlükdə QALIR (üzv reyestrində şöbəsi
   görünsün); ORGANIZATION əhatəli rolda o, icazə əhatəsini daraltmır (``scoping.get_permission_scope``).
   Hədəf rolda eyni bölmə ilə üzvlük artıq varsa köhnə sətir toxunulmur (unikal məhdudiyyət, heç nə silinmir).
   AKADEMİK bölmə (fakültə / kafedra / ixtisas / qrup — məs. «Ekoloji monitorinq kafedrası») QƏSDƏN düşmür:
   onun ``member`` üzvü org-wide oxu rolu almamalıdır. «Monitorinq şöbəsi»nin tipi ``department``-dir.

Geri dönüş: eyni ad qaydası ilə üzvlüklər əvvəlki rola qayıdır; rol sətirləri yerində qalır.
"""

from django.db import migrations

_HEAD = "monitoring_head"
_STAFF = "monitoring_staff"
_UNIT_KEYWORD = "monitorinq"

_PERMISSIONS = [
    "unit.view",
    "member.view",
    "catalog.view",
    "course.view",
    "schedule.view",
    "syllabus.view",
    "subject_folder.view_unit",
    "journal.view",
    "journal.lessons_unit",
    "grade.view",
    "group.view",
    "people.view_teachers",
    "people.view_students",
    "plan.view",
    "semester.view",
    "workload.view",
    "workload.report",
    "analytics.view_all",
    "analytics.view_unit",
    "student.records_view",
    "student.registry_view",
    "application.create",
]

ROLE_SPECS = [
    {
        "name": _HEAD,
        "display_name": "Monitorinq şöbəsinin müdiri",
        "level": 70,
        "scope_type": "organization",
        "permissions": list(_PERMISSIONS),
        "description": "Monitoring department head — organization-wide read-only view of the teaching process",
    },
    {
        "name": _STAFF,
        "display_name": "Monitorinq şöbəsinin əməkdaşı",
        "level": 60,
        "scope_type": "organization",
        "permissions": list(_PERMISSIONS),
        "description": "Monitoring department staff — organization-wide read-only view of the teaching process",
    },
]

#: Köhnə rol → yeni rol (yalnız «monitorinq» bölməsindəki aktiv üzvlüklər).
MEMBERSHIP_MOVES = {"admin_unit_head": _HEAD, "member": _STAFF}
#: Bu tipli (akademik) bölmənin adı «monitorinq» daşısa da üzvlükləri köçürülmür.
ACADEMIC_UNIT_TYPES = frozenset({"faculty", "chair", "specialty", "group"})


def _bypass(schema_editor):
    if schema_editor is not None and schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def is_monitoring_unit(name, unit_type="") -> bool:
    """Monitorinq şöbəsidirmi: adında «monitorinq» (böyük/kiçik hərf, İ/I/ı fərqsiz) və akademik bölmə deyil."""
    if unit_type in ACADEMIC_UNIT_TYPES:
        return False
    text = str(name or "")
    for source, target in (("İ", "i"), ("I", "i"), ("ı", "i")):
        text = text.replace(source, target)
    return _UNIT_KEYWORD in text.lower()


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
                scope_type=spec["scope_type"],
                permissions=list(spec["permissions"]),
                is_system=True,
                is_active=True,
            )
        else:
            permissions = list(role.permissions or [])
            missing = [key for key in spec["permissions"] if key not in permissions]
            if missing and "*" not in permissions:
                role.permissions = permissions + missing
                role.save(update_fields=["permissions"])
        roles[spec["name"]] = role
    return roles


def _move(Membership, organization, source_name, target_role) -> int:
    """``source_name`` rolundakı «monitorinq» üzvlüklərini ``target_role``-a keçirir (dublikat yaratmır)."""
    moved = 0
    rows = Membership.objects.filter(
        organization=organization, is_active=True, role__name=source_name, scope_unit__isnull=False
    ).select_related("scope_unit")
    for membership in rows.iterator():
        if not is_monitoring_unit(membership.scope_unit.name, membership.scope_unit.unit_type):
            continue
        duplicate = (
            Membership.objects.filter(
                organization=organization,
                user_id=membership.user_id,
                role=target_role,
                scope_unit_id=membership.scope_unit_id,
            )
            .exclude(pk=membership.pk)
            .exists()
        )
        if duplicate:
            continue
        membership.role = target_role
        membership.save(update_fields=["role"])
        moved += 1
    return moved


def forward(apps, schema_editor):
    _bypass(schema_editor)
    Membership = apps.get_model("organizations", "Membership")
    Organization = apps.get_model("organizations", "Organization")
    Role = apps.get_model("organizations", "Role")
    for organization in Organization.objects.filter(org_type="university").iterator():
        roles = _ensure_roles(Role, organization)
        for source_name, target_name in MEMBERSHIP_MOVES.items():
            _move(Membership, organization, source_name, roles[target_name])


def backward(apps, schema_editor):
    _bypass(schema_editor)
    Membership = apps.get_model("organizations", "Membership")
    Organization = apps.get_model("organizations", "Organization")
    Role = apps.get_model("organizations", "Role")
    for organization in Organization.objects.filter(org_type="university").iterator():
        for source_name, target_name in MEMBERSHIP_MOVES.items():
            previous = Role.objects.filter(organization=organization, name=source_name).first()
            if previous is not None:
                _move(Membership, organization, target_name, previous)


class Migration(migrations.Migration):
    dependencies = [("organizations", "0084_exam_center_staff_score_entry")]
    operations = [migrations.RunPython(forward, backward)]
