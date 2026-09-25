"""Keyfiyyətə nəzarət şöbəsi rolları + anonim sorğu icazələri (2026-09-25 sahib tələbi).

Sahib: «anonim sorğunun nəticələrini kafedra müdiri, tədris şöbəsi və keyfiyyətə
nəzarət rolu (yoxdursa yarat) və onun rəhbəri görsün; onlardan yuxarıda rektor,
prorektor və RİM rəhbəri də görsün».

──────────────────────────────────────────────────────────────────────────────
Rollar
──────────────────────────────────────────────────────────────────────────────
* ``quality_control_head`` — «Keyfiyyətə nəzarət şöbəsinin rəhbəri» (səviyyə 70):
  nəticələr (bütün təşkilat) + kampaniyaların idarəsi (``survey.manage``).
* ``quality_control_staff`` — «Keyfiyyətə nəzarət əməkdaşı» (səviyyə 60): eyni
  oxu səthi, idarə açarı YOXDUR.

⚠️ SƏVİYYƏLƏR 80-dən AŞAĞIDIR QƏSDƏN: ``core.roles.ProfileRole`` ``level >= 80``
olan rola implicit ``org_admin`` aliası verir və ``is_admin_level`` (≥80) qapıları
açılır — keyfiyyət şöbəsinə nə tenant idarəetməsi, nə inzibati səviyyə lazımdır.
ORGANIZATION əhatəlidirlər: ``get_permission_scope`` onlara ORG-WIDE nəticə verir.

──────────────────────────────────────────────────────────────────────────────
İcazə açarları (kataloq: ``SURVEY_PERMISSION_CATEGORIES``)
──────────────────────────────────────────────────────────────────────────────
* ``survey.results.view`` — nəticələrə baxış; əhatə struktur scope-una tabedir:
  kafedra müdiri (UNIT) → öz kafedrası; tədris şöbəsi / keyfiyyət / prorektor
  (ORGANIZATION) → bütün təşkilat; rektor və RİM rəhbəri ``*`` ilə əhatəlidir.
  Dekan sahibin siyahısında YOXDUR — lazım olsa icazə redaktorundan verilir
  (əhatə avtomatik fakültəsi ilə məhdudlaşır).
* ``survey.manage`` — kampaniya idarəsi (keyfiyyət rəhbəri; RİM rəhbəri ``*``).

Kataloq qeydiyyatı: ``permissions.py`` stage2/stage3 dəstlərini öz sonunda bir
sətirlə birləşdirir. Bu modul ``default_roles_university`` vasitəsilə
``OrganizationsConfig.ready()`` → ``signals`` → ``default_roles`` zəncirində
HƏR prosesdə import olunur və birləşməni ÖZÜ, idempotent edir (aşağıda
``_register_catalog``). ``permissions.py``-a açıq çağırış əlavə olunsa da zərər
yoxdur — təkrar birləşmə təsirsizdir.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

from core.constants import RoleScopeType

_PERM_CTX = "organizations.permission.label"

PERM_SURVEY_RESULTS = "survey.results.view"
PERM_SURVEY_MANAGE = "survey.manage"

#: ``PERMISSION_CATEGORIES``-ə əlavə olunan kateqoriya.
SURVEY_PERMISSION_CATEGORIES = {
    "survey": [PERM_SURVEY_RESULTS, PERM_SURVEY_MANAGE],
}
SURVEY_CATEGORY_LABELS = {"survey": "Anonim sorğu (müəllim qiymətləndirməsi)"}
SURVEY_PERMISSION_LABELS = {
    PERM_SURVEY_RESULTS: pgettext_lazy(_PERM_CTX, "Anonim sorğu nəticələrinə baxış"),
    PERM_SURVEY_MANAGE: pgettext_lazy(_PERM_CTX, "Sorğu kampaniyalarını idarə etmək"),
}

#: Keyfiyyət şöbəsinin ORTAQ oxu səthi (struktur/kataloq adları filtrlərdə lazımdır).
_QUALITY_SHARED = [
    "org.view",
    "unit.view",
    "member.view",
    "catalog.view",
    "course.view",
    "analytics.view_all",
    PERM_SURVEY_RESULTS,
]

QUALITY_CONTROL_ROLES = [
    {
        "name": "quality_control_head",
        "display_name": "Keyfiyyətə nəzarət şöbəsinin rəhbəri",
        "level": 70,
        "scope_type": RoleScopeType.ORGANIZATION,
        "permissions": [*_QUALITY_SHARED, PERM_SURVEY_MANAGE],
        "description": "Quality assurance head — anonymous teaching-evaluation results and survey campaigns",
    },
    {
        "name": "quality_control_staff",
        "display_name": "Keyfiyyətə nəzarət əməkdaşı",
        "level": 60,
        "scope_type": RoleScopeType.ORGANIZATION,
        "permissions": list(_QUALITY_SHARED),
        "description": "Quality assurance staff — anonymous teaching-evaluation results (read-only)",
    },
]

#: Mövcud rollara verilən sorğu açarları (rektor/RİM rəhbəri ``*`` ilə əhatəlidir).
SURVEY_GRANTS: dict[str, tuple[str, ...]] = {
    "chair_head": (PERM_SURVEY_RESULTS,),
    "teaching_office_head": (PERM_SURVEY_RESULTS,),
    "teaching_office_staff": (PERM_SURVEY_RESULTS,),
    "vice_rector": (PERM_SURVEY_RESULTS,),
}


def apply_quality_control_grants(roles):
    """``SURVEY_GRANTS``-i rol siyahısına idempotent tətbiq edir."""
    for role in roles:
        wanted = SURVEY_GRANTS.get(role.get("name"))
        if not wanted:
            continue
        permissions = role.setdefault("permissions", [])
        if "*" in permissions:
            continue
        for permission in wanted:
            if permission in permissions or "survey.*" in permissions:
                continue
            permissions.append(permission)
    return roles


def merge_survey_permissions(categories: dict, category_labels: dict, permission_labels: dict) -> None:
    """Kataloqu YERİNDƏ genişləndirir (idempotent — ``merge_stage3`` ilə eyni naxış)."""
    for name, keys in SURVEY_PERMISSION_CATEGORIES.items():
        bucket = categories.setdefault(name, [])
        for key in keys:
            if key not in bucket:
                bucket.append(key)
    category_labels.update(SURVEY_CATEGORY_LABELS)
    permission_labels.update(SURVEY_PERMISSION_LABELS)


def _register_catalog() -> None:
    from . import permissions as catalog

    merge_survey_permissions(
        catalog.PERMISSION_CATEGORIES, catalog.PERMISSION_CATEGORY_LABELS, catalog.PERMISSION_LABELS
    )


_register_catalog()


__all__ = [
    "PERM_SURVEY_MANAGE",
    "PERM_SURVEY_RESULTS",
    "QUALITY_CONTROL_ROLES",
    "SURVEY_GRANTS",
    "SURVEY_PERMISSION_CATEGORIES",
    "apply_quality_control_grants",
    "merge_survey_permissions",
]
