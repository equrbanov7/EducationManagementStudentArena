"""Dərs cədvəli idarəetməsi açarı — `schedule.view` / `schedule.manage` seed-i.

SAHİBİN QƏRARI (2026-09): dərs cədvəlinin slotlarını YARATMAQ/SİLMƏK adi
müəllimin işi deyil. Əvvəllər `apps/registrar/schedule_views.py` yalnız
`journal_access.is_direct_editor`-a baxırdı — yəni açılışın müəllimi (və ya org
sahibi/superuser) universitetin cədvəlinə istədiyi saatı və auditoriyanı yaza
bilirdi, proqram koordinatoru / dekanlıq isə HEÇ NƏ edə bilmirdi.

Yeni model nəzarətlidir:

* `schedule.manage` — slot əlavəsi/silinməsi (əhatə UNIT rollarında
  `Membership.scope_unit` alt-ağacı ilə məhdudlaşır);
* `schedule.view`   — cədvələ baxış (kataloq bütövlüyü üçün; şəxsi cədvəl
  onsuz da hər kəsə açıqdır).

Mövcud tenantlarda dörd rola verilir (`default_roles_university.py` ilə eyni):

    program_coordinator  — ixtisas alt-ağacı (cədvəlin ƏSAS sahibi)
    ikt_rehber (RİM)     — org-wide
    dean                 — fakültə alt-ağacı
    chair_head           — kafedra alt-ağacı

`*` daşıyan rollar (rektor/prorektor/sahib) onsuz da əhatə olunur, ona görə
onlara heç nə əlavə edilmir. Digər rola lazım olsa açar permission-editordan
verilir (audit izi ilə).

İdempotentdir. Geri dönüş: hər iki açar bütün rollardan çıxarılır.
"""

from django.db import migrations

_PERMISSIONS = ("schedule.view", "schedule.manage")

#: Açarın verildiyi default rol adları (kod adı — display_name RİM üçün fərqlidir).
_TARGET_ROLES = ("program_coordinator", "ikt_rehber", "dean", "chair_head")


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name__in=_TARGET_ROLES).iterator():
        permissions = list(role.permissions or [])
        if "*" in permissions:
            continue
        changed = False
        for permission in _PERMISSIONS:
            if permission not in permissions:
                permissions.append(permission)
                changed = True
        if changed:
            role.permissions = permissions
            role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.all().iterator():
        permissions = [perm for perm in (role.permissions or []) if perm not in _PERMISSIONS]
        if len(permissions) != len(role.permissions or []):
            role.permissions = permissions
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [("organizations", "0032_seed_alumni_role")]

    operations = [migrations.RunPython(forward, backward)]
