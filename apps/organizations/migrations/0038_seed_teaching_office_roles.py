"""Tədris şöbəsi rollarını və `structure.*` / `catalog.*` açarlarını əkir.

Dizayn handoff Mərhələ 1 (ekran 01–04). İki iş görür:

1. HƏR universitet tipli təşkilatda iki YENİ sistem rolu yaradır —
   ``teaching_office_head`` (85) və ``teaching_office_staff`` (60). Rol artıq
   varsa TOXUNULMUR (admin əl ilə redaktə etmiş ola bilər); yalnız kataloqdan
   çatışmayan açarlar əlavə olunur.
2. MÖVCUD rollara (dekan, kafedra müdiri, koordinator, RİM, prorektor) yeni
   struktur/kataloq açarlarını paylayır — ``default_roles_teaching_office``
   ilə EYNİ xəritədən oxuyur, yəni yeni tenant seed-i ilə köhnə tenant
   migrasiyası bir-birindən sürüşə bilmir.

⚠️ Rol adı ``teaching_office_head`` ``core.roles.ProfileRole``-un
``ADMIN_ALIAS_EXEMPT_ROLE_NAMES`` dəstindədir (level 85 ≥ 80 olduğu üçün
məcburidir) — əks halda rol implicit ``org_admin`` səthini alardı.

İdempotentdir. Geri dönüş yalnız BU migrasiyanın əlavə etdiyi açarları çıxarır
və yaratdığı rolları (üzvü yoxdursa) silir.
"""

from django.db import migrations

_TEACHING_OFFICE_ROLE_NAMES = ("teaching_office_head", "teaching_office_staff")
_WILDCARD = "*"


def _role_specs():
    """(name, display_name, level, scope_type, permissions, description) siyahısı."""
    from apps.organizations.default_roles_teaching_office import TEACHING_OFFICE_ROLES

    return [dict(spec) for spec in TEACHING_OFFICE_ROLES]


def _grants():
    from apps.organizations.default_roles_teaching_office import TEACHING_OFFICE_GRANTS

    return dict(TEACHING_OFFICE_GRANTS)


def forward(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    Role = apps.get_model("organizations", "Role")

    specs = _role_specs()
    grants = _grants()
    granted_keys = {key for keys in grants.values() for key in keys}

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
                continue
            permissions = list(role.permissions or [])
            if _WILDCARD in permissions:
                continue
            changed = False
            for key in spec["permissions"]:
                if key not in permissions:
                    permissions.append(key)
                    changed = True
            if changed:
                role.permissions = permissions
                role.save(update_fields=["permissions"])

        for role_name, keys in grants.items():
            role = Role.objects.filter(organization=organization, name=role_name).first()
            if role is None:
                continue
            permissions = list(role.permissions or [])
            if _WILDCARD in permissions:
                continue
            changed = False
            for key in keys:
                if key not in permissions:
                    permissions.append(key)
                    changed = True
            if changed:
                role.permissions = permissions
                role.save(update_fields=["permissions"])

    # Sağlamlıq: kataloqda olmayan açar əkilməsin (yazı səhvinin erkən tutulması).
    assert all("." in key for key in granted_keys), granted_keys


def backward(apps, schema_editor):
    Membership = apps.get_model("organizations", "Membership")
    Role = apps.get_model("organizations", "Role")

    grants = _grants()
    for role_name, keys in grants.items():
        for role in Role.objects.filter(name=role_name).iterator():
            permissions = list(role.permissions or [])
            remaining = [perm for perm in permissions if perm not in keys]
            if len(remaining) != len(permissions):
                role.permissions = remaining
                role.save(update_fields=["permissions"])

    for role in Role.objects.filter(name__in=_TEACHING_OFFICE_ROLE_NAMES).iterator():
        if Membership.objects.filter(role=role).exists():
            # Üzvü olan rolu SİLMİRİK — üzvlük itərdi.
            continue
        role.delete()


class Migration(migrations.Migration):

    dependencies = [("organizations", "0037_rls_question_submission_event")]

    operations = [migrations.RunPython(forward, backward)]
