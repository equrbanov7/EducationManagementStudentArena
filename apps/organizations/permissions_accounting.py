"""«Mühasibatlıq» + 25% təkrar imtahan açarları (sahib 2026-10-18).

Sahib: «Mühasibatlıq üçün hissə olsun burda, müəllimləri keçdiyi dərslərdən aylıq dərs yüklərinə qədər
burdan görə bilsin.» Qərar (tövsiyə olunan variant): yeni «Mühasib» (``accountant``) rolu, RİM təyin edir;
bölməni rektor, Qəyyumlar Şurasının sədri, RİM rəhbəri (``*``) və qəyyumlar da görür.

* ``accounting.view`` — kabinetin «Mühasibatlıq» bölməsi (müəllim × ay: keçirilmiş saat, plan, fərq,
  Excel ixracı). YALNIZ OXU; əhatə ``get_permission_scope`` ilə (ORGANIZATION rolu → bütün təşkilat).
* ``retake.payment_verify`` — 25% təkrar imtahanın ödəniş qəbzini yoxlamaq (mühasib; registrar-dakı
  təkrar imtahan axını bu açarı ADI ilə yoxlayır).
* ``retake.manage`` — dekanlıq / tədris şöbəsi tələbəni 25% təkrar imtahana buraxır və alt qrup
  yerləşdirməsinə qərar verir (registrar axını + «Alt qrupa tələbə əlavə et» aləti).

NİYƏ AYRI MODUL? ``permissions.py`` modul ölçüsü büdcəsinə (600) yaxındır — ``permissions_hr.py`` ilə eyni
naxış: burada YALNIZ data, birləşmə ``permissions.py``-ın sonunda bir sətirlə. Rol şablonu və verilişlər:
``default_roles_accounting.py``; mövcud tenantlar: miqrasiya ``0067_accounting_retake_permissions``.
"""

from django.utils.translation import pgettext_lazy

_PERM_CTX = "organizations.permission.label"

PERM_ACCOUNTING_VIEW = "accounting.view"
PERM_RETAKE_PAYMENT_VERIFY = "retake.payment_verify"
PERM_RETAKE_MANAGE = "retake.manage"
#: 2026-10-19: 25% ödənişinin «Təhsil haqqı cədvəli» (illik təhsil haqqı → təxmini məbləğ) — mühasib + RİM.
PERM_ACCOUNTING_MANAGE_FEES = "accounting.manage_fees"

ACCOUNTING_PERMISSION_CATEGORIES = {
    "accounting": [PERM_ACCOUNTING_VIEW, PERM_ACCOUNTING_MANAGE_FEES],
    "retake": [PERM_RETAKE_PAYMENT_VERIFY, PERM_RETAKE_MANAGE],
}

ACCOUNTING_CATEGORY_LABELS = {
    "accounting": "Mühasibatlıq",
    "retake": "Təkrar imtahan (25%)",
}

ACCOUNTING_PERMISSION_LABELS = {
    PERM_ACCOUNTING_VIEW: pgettext_lazy(
        _PERM_CTX, "Mühasibatlıq bölməsi (müəllimlərin aylıq keçirilmiş dərs saatı, plan, ixrac)"
    ),
    PERM_ACCOUNTING_MANAGE_FEES: pgettext_lazy(
        _PERM_CTX, "Təhsil haqqı cədvəlini idarə etmək (25% təkrar imtahanın təxmini məbləği)"
    ),
    PERM_RETAKE_PAYMENT_VERIFY: pgettext_lazy(_PERM_CTX, "25% təkrar imtahan ödəniş qəbzini yoxlamaq"),
    PERM_RETAKE_MANAGE: pgettext_lazy(
        _PERM_CTX, "Tələbəni 25% təkrar imtahana buraxmaq və alt qrup yerləşdirməsinə qərar vermək"
    ),
}


def merge_accounting_permissions(categories: dict, category_labels: dict, permission_labels: dict) -> None:
    """Kataloqu YERİNDƏ genişləndirir (idempotent — təkrar çağırış təsirsizdir)."""
    for name, keys in ACCOUNTING_PERMISSION_CATEGORIES.items():
        bucket = categories.setdefault(name, [])
        for key in keys:
            if key not in bucket:
                bucket.append(key)
    category_labels.update(ACCOUNTING_CATEGORY_LABELS)
    permission_labels.update(ACCOUNTING_PERMISSION_LABELS)


__all__ = [
    "ACCOUNTING_CATEGORY_LABELS",
    "ACCOUNTING_PERMISSION_CATEGORIES",
    "ACCOUNTING_PERMISSION_LABELS",
    "PERM_ACCOUNTING_MANAGE_FEES",
    "PERM_ACCOUNTING_VIEW",
    "PERM_RETAKE_MANAGE",
    "PERM_RETAKE_PAYMENT_VERIFY",
    "merge_accounting_permissions",
]
