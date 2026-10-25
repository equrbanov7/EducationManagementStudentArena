"""«Kafedra» sayılan bölmə tipləri — kafedra seçicilərinin/süzgəclərinin TƏK tərifi (sahib 2026-10-25).

NİYƏ: kafedra seçiciləri (Müəllimlər/Tələbələr kataloqu, jurnal, keçilmiş dərslər, statistika, dərs yükü, HR …)
``unit_type IN (chair, department)`` ilə qurulurdu. QKU strukturunda (``apply_org_structure``, 2026-09-27)
kafedralar ``chair``, inzibati ŞÖBƏLƏR isə ``department`` tipindədir (RİM-in «yeni inzibati bölmə» axını da şöbəni
``department`` kimi yaradır — ``accounts.services.rim.create_unit.ADMIN_UNIT_TYPES``). Nəticədə «Elm və İnnovasiyalar
şöbəsi», «Elmi Kitabxana», «Elmi nəşrlərlə iş şöbəsi» … «Kafedra» süzgəcində çıxırdı.

QAYDA (təşkilat üzrə):

* təşkilatda ``chair`` tipli bölmə VARSA — kafedra YALNIZ ``chair``-dır; ``department`` inzibati şöbədir;
* ``chair`` tipi heç işlənməyibsə (kafedraları ``department`` kimi modelləşdirən köhnə/sınaq təşkilatları) —
  ``department`` kafedra sayılmağa davam edir (davranış dəyişmir).

Nəticə təşkilat obyektinin üzərində yadda saxlanılır (sorğu başına ən çox 1 əlavə ``EXISTS``).
"""

from __future__ import annotations

from core.constants import OrgUnitType

#: Köhnə tərif — ``chair`` tipi işlənməyən təşkilatlarda qüvvədədir.
LEGACY_KAFEDRA_UNIT_TYPES = (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)
CHAIR_ONLY = (OrgUnitType.CHAIR,)
_CACHE_ATTR = "_ems_kafedra_unit_types"


def _organization_id(organization):
    if organization is None:
        return None
    return getattr(organization, "pk", organization)


def kafedra_unit_types(organization) -> tuple:
    """Bu təşkilatda «kafedra» sayılan ``OrgUnit.unit_type`` dəyərləri (``unit_type__in=`` üçün)."""
    org_id = _organization_id(organization)
    if org_id is None:
        return LEGACY_KAFEDRA_UNIT_TYPES
    cached = getattr(organization, _CACHE_ATTR, None)
    if cached is not None:
        return cached
    from .models import OrgUnit

    uses_chairs = OrgUnit.objects.filter(organization_id=org_id, unit_type=OrgUnitType.CHAIR).exists()
    result = CHAIR_ONLY if uses_chairs else LEGACY_KAFEDRA_UNIT_TYPES
    if hasattr(organization, "pk"):
        try:
            setattr(organization, _CACHE_ATTR, result)
        except AttributeError:  # pragma: no cover — slots/immutable obyekt
            pass
    return result


def kafedra_q(prefix: str = ""):
    """SORĞUSUZ ``Q`` (``OrgUnit`` üzərində, ``prefix`` — məs. ``"scope_unit__"``): eyni qayda alt-sorğu ilə —
    sorğu büdcəsi kilidli səhifələr üçün (əlavə ``EXISTS`` sorğusu yaranmır)."""
    from django.db.models import Exists, OuterRef, Q

    from .models import OrgUnit

    chairs = OrgUnit.objects.filter(organization_id=OuterRef(f"{prefix}organization_id"), unit_type=OrgUnitType.CHAIR)
    return Q(**{f"{prefix}unit_type": OrgUnitType.CHAIR}) | (
        Q(**{f"{prefix}unit_type": OrgUnitType.DEPARTMENT}) & ~Exists(chairs)
    )


def narrow_kafedra_rows(rows, type_of):
    """Sorğusuz variant: TƏŞKİLATIN BÜTÜN ``chair``/``department`` sətirləri artıq oxunubsa — içində ``chair`` varsa
    yalnız onları saxlayır (eyni qayda, əlavə ``EXISTS`` olmadan). ``type_of(row)`` sətrin ``unit_type``-ını verir."""
    rows = list(rows)
    if any(type_of(row) == OrgUnitType.CHAIR for row in rows):
        return [row for row in rows if type_of(row) == OrgUnitType.CHAIR]
    return [row for row in rows if type_of(row) in LEGACY_KAFEDRA_UNIT_TYPES]


def is_kafedra_type(organization, unit_type) -> bool:
    """``unit_type`` bu təşkilatda kafedradırmı."""
    return str(unit_type or "") in kafedra_unit_types(organization)


def is_kafedra_unit(unit) -> bool:
    """``OrgUnit`` obyekti kafedradırmı (təşkilatı obyektdən; ``organization`` yüklənibsə onun keşi işlənir)."""
    if unit is None:
        return False
    organization = unit.organization if "organization" in unit._state.fields_cache else unit.organization_id
    return is_kafedra_type(organization, unit.unit_type)


__all__ = [
    "CHAIR_ONLY",
    "LEGACY_KAFEDRA_UNIT_TYPES",
    "is_kafedra_type",
    "is_kafedra_unit",
    "kafedra_q",
    "kafedra_unit_types",
    "narrow_kafedra_rows",
]
