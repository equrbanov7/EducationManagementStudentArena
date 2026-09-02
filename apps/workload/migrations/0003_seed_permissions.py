"""Mövcud tenantlarda `workload.*` icazələrinin backfill-i.

``default_roles_university.py`` yalnız YENİ təşkilat yaradılanda işləyir
(``organizations/signals.py``), ona görə köçürülmüş tenantlarda açarlar
rollara data-miqrasiyası ilə əlavə olunur — sillabus fazasının BURAXDIĞI
addım məhz bu idi (bax SCOUT §7 «syllabus perms were never backfilled»).

⚠️ Miqrasiya QƏSDƏN ``apps/workload``-dadır, ``apps/organizations``-da yox:
organizations miqrasiya nömrələri paralel iş axınları tərəfindən tutulub.
Asılılıq ``organizations.0032_seed_alumni_role``-dır (rol cədvəli hazır olsun).

Bölgü (SAHİBİN AXINI): kafedra müdiri yaradır+bölür, müəllim öz yükünü görür,
dekan fakültəni görür+hesabat, RİM/prorektor hər şey. `workload.approve`
HEÇ BİR rola verilmir — dekanlıq təsdiqi (F2) hələ yoxdur.

İdempotentdir; geri dönüş açarları yalnız AÇIQ yazıldığı yerlərdən çıxarır.
"""

from django.db import migrations

_ROLE_PERMISSIONS = {
    "chair_head": ("workload.view", "workload.manage", "workload.distribute", "workload.report"),
    "teacher": ("workload.view",),
    "assistant": ("workload.view",),
    "lab_assistant": ("workload.view",),
    "dean": ("workload.view", "workload.report"),
    "ikt_rehber": ("workload.*",),
    "vice_rector": ("workload.*",),
    "program_coordinator": ("workload.view",),
}

_ALL_KEYS = {
    "workload.view",
    "workload.manage",
    "workload.submit",
    "workload.review",
    "workload.approve",
    "workload.distribute",
    "workload.report",
    "workload.*",
}


def _covered(permissions, key: str) -> bool:
    """Rol açarı ONSUZ DA daşıyırmı (`*`, `workload.*` və ya açarın özü)."""
    if "*" in permissions or key in permissions:
        return True
    return key != "workload.*" and "workload.*" in permissions


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role_name, keys in _ROLE_PERMISSIONS.items():
        for role in Role.objects.filter(name=role_name).iterator():
            permissions = list(role.permissions or [])
            added = False
            for key in keys:
                if _covered(permissions, key):
                    continue
                permissions.append(key)
                added = True
            if added:
                role.permissions = permissions
                role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.all().iterator():
        permissions = list(role.permissions or [])
        remaining = [perm for perm in permissions if perm not in _ALL_KEYS]
        if len(remaining) != len(permissions):
            role.permissions = remaining
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("workload", "0002_rls_workload"),
        ("organizations", "0032_seed_alumni_role"),
    ]

    operations = [migrations.RunPython(forward, backward)]
