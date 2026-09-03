"""`plan.*` / `semester.*` / `unit.group_manage` açarlarını mövcud rollara əkir.

Dizayn handoff Mərhələ 2 (ekran 05 «Tədris planı», 06 «Qruplar», 07 «Semestr
açılışı»). YENİ ROL YARATMIR — Mərhələ 1 rolları (``teaching_office_head`` /
``teaching_office_staff``) və mövcud akademik rollar (kafedra müdiri, dekan,
koordinator, RİM, prorektor) yalnız yeni açarları alır.

Xəritə ``default_roles_stage2.STAGE2_ROLE_GRANTS``-dan oxunur, yəni seed axını
(yeni tenant) ilə migrasiya (mövcud tenant) bir-birindən sürüşə bilmir.

⚠️ Xəritə ``default_roles_teaching_office``-dakından AYRIDIR: əks halda 0038-in
geri dönüşü Mərhələ 2 açarlarını da silərdi.

İdempotentdir. Geri dönüş yalnız bu migrasiyanın açarlarını çıxarır (rol
silinmir — rollar bu migrasiyada yaradılmır).
"""

from django.db import migrations

_WILDCARD = "*"


def _grants():
    from apps.organizations.default_roles_stage2 import STAGE2_ROLE_GRANTS

    return dict(STAGE2_ROLE_GRANTS)


def forward(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")
    Role = apps.get_model("organizations", "Role")

    grants = _grants()
    for organization in Organization.objects.filter(org_type="university").iterator():
        for role_name, keys in grants.items():
            role = Role.objects.filter(organization=organization, name=role_name).first()
            if role is None:
                continue
            permissions = list(role.permissions or [])
            if _WILDCARD in permissions:
                continue
            changed = False
            for key in keys:
                prefix_wildcard = f"{key.split('.', 1)[0]}.*"
                if key in permissions or prefix_wildcard in permissions:
                    continue
                permissions.append(key)
                changed = True
            if changed:
                role.permissions = permissions
                role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")

    grants = _grants()
    for role_name, keys in grants.items():
        for role in Role.objects.filter(name=role_name).iterator():
            permissions = list(role.permissions or [])
            remaining = [perm for perm in permissions if perm not in keys]
            if len(remaining) != len(permissions):
                role.permissions = remaining
                role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [("organizations", "0040_semester_lock_fields")]

    operations = [migrations.RunPython(forward, backward)]
