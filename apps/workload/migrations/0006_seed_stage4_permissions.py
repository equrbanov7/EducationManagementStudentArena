"""Dərs yükü zəncirinin açarlarının backfill-i (dizayn Mərhələ 4).

``default_roles_university.py`` yalnız YENİ təşkilat yaradılanda işləyir, ona
görə köçürülmüş tenantlarda `workload.submit/review/approve/object` açarları
data-miqrasiyası ilə paylanır. Xəritə ``apps/organizations/default_roles_stage4``-dən
OXUNUR ki, seed ilə migration sürüşə bilməsin.

⚠️ Miqrasiya QƏSDƏN ``apps/workload``-dadır (``0003_seed_permissions`` naxışı) —
``organizations`` nömrələri paralel axınlar tərəfindən tutulub.

Geri dönüş YALNIZ bu mərhələnin dörd açarını çıxarır; FAZA 3-ün
`workload.view/manage/distribute/report` açarlarına TOXUNMUR.
"""

from django.db import migrations

from apps.organizations.default_roles_stage4 import STAGE4_ROLE_GRANTS

#: Geri dönüşdə çıxarılan açarlar — YALNIZ Mərhələ 4-ün özününkülər.
_STAGE4_KEYS = {
    "workload.submit",
    "workload.review",
    "workload.approve",
    "workload.object",
}


def _covered(permissions, key: str) -> bool:
    if "*" in permissions or key in permissions:
        return True
    return "workload.*" in permissions


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role_name, keys in STAGE4_ROLE_GRANTS.items():
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
        remaining = [perm for perm in permissions if perm not in _STAGE4_KEYS]
        if len(remaining) != len(permissions):
            role.permissions = remaining
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("workload", "0005_rls_stage4"),
        ("organizations", "0041_seed_stage2_permissions"),
    ]

    operations = [migrations.RunPython(forward, backward)]
