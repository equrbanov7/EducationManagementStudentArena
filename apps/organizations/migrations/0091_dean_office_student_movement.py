"""Dekanlıq tələbə hərəkəti + «Dekanlıq laborantı» rolu MÖVCUD universitetlərə — sahib 2026-11-27.

Sahib: «dekanlıqda dondurma, bərpa, xaric və s. edə bilsin». Şablon: ``default_roles_dean_office`` (dəstlər burada
DONDURULUB — test şablonla müqayisə edir).

1. ``dean`` / ``vice_dean``: çatışmayan açarlar əlavə olunur (``*`` / ``<prefiks>.*`` daşıyan rola toxunulmur).
2. ``dean_office_assistant`` («Dekanlıq laborantı», UNIT, səviyyə 58): yoxdursa yaradılır, varsa çatışmayan açar
   əlavə olunur. ÜZVLÜK VERİLMİR — mövcud dekanlıq laborantları ``reassign_dean_office_laborants_20261127`` əmri ilə
   (defolt dry-run) köçürülür.
3. «Dekanlıq» müraciət şöbəsinin (``ApplicationUnit.code = "dekan"``) emalçılarına ``dean_office_assistant``
   (tenant siyahıdan ``dean``-i çıxarıbsa toxunulmur).

Geri dönüş: əlavə olunan açarlar (dekanda yalnız ``student.movement``) və emalçı adı geri götürülür; rol sətri passivləşdirilir (silinmir).
"""

from django.db import migrations

_ROLE = "dean_office_assistant"
_MOVEMENT = ["student.movement", "people.manage_academic", "student.registry_view"]
GRANTS = {
    "dean": list(_MOVEMENT),
    "vice_dean": [*_MOVEMENT, "unit.group_manage"],
}
#: Geri dönüşdə götürülən açarlar — dekanda ``people.manage_academic`` / ``student.registry_view`` əvvəldən var idi.
_BACKWARD_REMOVE = {"dean": ["student.movement"], "vice_dean": GRANTS["vice_dean"]}
_PERMISSIONS = [
    "unit.view",
    "unit.group_manage",
    "member.view",
    "course.view",
    "journal.roster",
    *_MOVEMENT,
    "student.records_view",
    "schedule.view",
    "schedule.manage",
    "application.create",
    "application.handle",
    "people.view_teachers",
    "people.view_students",
    "people.view_contacts",
    "people.view_demographics",
]
ROLE_SPEC = {
    "name": _ROLE,
    "display_name": "Dekanlıq laborantı",
    "level": 58,
    "description": "Dean's office assistant — groups, student movement, registry, schedule, dean's office requests",
}
_UNIT_CODE = "dekan"
_DEAN = "dean"


def _covered(permissions, key):
    return key in permissions or f"{key.split('.', 1)[0]}.*" in permissions or "*" in permissions


def _bypass(schema_editor):
    if schema_editor is not None and schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def _grant(role, keys):
    permissions = list(role.permissions or [])
    missing = [key for key in keys if not _covered(permissions, key)]
    if missing:
        role.permissions = permissions + missing
        role.save(update_fields=["permissions"])


def forward(apps, schema_editor):
    _bypass(schema_editor)
    Organization = apps.get_model("organizations", "Organization")
    Role = apps.get_model("organizations", "Role")
    for organization in Organization.objects.filter(org_type="university").iterator():
        for role in Role.objects.filter(organization=organization, name__in=list(GRANTS)):
            _grant(role, GRANTS[role.name])
        role = Role.objects.filter(organization=organization, name=_ROLE).first()
        if role is None:
            Role.objects.create(
                organization=organization,
                name=_ROLE,
                display_name=ROLE_SPEC["display_name"],
                description=ROLE_SPEC["description"],
                level=ROLE_SPEC["level"],
                scope_type="unit",
                permissions=list(_PERMISSIONS),
                is_system=True,
                is_active=True,
            )
        else:
            _grant(role, _PERMISSIONS)

    ApplicationUnit = apps.get_model("applications", "ApplicationUnit")
    for unit in ApplicationUnit.objects.filter(code=_UNIT_CODE).iterator():
        names = [str(name) for name in (unit.handler_role_names or []) if name]
        if _DEAN in names and _ROLE not in names:
            unit.handler_role_names = [*names, _ROLE]
            unit.save(update_fields=["handler_role_names"])


def backward(apps, schema_editor):
    _bypass(schema_editor)
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name__in=list(_BACKWARD_REMOVE)).iterator():
        permissions = list(role.permissions or [])
        kept = [key for key in permissions if key not in _BACKWARD_REMOVE[role.name]]
        if kept != permissions:
            role.permissions = kept
            role.save(update_fields=["permissions"])
    Role.objects.filter(name=_ROLE, is_active=True).update(is_active=False)

    ApplicationUnit = apps.get_model("applications", "ApplicationUnit")
    for unit in ApplicationUnit.objects.filter(code=_UNIT_CODE).iterator():
        names = [str(name) for name in (unit.handler_role_names or []) if name]
        if _ROLE in names:
            unit.handler_role_names = [name for name in names if name != _ROLE]
            unit.save(update_fields=["handler_role_names"])


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0090_registry_name_guard"),
        ("applications", "0014_attachment_path_255"),
    ]

    operations = [migrations.RunPython(forward, backward)]
