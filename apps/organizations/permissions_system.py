"""«Sistem monitorinqi» icazəsi — `system.monitoring.view` (sahib tələbi, 2026-10-01).

Sahibin tələbi: «RİM rəhbərinə superadmindəki serveri izləmək özəlliyini ver —
serverdə nə baş verib, nələr olub, hər şeyi görsün». Əvvəl bölmə və onun bütün
API-ları YALNIZ platforma superadmininə açıq idi (``is_superadmin_user``).

NİYƏ AYRI MODUL? ``permissions_account.py`` ilə eyni səbəb: ``permissions.py``
modul ölçüsü büdcəsinə (600) yaxındır. Burada YALNIZ DATA var; birləşdirmə
``permissions.py``-ın sonunda bir sətirlə olur — kataloq TƏK dəst qalır.

NİYƏ YENİ PREFİKS (`system.`)? Açar platforma/infrastruktur səthini açır
(server, konteynerlər, baza, loglar, təhlükəsizlik hadisələri) — heç bir
mövcud ailəyə (`audit.*`, `analytics.*`, `user.*`) aid deyil və həmin
wildcard-ları daşıyan rollar bu səthi avtomatik ALMAMALIDIR. Açar YALNIZ
OXUDUR: insident əməlləri (qəbul et / həll et / susdur) superadmin-only qalır.

Tam `*` daşıyan rollar (şablonda `rector`, `ikt_rehber`) açarı wildcard ilə
alır; miqrasiya 0056 isə `ikt_rehber` rolu tenantda daraldılıbsa açarı ayrıca
əlavə edir.
"""

from django.utils.translation import pgettext_lazy

_PERM_CTX = "organizations.permission.label"

#: Açarın özü — kodda həmişə bu sabitdən (və ya eyni literal-dan) istifadə edin.
PERM_SYSTEM_MONITORING_VIEW = "system.monitoring.view"

SYSTEM_PERMISSION_CATEGORIES = {
    "system": [PERM_SYSTEM_MONITORING_VIEW],
}

SYSTEM_CATEGORY_LABELS = {
    "system": "Sistem monitorinqi",
}

SYSTEM_PERMISSION_LABELS = {
    PERM_SYSTEM_MONITORING_VIEW: pgettext_lazy(
        _PERM_CTX, "Sistem monitorinqinə baxış (server, xidmətlər, xətalar, təhlükəsizlik hadisələri)"
    ),
}


def merge_system_permissions(categories: dict, category_labels: dict, permission_labels: dict) -> None:
    """Kataloqu YERİNDƏ genişləndirir (idempotent — təkrar çağırış təsirsizdir)."""
    for name, keys in SYSTEM_PERMISSION_CATEGORIES.items():
        bucket = categories.setdefault(name, [])
        for key in keys:
            if key not in bucket:
                bucket.append(key)
    category_labels.update(SYSTEM_CATEGORY_LABELS)
    permission_labels.update(SYSTEM_PERMISSION_LABELS)


__all__ = [
    "PERM_SYSTEM_MONITORING_VIEW",
    "SYSTEM_CATEGORY_LABELS",
    "SYSTEM_PERMISSION_CATEGORIES",
    "SYSTEM_PERMISSION_LABELS",
    "merge_system_permissions",
]
