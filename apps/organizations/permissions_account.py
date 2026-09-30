"""«Parol sıfırlama» icazəsi — `account.password_reset` (sahib tələbi, 2026-09-30).

Sahibin tələbi: parolunu unudan tələbə/müəllim RİM-ə gəlir; RİM rəhbəri (və bu
açar verilən istənilən rol) istifadəçi adını yazıb parolu sıfırlayır, ilkin giriş
parolu verir, istifadəçi isə ilk girişdə öz parolunu qurmağa məcbur olur.

NİYƏ AYRI MODUL? ``permissions_stage3.py`` ilə eyni səbəb: ``permissions.py``
modul ölçüsü büdcəsinə (600) yaxındır. Burada YALNIZ DATA var; birləşdirmə
``permissions.py``-ın sonunda bir sətirlə olur — kataloq TƏK dəst qalır
(``test_permissions.py`` kataloq ↔ etiket uyğunluğunu yoxlayır).

NİYƏ `user.credentials` DEYİL? O açar «RİM mərkəzi»nin geniş hesab səthini açır
(axtarış kartı, səbəb məcburi, köhnə sistemdən gələn hesablar). Bu açar isə TƏK
əməldir — «parolu sıfırla» — və rol redaktorundan ayrıca verilə bilməlidir:
məsələn dekanlığın əməkdaşına RİM mərkəzini açmadan yalnız parol sıfırlama
hüququ vermək olsun. Prefiks QƏSDƏN `user.` DEYİL: `user.*` wildcard-ı daşıyan
rol bu əməli avtomatik almasın (əsasnamə 5.5 — səlahiyyət ayrılığı).

Kateqoriya: mövcud «users» (Hesab idarəetməsi (RİM)) — redaktorda açar
`user.credentials`-ın yanında görünür.
"""

from django.utils.translation import pgettext_lazy

_PERM_CTX = "organizations.permission.label"

#: Açarın özü — kodda həmişə bu sabitdən istifadə edin.
PERM_ACCOUNT_PASSWORD_RESET = "account.password_reset"

#: ``PERMISSION_CATEGORIES``-ə əlavə olunan açarlar (mövcud kateqoriyaya).
ACCOUNT_PERMISSION_CATEGORIES = {
    "users": [PERM_ACCOUNT_PASSWORD_RESET],
}

ACCOUNT_PERMISSION_LABELS = {
    PERM_ACCOUNT_PASSWORD_RESET: pgettext_lazy(
        _PERM_CTX, "Parolu sıfırlamaq (müvəqqəti parol vermək, ilk girişdə dəyişmək məcburi)"
    ),
}


def merge_account_permissions(categories: dict, category_labels: dict, permission_labels: dict) -> None:
    """Kataloqu YERİNDƏ genişləndirir (idempotent — təkrar çağırış təsirsizdir)."""
    for name, keys in ACCOUNT_PERMISSION_CATEGORIES.items():
        bucket = categories.setdefault(name, [])
        for key in keys:
            if key not in bucket:
                bucket.append(key)
    permission_labels.update(ACCOUNT_PERMISSION_LABELS)


__all__ = [
    "ACCOUNT_PERMISSION_CATEGORIES",
    "ACCOUNT_PERMISSION_LABELS",
    "PERM_ACCOUNT_PASSWORD_RESET",
    "merge_account_permissions",
]
