"""«Elanlar» icazəsi — `announcement.manage` (sahib tələbi, 2026-10-06).

Açar elan yaratmaq / redaktə / dərc / arxiv səthini açır. Əhatə struktur scope-una
tabedir (``organizations.scoping.get_permission_scope``): ORGANIZATION rolu (prorektor,
tədris şöbəsi, Tələbə Xidmətləri Mərkəzi) bütün təşkilata, UNIT rolu (dekan, dekan
müavini, kafedra müdiri) yalnız öz ``scope_unit`` alt-ağacına elan ünvanlaya bilər —
server tərəfdə ``apps/announcements/services/access.py`` yoxlayır.

NİYƏ AYRI MODUL? ``permissions_system.py`` ilə eyni səbəb: ``permissions.py`` modul
ölçüsü büdcəsinə yaxındır. Burada YALNIZ DATA var; birləşdirmə ``permissions.py``-ın
sonunda bir sətirlə, rol şablonuna verilmə isə ``default_roles_university.py``-da
``apply_announcement_grants`` ilə olur. Mövcud tenantlar: ``announcements/0003``.
"""

from django.utils.translation import pgettext_lazy

_PERM_CTX = "organizations.permission.label"

PERM_ANNOUNCEMENT_MANAGE = "announcement.manage"

ANNOUNCEMENT_PERMISSION_CATEGORIES = {"announcement": [PERM_ANNOUNCEMENT_MANAGE]}
ANNOUNCEMENT_CATEGORY_LABELS = {"announcement": "Elanlar"}
ANNOUNCEMENT_PERMISSION_LABELS = {
    PERM_ANNOUNCEMENT_MANAGE: pgettext_lazy(_PERM_CTX, "Elan yaratmaq və dərc etmək (öz əhatəsində)"),
}

#: Şablonda açarı alan rollar (rektor / RİM rəhbəri ``*`` ilə onsuz da əhatəlidir).
ANNOUNCEMENT_GRANT_ROLES = (
    "vice_rector",
    "dean",
    "vice_dean",
    "chair_head",
    "teaching_office_head",
    "student_services",
)


def merge_announcement_permissions(categories: dict, category_labels: dict, permission_labels: dict) -> None:
    """Kataloqu YERİNDƏ genişləndirir (idempotent — təkrar çağırış təsirsizdir)."""
    for name, keys in ANNOUNCEMENT_PERMISSION_CATEGORIES.items():
        bucket = categories.setdefault(name, [])
        for key in keys:
            if key not in bucket:
                bucket.append(key)
    category_labels.update(ANNOUNCEMENT_CATEGORY_LABELS)
    permission_labels.update(ANNOUNCEMENT_PERMISSION_LABELS)


def apply_announcement_grants(roles):
    """Rol şablonlarına açarı idempotent əlavə edir (``*`` / ``announcement.*`` daşıyana toxunmur)."""
    for role in roles:
        if role.get("name") not in ANNOUNCEMENT_GRANT_ROLES:
            continue
        permissions = role.setdefault("permissions", [])
        if "*" in permissions or "announcement.*" in permissions or PERM_ANNOUNCEMENT_MANAGE in permissions:
            continue
        permissions.append(PERM_ANNOUNCEMENT_MANAGE)
    return roles


__all__ = [
    "ANNOUNCEMENT_CATEGORY_LABELS",
    "ANNOUNCEMENT_GRANT_ROLES",
    "ANNOUNCEMENT_PERMISSION_CATEGORIES",
    "ANNOUNCEMENT_PERMISSION_LABELS",
    "PERM_ANNOUNCEMENT_MANAGE",
    "apply_announcement_grants",
    "merge_announcement_permissions",
]
