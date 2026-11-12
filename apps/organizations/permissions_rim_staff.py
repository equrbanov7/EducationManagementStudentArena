"""RİM əməkdaşının (``rim_staff``) GÜNDƏLİK iş açarları — sahib 2026-11-12.

Sahib: «yük bölgüsü, fənn təhvili, qruplar, RİM mərkəzi hissəsi sidebardakı, orada parol sıfırlanması. Gündəlik
olaraq ən çox lazım olan nə varsa hamısına access-i olsun. Gün əlavə etmək, çıxarmaq, silmək və s., alt qrup əlavə
etmək». 2026-09-06 şablonu RİM əməkdaşını «yalnız oxu» kimi qurmuşdu — bu açarlar əvvəl yalnız RİM rəhbərində
(``ikt_rehber`` → ``*``) idi, ona görə əməkdaş bu bölmələri ümumiyyətlə görmürdü.

Yeni açar — ``journal.direct_edit``: başqa müəllimin jurnalında BİRBAŞA redaktə (dərs günü əlavə et / dəyiş / sil,
bal yaz; «Data bərpası» rejimi açıqdırsa səbəblə keçmiş tarix). Qapı ``registrar.journal_access``-dadır və YALNIZ
DƏQİQ açara baxır (``*`` / ``journal.*`` saymır) — rektor/sədrin ``*`` şablonu jurnala birbaşa redaktor kimi
düşməsin (davranış dəyişməsin). RİM rəhbəri onsuz da ``is_ikt_rehber`` ilə birbaşa redaktordur.

QƏSDƏN VERİLMƏYƏNLƏR (rəhbərdə qalır): ``role.*`` (rol/icazə verilməsi), ``user.soft_delete``, ``user.import*``,
``journal.correct`` / ``journal.close``, «Sistem tənzimləmələri» / «Jurnal təmizliyi» / «Jurnaldan çıxarılmalar»
(rol adı qapısı, RİM rəhbəri + superadmin), ``system.monitoring.view``, ``semester.open/lock``, ``catalog.manage``.

Şablon ``default_roles_rim.py``-dadır; mövcud tenantlar — miqrasiya ``organizations/0082``.
"""

from django.utils.translation import pgettext_lazy

from .journal_direct_edit import PERM_JOURNAL_DIRECT_EDIT

_PERM_CTX = "organizations.permission.label"

_LABEL = pgettext_lazy(_PERM_CTX, "Başqa müəllimin jurnalında birbaşa redaktə (dərs günü əlavə et / dəyiş / sil)")

#: RİM əməkdaşına 2026-11-12-də verilən açarlar (miqrasiya 0082 eyni siyahını köçürür).
RIM_STAFF_DAILY_PERMISSIONS = (
    # «RİM mərkəzi» (axtarış, parol təyini, redaktə, blok) + «Parol sıfırlama».
    "user.search",
    "user.credentials",
    "user.edit",
    "user.block",
    "account.password_reset",
    # «Yük bölgüsü» + «Yük mərkəzi» + dərs yükü faylı.
    "workload.distribute",
    "workload.manage",
    "workload.load_import",
    # «Fənn təhvili».
    "journal.reassign",
    # Jurnal: oxu, siyahı (azad et / əlavə et), «Keçilmiş dərslər», birbaşa redaktə.
    "journal.view",
    "journal.roster",
    PERM_JOURNAL_DIRECT_EDIT,
    # «Qruplar» (qrup / alt qrup yarat, köçürmə), «Tələbə reyestri», tələbə hərəkəti.
    "unit.group_manage",
    "student.registry_view",
    "student.movement",
    "student.assign_group",
    # «Alt qrupa tələbə əlavə et» + «Alt qrup tələbələri».
    "retake.manage",
    # «Cədvəl idarəetməsi» (redaktor).
    "schedule.manage",
)


def merge_rim_staff_permissions(categories: dict, category_labels: dict, permission_labels: dict) -> None:
    """``journal`` kateqoriyasına ``journal.direct_edit`` açarını YERİNDƏ əlavə edir (idempotent)."""
    bucket = categories.setdefault("journal", [])
    if PERM_JOURNAL_DIRECT_EDIT not in bucket:
        bucket.append(PERM_JOURNAL_DIRECT_EDIT)
    permission_labels[PERM_JOURNAL_DIRECT_EDIT] = _LABEL


__all__ = [
    "PERM_JOURNAL_DIRECT_EDIT",
    "RIM_STAFF_DAILY_PERMISSIONS",
    "merge_rim_staff_permissions",
]
