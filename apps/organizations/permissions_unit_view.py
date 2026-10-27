"""Tyutor və laborant — kafedranın sillabus və dərs materiallarına YALNIZ-OXU baxış (sahib 2026-10-27).

Sahibin sözü: «tyutor və laborantlar müəllimlərin keçilmiş dərs yükünə baxa bilsin, əlavə olaraq özlərinə aid
olan kafedra sillabusa, dərs materialı varsa ona baxmaq olsun».

* «Keçilmiş dərslər» — YENİ açar YOXDUR: laborantda ``journal.lessons_unit`` (2026-09-08), tyutorda
  ``journal.roster`` (koordinatorla ortaq dəst) artıq var; kafedra kökü olan əhatənin boş qalması
  ``registrar.lessons_log.supervision_q``-da düzəldilib.
* Sillabus — mövcud ``syllabus.view`` (yalnız oxu): əhatə ``Syllabus.chair_unit`` alt-ağacıdır
  (``apps.syllabus.services.scoping``); yazı / qərar / plan saatı düzəlişi AYRI açarlardadır.
* Dərs materialı — YENİ ``subject_folder.view_unit``: əhatədəki fənn qovluqlarının DƏRC EDİLMİŞ materiallarına
  baxış və endirmə (``apps.subject_folder.services.unit_view``). Tələbə göndərişlərini AÇMIR, qovluğu idarə
  etmir — ``journal.view`` (jurnal müşahidəsi) QƏSDƏN verilmir.

Tyutor ↔ proqram koordinatoru paritet qrupundadır (``default_roles_role_audit.ROLE_PARITY_GROUPS``) — açarlar
hər ikisinə yazılır ki, dəstlər bərabər qalsın. Mövcud tenantlar: miqrasiya ``organizations/0074``.

NİYƏ AYRI MODUL? ``permissions.py`` ölçü büdcəsinin (600) sərhədindədir — ``permissions_workload_load.py`` naxışı.
"""

from django.utils.translation import pgettext_lazy

_PERM_CTX = "organizations.permission.label"

PERM_SUBJECT_FOLDER_VIEW_UNIT = "subject_folder.view_unit"
PERM_SYLLABUS_VIEW = "syllabus.view"

#: Rol adı → verilən açarlar (QƏSDƏN dondurulub; miqrasiya 0074 eyni dəsti işlədir).
UNIT_VIEW_GRANTS: dict[str, tuple[str, ...]] = {
    "tutor": (PERM_SYLLABUS_VIEW, PERM_SUBJECT_FOLDER_VIEW_UNIT),
    "program_coordinator": (PERM_SYLLABUS_VIEW, PERM_SUBJECT_FOLDER_VIEW_UNIT),
    "lab_assistant": (PERM_SYLLABUS_VIEW, PERM_SUBJECT_FOLDER_VIEW_UNIT),
}
# Qəyyum «hər şeyi GÖRÜR» (sahib 2026-10-17) — yeni oxu açarı ``default_roles_oversight._TRUSTEE_PERMISSIONS``-dadır.

_LABEL = pgettext_lazy(_PERM_CTX, "Kafedranın fənn qovluqlarına (dərs materiallarına) baxmaq")
_CATEGORY = "subject_folder"
#: Kateqoriya etiketləri digər birləşmə modulları kimi düz mətndir (``permissions_announcements`` naxışı).
_CATEGORY_LABEL = "Fənn qovluqları"


def merge_unit_view_permissions(categories: dict, category_labels: dict, permission_labels: dict) -> None:
    """Ayrı ``subject_folder`` kateqoriyasına açarı YERİNDƏ əlavə edir (idempotent)."""
    bucket = categories.setdefault(_CATEGORY, [])
    if PERM_SUBJECT_FOLDER_VIEW_UNIT not in bucket:
        bucket.append(PERM_SUBJECT_FOLDER_VIEW_UNIT)
    category_labels[_CATEGORY] = _CATEGORY_LABEL
    permission_labels[PERM_SUBJECT_FOLDER_VIEW_UNIT] = _LABEL


def _covered(permissions, key) -> bool:
    return key in permissions or f"{key.split('.', 1)[0]}.*" in permissions or "*" in permissions


def apply_unit_view_grants(roles):
    """Rol şablonlarına açarları idempotent əlavə edir (``*`` / prefiks wildcard daşıyana toxunmur)."""
    for role in roles:
        permissions = role.setdefault("permissions", [])
        for key in UNIT_VIEW_GRANTS.get(role.get("name"), ()):
            if not _covered(permissions, key):
                permissions.append(key)
    return roles


__all__ = [
    "PERM_SUBJECT_FOLDER_VIEW_UNIT",
    "PERM_SYLLABUS_VIEW",
    "UNIT_VIEW_GRANTS",
    "apply_unit_view_grants",
    "merge_unit_view_permissions",
]
