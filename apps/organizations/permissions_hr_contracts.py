"""«Əmək müqavilələri» açarları — ``hr.contracts_view`` / ``hr.contracts_manage`` (sahib 2026-10-19).

Sahib: «Kadrlar üçün yer et, müəllimlərin əmək müqaviləsinə uyğun yer olsun — təkcə müəllimdə yox, hər kəs
işləyən. Müqavilə bitərkən HR və həmin şəxsə bildiriş getsin.» Bölmə ``apps.hr_contracts``-dadır.

* ``hr.contracts_view`` — kabinetin «Əmək müqavilələri» bölməsi (siyahı, fayl, tarixçə, Excel). OXU.
* ``hr.contracts_manage`` — əlavə, redaktə, yeniləmə, «müqavilə göndərildi», xitam; bitmə xatırlatmalarını alır.

Əhatə ``get_permission_scope`` ilə: ORGANIZATION rolu (HR) bütün təşkilatı, açarı alan UNIT rolu yalnız öz
alt-ağacını görür. Rol şablonları (bu modulun ``apply_hr_contract_grants``-ı): ``hr`` + ``ikt_rehber`` — hər iki
açar; ``trustee`` — yalnız oxu (qəyyumların «hamısını görür, heç nəyi dəyişmir» qaydası, 0066). Rektor, Qəyyumlar
Şurasının sədri, RİM rəhbəri ``*`` ilə əhatəlidir. Dekan QƏSDƏN almır (sahibin qərarı gözlənilir — açarı rol
redaktorundan vermək kifayətdir, əhatə onda avtomatik fakültə alt-ağacına daralır).
Mövcud tenantlar: miqrasiya ``0069_hr_contract_permissions`` (dəyərlər orada sətir-sətir köçürülüb).

NİYƏ AYRI MODUL? ``permissions.py`` modul ölçüsü büdcəsinə (600) yaxındır — ``permissions_accounting.py`` naxışı.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

_PERM_CTX = "organizations.permission.label"

PERM_HR_CONTRACTS_VIEW = "hr.contracts_view"
PERM_HR_CONTRACTS_MANAGE = "hr.contracts_manage"

HR_CONTRACT_PERMISSION_CATEGORIES = {"hr": [PERM_HR_CONTRACTS_VIEW, PERM_HR_CONTRACTS_MANAGE]}
HR_CONTRACT_CATEGORY_LABELS = {"hr": "Kadrlar"}
HR_CONTRACT_PERMISSION_LABELS = {
    PERM_HR_CONTRACTS_VIEW: pgettext_lazy(_PERM_CTX, "Əmək müqavilələrinə baxmaq (siyahı, fayl, tarixçə, ixrac)"),
    PERM_HR_CONTRACTS_MANAGE: pgettext_lazy(
        _PERM_CTX, "Əmək müqavilələrini idarə etmək (əlavə, yeniləmə, göndərmə, xitam; bitmə xatırlatmaları)"
    ),
}

#: Rol şablonlarına verilən açarlar (``*`` daşıyanlar onsuz da əhatəlidir).
HR_CONTRACT_GRANTS: dict[str, tuple[str, ...]] = {
    "hr": (PERM_HR_CONTRACTS_VIEW, PERM_HR_CONTRACTS_MANAGE),
    "ikt_rehber": (PERM_HR_CONTRACTS_VIEW, PERM_HR_CONTRACTS_MANAGE),
    "trustee": (PERM_HR_CONTRACTS_VIEW,),
}


def merge_hr_contract_permissions(categories: dict, category_labels: dict, permission_labels: dict) -> None:
    """Kataloqu YERİNDƏ genişləndirir (idempotent)."""
    for name, keys in HR_CONTRACT_PERMISSION_CATEGORIES.items():
        bucket = categories.setdefault(name, [])
        for key in keys:
            if key not in bucket:
                bucket.append(key)
    for name, label in HR_CONTRACT_CATEGORY_LABELS.items():
        category_labels.setdefault(name, label)
    permission_labels.update(HR_CONTRACT_PERMISSION_LABELS)


def _covered(permissions, key) -> bool:
    return key in permissions or f"{key.split('.', 1)[0]}.*" in permissions or "*" in permissions


def apply_hr_contract_grants(roles):
    """``HR_CONTRACT_GRANTS``-ı rol şablonlarına idempotent tətbiq edir (yerində)."""
    for role in roles:
        permissions = role.setdefault("permissions", [])
        for key in HR_CONTRACT_GRANTS.get(role.get("name"), ()):
            if not _covered(permissions, key):
                permissions.append(key)
    return roles


__all__ = [
    "HR_CONTRACT_CATEGORY_LABELS",
    "HR_CONTRACT_GRANTS",
    "HR_CONTRACT_PERMISSION_CATEGORIES",
    "HR_CONTRACT_PERMISSION_LABELS",
    "PERM_HR_CONTRACTS_MANAGE",
    "PERM_HR_CONTRACTS_VIEW",
    "apply_hr_contract_grants",
    "merge_hr_contract_permissions",
]
