"""`hr.contracts_view` / `hr.contracts_manage` — «Əmək müqavilələri» açarları (sahib 2026-10-19).

Şablon: ``permissions_hr_contracts.HR_CONTRACT_GRANTS``. Dəyərlər burada SƏTİR-SƏTİR köçürülüb (miqrasiya şablonu
import etmir — sonrakı şablon dəyişikliyi tarixi addımı dəyişməsin). Açar, onun ``hr.*`` wildcard-ı və ya ``*``
artıq varsa toxunulmur. İDEMPOTENT. Geri dönüş yalnız bu miqrasiyanın əlavə etdiyi açarları götürür.
"""

from django.db import migrations

_GRANTS = {
    "hr": ("hr.contracts_view", "hr.contracts_manage"),
    "ikt_rehber": ("hr.contracts_view", "hr.contracts_manage"),
    "trustee": ("hr.contracts_view",),
}


def _covered(permissions, key):
    return key in permissions or f"{key.split('.', 1)[0]}.*" in permissions or "*" in permissions


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name__in=list(_GRANTS)).iterator():
        permissions = list(role.permissions or [])
        added = [key for key in _GRANTS[role.name] if not _covered(permissions, key)]
        if added:
            role.permissions = permissions + added
            role.save(update_fields=["permissions"])


# ⚠️ Geri dönüş açarı «bu miqrasiya əlavə edibmi» yoxlamadan götürür: 0069-dan ƏVVƏL rol redaktorundan əl ilə verilmiş
# eyni açar da silinər (açarlar 2026-10-19-da yaranıb — ondan əvvəl verilə bilməzdi; şüurlu qəbul edilmiş sadələşdirmə).
def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name__in=list(_GRANTS)).iterator():
        granted = set(_GRANTS[role.name])
        permissions = [entry for entry in (role.permissions or []) if entry not in granted]
        if permissions != list(role.permissions or []):
            role.permissions = permissions
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [("organizations", "0068_accounting_manage_fees")]

    operations = [migrations.RunPython(forward, backward)]
