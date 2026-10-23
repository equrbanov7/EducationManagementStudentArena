"""«Dərs yükü faylını yükləmək» icazəsi — ``workload.load_import`` (sahib 2026-10-23).

Tədris şöbəsi kafedranın dərs yükü faylını (Excel şablonu və ya Forma 1) yükləyir: sistem tapşırıq sətirlərini,
müəllim bölgüsünü, açılışı (jurnal) və tələbə qeydiyyatını özü qurur (``apps.workload.services.load_upload``).
Tədris şöbəsinin rolunda ``workload.distribute`` QƏSDƏN yoxdur (əl ilə bölgü kafedranındır) — bu açar yalnız
fayl yolunu açır, əhatə ``organizations.scoping`` ilə (ORGANIZATION rolu → bütün kafedralar).

NİYƏ AYRI MODUL? ``permissions.py`` ölçü büdcəsinin (600) sərhədindədir — ``permissions_document_seal.py`` naxışı.
Rol şablonuna verilmə ``default_roles_university.py``-da; mövcud tenantlar — ``workload`` miqrasiyası.
"""

from django.utils.translation import pgettext_lazy

_PERM_CTX = "organizations.permission.label"

PERM_WORKLOAD_LOAD_IMPORT = "workload.load_import"

WORKLOAD_LOAD_GRANT_ROLES = ("ikt_rehber", "teaching_office_head", "teaching_office_staff")

_LABEL = pgettext_lazy(_PERM_CTX, "Dərs yükü faylını yükləmək (bölgü, açılış və tələbə qeydiyyatı avtomatik)")


def merge_workload_load_permissions(categories: dict, category_labels: dict, permission_labels: dict) -> None:
    """``workload`` kateqoriyasına açarı YERİNDƏ əlavə edir (idempotent)."""
    bucket = categories.setdefault("workload", [])
    if PERM_WORKLOAD_LOAD_IMPORT not in bucket:
        bucket.append(PERM_WORKLOAD_LOAD_IMPORT)
    permission_labels[PERM_WORKLOAD_LOAD_IMPORT] = _LABEL


def apply_workload_load_grants(roles):
    """Rol şablonlarına açarı idempotent əlavə edir (``*`` / ``workload.*`` daşıyana toxunmur)."""
    for role in roles:
        if role.get("name") not in WORKLOAD_LOAD_GRANT_ROLES:
            continue
        permissions = role.setdefault("permissions", [])
        if "*" in permissions or "workload.*" in permissions or PERM_WORKLOAD_LOAD_IMPORT in permissions:
            continue
        permissions.append(PERM_WORKLOAD_LOAD_IMPORT)
    return roles


__all__ = [
    "PERM_WORKLOAD_LOAD_IMPORT",
    "WORKLOAD_LOAD_GRANT_ROLES",
    "apply_workload_load_grants",
    "merge_workload_load_permissions",
]
