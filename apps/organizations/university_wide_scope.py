"""Universitet əhatəli kafedra — namizəd TƏLƏBƏLƏR bütün təşkilatdan (sahib 2026-11-22, RİM rəhbəri).

Sahib: «Xarici dil kafedrasında tyutorlar və dekanlıq işçiləri qrup yaradanda və ya alt qrupa tələbə əlavə edəndə
bütün universitetdən qrupları götürürlər. Onların qrup-tələbə görünüşünü universitet üzrə dəyişin — oradakı qruplar
universitetin bütün məktəblərinin tələbələrini bir qrupa yığır.»

TƏK QAYDA
─────────
Hədəf (qrup reyestrində qrup, «Alt qrupdan tələbə əlavə et»də jurnalın qrupu, səviyyə qrupunun kafedrası)
universitet əhatəli kafedranın ALT-AĞACINDADIRSA, namizəd tələbə əhatəsi bütün təşkilatdır
(:func:`candidate_scope`). Hədəfi olmayan «əvvəl tələbə» alətində («Alt qrupa yerləşdirmə») aktorun açarı daşıyan
üzvlüyü belə kafedraya (və ya altına) bağlıdırsa eyni genişlənmə (:func:`actor_in_university_wide_chair`).

Yalnız NAMİZƏD TƏLƏBƏ əhatəsi genişlənir:

* kim qrup yarada / tələbə əlavə edə bilər — açar + hədəfin aktorun öz əhatəsində olması — DƏYİŞMİR;
* tələbə + heyət rolunun «öz qrupu» istisnası (``UnitScope.excluded_unit_ids``) qalır;
* təşkilat sərhədi qalır — çağıranlar həmişə ``organization=`` ilə süzür (RLS də);
* namizədlər yalnız tələbə qeydləridir (``StudentAcademicRecord``) — heyət heç vaxt.

HANSI KAFEDRA (data ilə)
────────────────────────
``OrgUnit.settings["university_wide_students"]`` (kafedra tipli vahiddə): ``true`` — universitet əhatəli,
``false`` — açıq imtina. Açar yoxdursa DEFOLT: Xarici dillər kafedrası — 2026-09-27 struktur planının açarı
(``settings.structure_key`` → ``…:ch_foreign_lang``) və ya adı «Xarici dil…» ilə başlayan kafedra. Ümumi açar:
«Sistem tənzimləmələri» → «Akademik qaydalar» → ``academic.university_wide_chairs`` (defolt yanılı); söndürüləndə
əvvəlki qayda.
"""

from __future__ import annotations

from dataclasses import replace

from core.constants import OrgUnitType

from .scoping import ORG_WIDE_SCOPE, UnitScope, permission_scope_units

#: Kafedra vahidinin ``settings`` bayrağı (``true`` / ``false``; yoxdursa defolt qayda).
FLAG_KEY = "university_wide_students"
#: 2026-09-27 struktur planında Xarici dillər kafedrasının açarı (``scripts/data/qku_structure_2026_09_27.json``).
DEFAULT_STRUCTURE_SUFFIX = ":ch_foreign_lang"
DEFAULT_NAME_PREFIX = "xarici dil"
CHAIR_TYPES = (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)


def enabled() -> bool:
    from core import runtime_settings
    from core.runtime_settings_university_scope import KEY_UNIVERSITY_WIDE_CHAIRS

    return runtime_settings.get_bool(KEY_UNIVERSITY_WIDE_CHAIRS)


def _default_match(unit) -> bool:
    settings = unit.settings if isinstance(unit.settings, dict) else {}
    if str(settings.get("structure_key") or "").endswith(DEFAULT_STRUCTURE_SUFFIX):
        return True
    return " ".join(str(unit.name or "").split()).casefold().startswith(DEFAULT_NAME_PREFIX)


def is_university_wide_chair(unit) -> bool:
    """Bu kafedra vahidi universitet əhatəlidir (bayraq və ya defolt qayda; ümumi açarı YOXLAMIR)."""
    if unit is None or unit.unit_type not in CHAIR_TYPES:
        return False
    settings = unit.settings if isinstance(unit.settings, dict) else {}
    if FLAG_KEY in settings:
        return settings.get(FLAG_KEY) is True
    return _default_match(unit)


def university_wide_chairs(organization) -> tuple:
    """Təşkilatın universitet əhatəli AKTİV kafedralarının ``(pk, path)`` cütləri; açar sönülüdürsə boş."""
    if organization is None or not enabled():
        return ()
    from .models import OrgUnit

    rows = OrgUnit.objects.filter(organization=organization, is_active=True, unit_type__in=CHAIR_TYPES).only(
        "id", "name", "path", "unit_type", "settings"
    )
    return tuple((row.pk, row.path) for row in rows if is_university_wide_chair(row))


def _within(unit_pk, unit_path, chairs) -> bool:
    path = str(unit_path or "")
    return any(unit_pk == pk or (chair_path and path.startswith(f"{chair_path}/")) for pk, chair_path in chairs)


def unit_is_university_wide(organization, unit) -> bool:
    """Vahid (obyekt və ya id) universitet əhatəli kafedranın özü və ya alt-ağacındadırmı."""
    if unit is None or organization is None:
        return False
    chairs = university_wide_chairs(organization)
    if not chairs:
        return False
    if not hasattr(unit, "path"):
        from .models import OrgUnit

        unit = OrgUnit.objects.filter(organization=organization, pk=unit).only("id", "path").first()
        if unit is None:
            return False
    return _within(unit.pk, unit.path, chairs)


def actor_in_university_wide_chair(user, organization, permission: str) -> bool:
    """``permission`` daşıyan UNIT üzvlüklərindən biri universitet əhatəli kafedraya (və ya altına) bağlıdırmı."""
    units = permission_scope_units(user, organization, permission)
    if not units:
        return False
    chairs = university_wide_chairs(organization)
    return bool(chairs) and any(_within(unit.pk, unit.path, chairs) for unit in units)


def widen(scope: UnitScope) -> UnitScope:
    """Struktur əhatəsi olan aktor üçün bütün təşkilat — «öz qrupu» istisnası saxlanılır."""
    if not scope.has_structure_access or scope.is_org_wide:
        return scope
    return replace(ORG_WIDE_SCOPE, excluded_unit_ids=scope.excluded_unit_ids)


def candidate_scope(organization, scope: UnitScope, target) -> UnitScope:
    """Hədəf universitet əhatəli kafedradadırsa namizəd əhatəsi bütün təşkilat, yoxsa ``scope`` olduğu kimi."""
    if not scope.has_structure_access or scope.is_org_wide:
        return scope
    # Sahib 2026-11-25: əcnəbi qrupuna tələbə BÜTÜN universitetdən gəlir (öz qrupu başqa məktəbdə olur).
    from .group_kind import is_foreign

    if getattr(target, "unit_type", "") == "group" and is_foreign(target):
        return widen(scope)
    return widen(scope) if unit_is_university_wide(organization, target) else scope


__all__ = [
    "FLAG_KEY",
    "actor_in_university_wide_chair",
    "candidate_scope",
    "enabled",
    "is_university_wide_chair",
    "unit_is_university_wide",
    "university_wide_chairs",
    "widen",
]
