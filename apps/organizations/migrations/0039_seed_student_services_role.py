"""Tələbə Xidmətləri Mərkəzi rolunu və `student.*` açarlarını əkir.

Dizayn handoff Mərhələ 3 (ekran 08–09). Üç iş görür:

1. HƏR universitet tipli təşkilatda YENİ sistem rolu yaradır —
   ``student_services`` (60). Rol artıq varsa TOXUNULMUR; yalnız kataloqdan
   çatışmayan açarlar əlavə olunur.
2. MÖVCUD rollara (RİM, dekan, koordinator, prorektor) `student.*` açarlarını
   paylayır — ``default_roles_student_services.STUDENT_SERVICES_GRANTS``
   xəritəsindən oxuyur, yəni yeni tenant seed-i ilə köhnə tenant migrasiyası
   bir-birindən sürüşə bilmir.
3. Müraciətlər kataloqunun «Tələbə Xidmətləri Mərkəzi» (`telebe`) şöbəsinin
   emalçı rolları siyahısına ``student_services``-i ƏLAVƏ edir. ``hr``
   SİLİNMİR — mövcud tenantlarda əməkdaşlar hələ kadr rolu ilə işləyir və
   növbə bir anda sahibsiz qalmamalıdır (``seed_units`` mövcud sətri
   qəsdən yenidən yazmır, ona görə bu addım burada lazımdır).

İdempotentdir. Geri dönüş yalnız BU migrasiyanın əlavə etdiyini çıxarır və
yaratdığı rolu (üzvü yoxdursa) silir.
"""

from django.db import migrations

_ROLE_NAME = "student_services"
_WILDCARD = "*"
_APPLICATION_UNIT_CODE = "telebe"


def _role_specs():
    from apps.organizations.default_roles_student_services import STUDENT_SERVICES_ROLES

    return [dict(spec) for spec in STUDENT_SERVICES_ROLES]


def _grants():
    from apps.organizations.default_roles_student_services import STUDENT_SERVICES_GRANTS

    return dict(STUDENT_SERVICES_GRANTS)


def _add_keys(role, keys) -> None:
    permissions = list(role.permissions or [])
    if _WILDCARD in permissions:
        return
    changed = False
    for key in keys:
        if key not in permissions:
            permissions.append(key)
            changed = True
    if changed:
        role.permissions = permissions
        role.save(update_fields=["permissions"])


def forward(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    Role = apps.get_model("organizations", "Role")
    ApplicationUnit = apps.get_model("applications", "ApplicationUnit")

    specs = _role_specs()
    grants = _grants()

    for organization in Organization.objects.filter(org_type="university").iterator():
        for spec in specs:
            role = Role.objects.filter(organization=organization, name=spec["name"]).first()
            if role is None:
                Role.objects.create(
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
            else:
                _add_keys(role, spec["permissions"])

        for role_name, keys in grants.items():
            role = Role.objects.filter(organization=organization, name=role_name).first()
            if role is not None:
                _add_keys(role, keys)

        unit = ApplicationUnit.objects.filter(organization=organization, code=_APPLICATION_UNIT_CODE).first()
        if unit is not None:
            names = list(unit.handler_role_names or [])
            if _ROLE_NAME not in names:
                # ƏLAVƏ, əvəzləmə DEYİL — `hr` fallback kimi qalır.
                unit.handler_role_names = [_ROLE_NAME] + names
                unit.save(update_fields=["handler_role_names"])


def backward(apps, schema_editor):
    Membership = apps.get_model("organizations", "Membership")
    Role = apps.get_model("organizations", "Role")
    ApplicationUnit = apps.get_model("applications", "ApplicationUnit")

    grants = _grants()
    for role_name, keys in grants.items():
        for role in Role.objects.filter(name=role_name).iterator():
            permissions = list(role.permissions or [])
            remaining = [perm for perm in permissions if perm not in keys]
            if len(remaining) != len(permissions):
                role.permissions = remaining
                role.save(update_fields=["permissions"])

    for unit in ApplicationUnit.objects.filter(code=_APPLICATION_UNIT_CODE).iterator():
        names = [name for name in (unit.handler_role_names or []) if name != _ROLE_NAME]
        if names != list(unit.handler_role_names or []):
            unit.handler_role_names = names or ["hr"]
            unit.save(update_fields=["handler_role_names"])

    for role in Role.objects.filter(name=_ROLE_NAME).iterator():
        if Membership.objects.filter(role=role).exists():
            # Üzvü olan rolu SİLMİRİK — üzvlük itərdi.
            continue
        role.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0038_seed_teaching_office_roles"),
        ("applications", "0003_seed_permissions_and_catalog"),
    ]

    operations = [migrations.RunPython(forward, backward)]
