"""«İmtahan Mərkəzi» rolunu «İmtahan Mərkəzi rəhbəri»nə birləşdirir (sahib qərarı).

2026-09-06: rol kataloqunda iki sətir vardı — `exam_center` və
`exam_center_head`. Praktikada bu EYNİ adamdır; səlahiyyətlər də onsuz da eyni
idi (`accounts/roles.py::is_exam_center_head` hər ikisini qəbul edirdi, yeganə
fərq `people.view_contacts` idi). İki sətir yalnız çaşqınlıq yaradırdı: rol
təyinat siyahısında iki oxşar variant görünürdü.

NƏ EDİR (hər universitet tipli təşkilat üçün, İDEMPOTENT):

1. `exam_center_head` rolu yoxdursa şablondan yaradılır (yoxsa köçürəcək yer olmaz);
2. `exam_center` üzvlükləri rəhbər roluna keçirilir — həmin istifadəçinin artıq
   rəhbər üzvlüyü varsa DUBLİKAT yaradılmır, köhnə sətir silinir;
3. boş qalan `exam_center` rolu deaktiv edilir (SİLİNMİR: audit sətirləri və
   köhnə hesabatlar ona istinad edə bilər).

Geri dönüş rolu yenidən aktivləşdirir; üzvlüklər RƏHBƏRDƏ qalır (kimin əvvəl
hansı sətirdə olduğunu bilmək mümkün deyil və funksional fərq yoxdur).
"""

from django.db import migrations

_OLD = "exam_center"
_NEW = "exam_center_head"


def _head_spec():
    from apps.organizations.default_roles_university import UNIVERSITY_ROLES

    return next(dict(spec) for spec in UNIVERSITY_ROLES if spec["name"] == _NEW)


def forward(apps, schema_editor):
    Membership = apps.get_model("organizations", "Membership")
    Organization = apps.get_model("organizations", "Organization")
    Role = apps.get_model("organizations", "Role")
    spec = _head_spec()

    for organization in Organization.objects.filter(org_type="university").iterator():
        old_role = Role.objects.filter(organization=organization, name=_OLD).first()
        if old_role is None:
            continue
        head = Role.objects.filter(organization=organization, name=_NEW).first()
        if head is None:
            head = Role.objects.create(
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
        for membership in Membership.objects.filter(organization=organization, role=old_role).iterator():
            duplicate = (
                Membership.objects.filter(organization=organization, user_id=membership.user_id, role=head)
                .exclude(pk=membership.pk)
                .exists()
            )
            if duplicate:
                membership.delete()
                continue
            membership.role = head
            membership.save(update_fields=["role"])
        if old_role.is_active:
            old_role.is_active = False
            old_role.save(update_fields=["is_active"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    Role.objects.filter(name=_OLD, is_active=False).update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [("organizations", "0045_seed_oversight_roles")]

    operations = [migrations.RunPython(forward, backward)]
