"""«Kadr analitikası» icazəsi — `people.hr_analytics` (sahib tələbi, 2026-10-11).

Sahib: «İnsan resursları oradan tam hər şeyi analiz edə bilməlidir, statistik olaraq hər cür
məlumata çata bilməlidir — ştatlarla, müəllimlərin sayı və s.» Açar kabinetin «Kadr analitikası»
bölməsini açır (müəllim heyətinin sayı, ştat vahidləri, tərkib, dərs yükü, tədris fəaliyyəti,
məlumat keyfiyyəti + Excel ixracı). Əhatə struktur scope-una tabedir
(``organizations.scoping.get_permission_scope``): ORGANIZATION rolu (HR) bütün təşkilatı,
açarı alan UNIT rolu yalnız öz alt-ağacını görür.

NİYƏ `people.` AİLƏSİ? Bölmə kadr kataloqunun (``people.view_teachers``) analitik görünüşüdür —
icazə redaktorunda eyni «Müəllim və tələbə kataloqu» kateqoriyasında görünür. Tam `*` daşıyan
rollar (rektor, RİM rəhbəri) açarı wildcard ilə alır; `hr` rolu şablonda alır, MÖVCUD tenantlar
üçün miqrasiya ``0058_hr_analytics_permission`` əlavə edir.

Burada YALNIZ DATA var; birləşdirmə ``permissions.py``-ın sonunda bir sətirlə olur.
"""

from django.utils.translation import pgettext_lazy

_PERM_CTX = "organizations.permission.label"

PERM_HR_ANALYTICS = "people.hr_analytics"

HR_PERMISSION_CATEGORIES = {"people": [PERM_HR_ANALYTICS]}
HR_PERMISSION_LABELS = {
    PERM_HR_ANALYTICS: pgettext_lazy(_PERM_CTX, "Kadr analitikası (ştat, tərkib, dərs yükü, ixrac)"),
}

#: Şablonda açarı alan rollar (rektor / RİM rəhbəri ``*`` ilə onsuz da əhatəlidir).
HR_GRANT_ROLES = ("hr",)


def merge_hr_permissions(categories: dict, category_labels: dict, permission_labels: dict) -> None:
    """Kataloqu YERİNDƏ genişləndirir (idempotent). Kateqoriya etiketi «people»-dən qalır."""
    for name, keys in HR_PERMISSION_CATEGORIES.items():
        bucket = categories.setdefault(name, [])
        for key in keys:
            if key not in bucket:
                bucket.append(key)
    permission_labels.update(HR_PERMISSION_LABELS)


def apply_hr_grants(roles):
    """Rol şablonlarına açarı idempotent əlavə edir (``*`` / ``people.*`` daşıyana toxunmur)."""
    for role in roles:
        if role.get("name") not in HR_GRANT_ROLES:
            continue
        permissions = role.setdefault("permissions", [])
        if "*" in permissions or "people.*" in permissions or PERM_HR_ANALYTICS in permissions:
            continue
        permissions.append(PERM_HR_ANALYTICS)
    return roles


__all__ = [
    "HR_GRANT_ROLES",
    "HR_PERMISSION_CATEGORIES",
    "HR_PERMISSION_LABELS",
    "PERM_HR_ANALYTICS",
    "apply_hr_grants",
    "merge_hr_permissions",
]
