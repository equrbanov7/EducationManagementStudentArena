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

from functools import lru_cache

from django.utils.translation import pgettext_lazy

from core.constants import RoleScopeType

from .journal_direct_edit import PERM_JOURNAL_DIRECT_EDIT

PERM_FAQ_VIDEO_MANAGE = "faq.video.manage"

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
    category_labels["faq"] = pgettext_lazy("organizations.permission.category", "Video təlimatlar")
    faq = categories.setdefault("faq", [])
    if PERM_FAQ_VIDEO_MANAGE not in faq:
        faq.append(PERM_FAQ_VIDEO_MANAGE)
    permission_labels[PERM_FAQ_VIDEO_MANAGE] = pgettext_lazy(_PERM_CTX, "FAQ video dərslərini idarə etmək")


@lru_cache(maxsize=16)
def _faq_editor_roles(org_type):
    from .default_roles import get_default_roles_for_org_type

    return frozenset(
        row["name"] for row in get_default_roles_for_org_type(org_type) if PERM_FAQ_VIDEO_MANAGE in row["permissions"]
    )


def has_faq_video_editor_grant(active_memberships) -> bool:
    """Only active, seeded organization roles designated by the university template can edit."""
    return any(
        membership.role.is_system
        and membership.role.scope_type == RoleScopeType.ORGANIZATION
        and membership.role.name in _faq_editor_roles(membership.organization.org_type)
        and PERM_FAQ_VIDEO_MANAGE in (membership.role.permissions or [])
        for membership in active_memberships
    )


def editable_permission_categories():
    """Template-only grants stay out of the role editor's selectable and delegable keys."""
    from .permissions import PERMISSION_CATEGORIES

    return {
        category: keys
        for category, permissions in PERMISSION_CATEGORIES.items()
        if (keys := [key for key in permissions if key != PERM_FAQ_VIDEO_MANAGE])
    }


__all__ = [
    "PERM_FAQ_VIDEO_MANAGE",
    "has_faq_video_editor_grant",
    "editable_permission_categories",
    "PERM_JOURNAL_DIRECT_EDIT",
    "RIM_STAFF_DAILY_PERMISSIONS",
    "merge_rim_staff_permissions",
]
