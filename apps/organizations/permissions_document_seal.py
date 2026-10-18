"""«Sənəd yoxlaması» icazəsi — ``document_seal.manage`` (sahib 2026-10-18).

Açar kabinetdən kənar «Sənəd yoxlaması» səhifəsini (``/sened-yoxlamasi/``) açır: sistemin verdiyi
möhürlənmiş sənədlərin (QR + kod) siyahısı, kod / tələbə üzrə axtarış və **«Ləğv et»** (səbəb məcburi,
audit-ə yazılır). Publik yoxlama səhifəsi (``/yoxla/``) açarsız, girişsiz işləyir — bu açar ona aid deyil.

Əhatə ``organizations.scoping.get_permission_scope`` ilə: ORGANIZATION rolu → bütün təşkilat; açar UNIT
roluna verilsə → yalnız öz alt-ağacındakı tələbələrin sənədləri (``DocumentSeal.scope_path``).

NİYƏ AYRI MODUL? ``permissions.py`` ölçü büdcəsinə (600) yaxındır — ``permissions_accounting.py`` ilə eyni
naxış. Rol şablonuna verilmə ``default_roles_university.py``-da; mövcud tenantlar —
``verification/0002_seed_document_seal_permission`` (``announcements/0003`` naxışı).
"""

from django.utils.translation import pgettext_lazy

_PERM_CTX = "organizations.permission.label"

PERM_DOCUMENT_SEAL_MANAGE = "document_seal.manage"

DOCUMENT_SEAL_PERMISSION_CATEGORIES = {"document_seal": [PERM_DOCUMENT_SEAL_MANAGE]}
DOCUMENT_SEAL_CATEGORY_LABELS = {"document_seal": "Sənəd yoxlaması"}
DOCUMENT_SEAL_PERMISSION_LABELS = {
    PERM_DOCUMENT_SEAL_MANAGE: pgettext_lazy(
        _PERM_CTX, "Verilmiş rəsmi sənədlərin siyahısı və sənədi ləğv etmək (QR yoxlaması)"
    ),
}

#: Şablonda açarı alan rollar: RİM rəhbəri (``*`` daraldılıbsa da qalsın), Tədris şöbəsi (transkript
#: verən səth), Tələbə xidmətləri (transkript / arayış sorğularını icra edən bölmə).
DOCUMENT_SEAL_GRANT_ROLES = ("ikt_rehber", "teaching_office_head", "teaching_office_staff", "student_services")


def merge_document_seal_permissions(categories: dict, category_labels: dict, permission_labels: dict) -> None:
    """Kataloqu YERİNDƏ genişləndirir (idempotent — təkrar çağırış təsirsizdir)."""
    for name, keys in DOCUMENT_SEAL_PERMISSION_CATEGORIES.items():
        bucket = categories.setdefault(name, [])
        for key in keys:
            if key not in bucket:
                bucket.append(key)
    category_labels.update(DOCUMENT_SEAL_CATEGORY_LABELS)
    permission_labels.update(DOCUMENT_SEAL_PERMISSION_LABELS)


def apply_document_seal_grants(roles):
    """Rol şablonlarına açarı idempotent əlavə edir (``*`` / ``document_seal.*`` daşıyana toxunmur)."""
    for role in roles:
        if role.get("name") not in DOCUMENT_SEAL_GRANT_ROLES:
            continue
        permissions = role.setdefault("permissions", [])
        if "*" in permissions or "document_seal.*" in permissions or PERM_DOCUMENT_SEAL_MANAGE in permissions:
            continue
        permissions.append(PERM_DOCUMENT_SEAL_MANAGE)
    return roles


__all__ = [
    "DOCUMENT_SEAL_CATEGORY_LABELS",
    "DOCUMENT_SEAL_GRANT_ROLES",
    "DOCUMENT_SEAL_PERMISSION_CATEGORIES",
    "DOCUMENT_SEAL_PERMISSION_LABELS",
    "PERM_DOCUMENT_SEAL_MANAGE",
    "apply_document_seal_grants",
    "merge_document_seal_permissions",
]
