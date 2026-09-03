"""Tədris planı + semestr açılışı + akademik qrup icazələri (dizayn Mərhələ 2).

NİYƏ AYRI MODUL? ``permissions.py`` 556/600 sətirdir
(``scripts/check_module_size.py`` SOFT_CAP=600); üç yeni kateqoriya, onların
etiketləri və açar izahları birbaşa oraya yazılsaydı qapı qırmızıya düşərdi.
Burada YALNIZ DATA var — birləşdirmə ``permissions.py``-ın sonunda iki sətirlə
olur, yəni kataloq hələ də TƏK dəstdir (test onu yoxlayır:
``test_permissions.py`` kataloq ↔ etiket tam üst-üstə düşməlidir).

⚠️ PREFİKS QAYDASI: ``structure.*`` LEGACY-dir və CI-da bloklanır
(``DefaultRolesCanonicalPermissionTest.LEGACY_PREFIXES``). Akademik QRUP açarı
ona görə ``unit.group_manage``-dir — qrup ``OrgUnit(unit_type=group)``-dur,
``group.*`` isə BAŞQA anlayışdır (``exams.StudentGroup`` — imtahan kohortu).
"""

from django.utils.translation import pgettext_lazy

_PERM_CTX = "organizations.permission.label"

#: ``PERMISSION_CATEGORIES``-ə əlavə olunan yeni kateqoriyalar.
STAGE2_PERMISSION_CATEGORIES = {
    # Tədris planı (ekran 05) — təsdiq zəncirinin HƏR HALQASI AYRI açardır
    # (`approve_chair` / `approve_council` / `approve_office`), ona görə «baxan»
    # ilə «təsdiqləyən» bir-birindən ayrıla bilir (əsasnamə 5.5 səlahiyyət
    # ayrılığı). `plan.edit` YALNIZ qaralamanı dəyişir: təsdiqlənmiş plan
    # IMMUTABLE-dır (handoff §8 qayda 1) və heç bir açar onu redaktə etmir —
    # dəyişiklik yalnız yeni versiya yaradır.
    "plan": [
        "plan.view",
        "plan.edit",
        "plan.submit",
        "plan.approve_chair",
        "plan.approve_council",
        "plan.approve_office",
    ],
    # Semestr açılışı (ekran 07). `semester.unlock` AYRI açardır: kilid geri
    # qaytarılmır — açmaq üçün ayrıca səlahiyyət + ≥20 simvol səbəb lazımdır.
    "semester": [
        "semester.view",
        "semester.open",
        "semester.lock",
        "semester.unlock",
    ],
}

#: Mövcud kateqoriyalara əlavə olunan açarlar (kateqoriya adı → açarlar).
STAGE2_CATEGORY_ADDITIONS = {
    "structure": ["unit.group_manage"],
}

STAGE2_CATEGORY_LABELS = {
    "plan": "Tədris planı",
    "semester": "Semestr açılışı",
}

STAGE2_PERMISSION_LABELS = {
    "unit.group_manage": pgettext_lazy(_PERM_CTX, "Akademik qrup yaratmaq/idarə etmək"),
    "plan.view": pgettext_lazy(_PERM_CTX, "Tədris planına baxış"),
    "plan.edit": pgettext_lazy(_PERM_CTX, "Tədris planının qaralamasını redaktə etmək"),
    "plan.submit": pgettext_lazy(_PERM_CTX, "Tədris planını təsdiqə göndərmək"),
    "plan.approve_chair": pgettext_lazy(_PERM_CTX, "Tədris planını kafedra adından təsdiqləmək"),
    "plan.approve_council": pgettext_lazy(_PERM_CTX, "Tədris planını fakültə şurası adından təsdiqləmək"),
    "plan.approve_office": pgettext_lazy(_PERM_CTX, "Tədris planını Tədris şöbəsi adından təsdiqləmək"),
    "semester.view": pgettext_lazy(_PERM_CTX, "Semestr açılışına baxış"),
    "semester.open": pgettext_lazy(_PERM_CTX, "Plandan semestr açılışı yaratmaq"),
    "semester.lock": pgettext_lazy(_PERM_CTX, "Semestri kilidləmək"),
    "semester.unlock": pgettext_lazy(_PERM_CTX, "Semestrin kilidini açmaq (səbəblə)"),
}


def merge_stage2(categories: dict, category_labels: dict, permission_labels: dict) -> None:
    """Kataloqu YERİNDƏ genişləndirir (idempotent — təkrar çağırış təsirsizdir)."""
    for name, keys in STAGE2_CATEGORY_ADDITIONS.items():
        bucket = categories.setdefault(name, [])
        for key in keys:
            if key not in bucket:
                bucket.append(key)
    for name, keys in STAGE2_PERMISSION_CATEGORIES.items():
        bucket = categories.setdefault(name, [])
        for key in keys:
            if key not in bucket:
                bucket.append(key)
    category_labels.update(STAGE2_CATEGORY_LABELS)
    permission_labels.update(STAGE2_PERMISSION_LABELS)


__all__ = [
    "STAGE2_CATEGORY_ADDITIONS",
    "STAGE2_CATEGORY_LABELS",
    "STAGE2_PERMISSION_CATEGORIES",
    "STAGE2_PERMISSION_LABELS",
    "merge_stage2",
]
