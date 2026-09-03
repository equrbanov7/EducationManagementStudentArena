"""Akademik qrup köməkçiləri — tutum, doluluq, avtomatik təklif, yaratma.

NİYƏ ``accounts``-DA? Qrup ``organizations.OrgUnit``-dir, doluluq isə
``registrar.StudentAcademicRecord``-dan sayılır. Modul sərhədi qaydası
(``scripts/module_deps.py``) ikisinin bir-birini import etməsini istəmir —
``registrar`` ``organizations``-a YALNIZ string-ref FK ilə baxır. ``accounts``
isə onsuz da hər ikisinin istehlakçısıdır (``services/people``, ``services/intake``),
ona görə GLUE burada yaşayır və HƏM qəbul (ekran 08), HƏM də reyestr
(ekran 09) eyni mənbədən oxuyur.

Qrup metadatası ``OrgUnit.settings`` JSON-undadır:

    {"capacity": 25, "language_sector": "az"}

⚠️ SEKTOR HARDCODE EDİLMİR (layihə yaddaşı: «akademik struktur universitetə
görə dəyişir → tenant-konfiqurasiya olunan»). Dəyər sərbəst mətndir; müqayisə
normallaşdırılmış şəkildə aparılır (``az``/``AZ``/``Azərbaycan`` → ``az``).
"""

from __future__ import annotations

import unicodedata

from core.constants import OrgUnitType

#: Qrupun default yer limiti — NK «Tədris prosesinin təşkili» qaydası: 15–30.
#: Tenant öz dəyərini ``OrgUnit.settings["capacity"]`` ilə verir; kodda BAŞQA
#: hardcode YOXDUR.
DEFAULT_GROUP_CAPACITY = 30

#: Sektorun normallaşdırılmış qısaltmaları (yalnız MÜQAYİSƏ üçün — saxlanılan
#: dəyər istifadəçinin yazdığıdır).
_SECTOR_ALIASES = {
    "az": "az",
    "aze": "az",
    "azərbaycan": "az",
    "azerbaycan": "az",
    "en": "en",
    "eng": "en",
    "ing": "en",
    "ingilis": "en",
    "english": "en",
    "ru": "ru",
    "rus": "ru",
    "русский": "ru",
}


def normalize_sector(value) -> str:
    """Dil bölməsini müqayisə açarına çevirir (boş → "")."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    if not text:
        return ""
    return _SECTOR_ALIASES.get(text, text)


def group_capacity(unit) -> int:
    """Qrupun yer limiti — vahidin öz ayarı, yoxsa default."""
    raw = (getattr(unit, "settings", None) or {}).get("capacity")
    try:
        capacity = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_GROUP_CAPACITY
    return capacity if capacity > 0 else DEFAULT_GROUP_CAPACITY


def group_sector(unit) -> str:
    """Qrupun dil bölməsi (normallaşdırılmamış — göstərilən dəyər)."""
    return str((getattr(unit, "settings", None) or {}).get("language_sector") or "")


def groups_under(organization, specialty_unit):
    """İxtisasın altındakı AKTİV akademik qruplar (materiallaşdırılmış yol)."""
    from apps.organizations.models import OrgUnit

    if specialty_unit is None:
        return OrgUnit.objects.none()
    prefix = f"{specialty_unit.path}/"
    return OrgUnit.objects.filter(
        organization=organization,
        unit_type=OrgUnitType.GROUP,
        is_active=True,
    ).filter(path__startswith=prefix)


def occupancy_map(organization, group_ids) -> dict:
    """``{group_id: aktiv tələbə sayı}`` — BİR sorğu (annotasiya deyil, aqreqat)."""
    from django.db.models import Count

    from apps.registrar.models import AcademicStatus, StudentAcademicRecord

    ids = [gid for gid in group_ids if gid]
    if not ids:
        return {}
    rows = (
        StudentAcademicRecord.objects.filter(
            organization=organization,
            group_id__in=ids,
            status=AcademicStatus.ENROLLED,
        )
        .values("group_id")
        .annotate(total=Count("id"))
    )
    return {str(row["group_id"]): row["total"] for row in rows}


def group_options(organization, specialty_unit, *, sector: str = "") -> list:
    """Qrup seçicisinin sətirləri: ad, tutum, doluluq, boş yer, sektor.

    Sektor verilibsə UYĞUN gələnlər ƏVVƏLƏ çıxır (süzülmür — operator qarışıq
    sektorlu qrupa da təyin edə bilməlidir, amma default təklif düzgün olsun).
    """
    units = list(groups_under(organization, specialty_unit).only("id", "name", "code", "settings", "path"))
    occupancy = occupancy_map(organization, [unit.pk for unit in units])
    wanted = normalize_sector(sector)

    rows = []
    for unit in units:
        capacity = group_capacity(unit)
        taken = occupancy.get(str(unit.pk), 0)
        unit_sector = group_sector(unit)
        rows.append(
            {
                "id": str(unit.pk),
                "name": unit.name,
                "code": unit.code or "",
                "sector": unit_sector,
                "capacity": capacity,
                "taken": taken,
                "free": max(capacity - taken, 0),
                "is_full": taken >= capacity,
                "sector_match": bool(wanted) and normalize_sector(unit_sector) == wanted,
            }
        )
    rows.sort(key=lambda row: (not row["sector_match"], row["is_full"], -row["free"], row["name"]))
    return rows


def propose_group(rows, *, needed: int = 1) -> dict | None:
    """Avtomatik təklif: sektoru uyğun, BOŞ YERİ ÇATAN ilk qrup.

    ``None`` — uyğun qrup yoxdur (UI «Yeni qrup yarat» addımını göstərir).
    """
    for row in rows:
        if row["free"] >= needed:
            return row
    return None


def suggest_group_name(organization, specialty_unit, *, admission_year, sector: str = "") -> str:
    """«Yeni qrup yarat» dialoqunun ÖN DOLDURULMASI (operator dəyişə bilər).

    Ad şablonu tenant-a görə dəyişdiyi üçün burada YALNIZ təklif verilir və
    heç yerdə məcburi deyil: `<qəbul ili> <ixtisas qısaltması>[ <sektor>][-N]`.
    """
    base_parts = [str(admission_year or "").strip()]
    short = (getattr(specialty_unit, "code", "") or "").strip()
    if not short:
        short = "".join(word[:1] for word in str(getattr(specialty_unit, "name", "")).split()[:3]).upper()
    base_parts.append(short)
    normalized = normalize_sector(sector)
    if normalized and normalized != "az":
        base_parts.append(normalized)
    base = " ".join(part for part in base_parts if part) or "Yeni qrup"

    existing = set(groups_under(organization, specialty_unit).values_list("name", flat=True))
    if base not in existing:
        return base
    index = 2
    while f"{base}-{index}" in existing:
        index += 1
    return f"{base}-{index}"


def create_group(organization, *, specialty_unit, name: str, capacity: int, sector: str = "", code: str = ""):
    """Yeni akademik qrup yaradır (``OrgUnit``, ixtisasın altında).

    ⚠️ Bu funksiya İCAZƏ YOXLAMIR — çağıran (`views/student_admission.py`)
    ``student.assign_group`` açarını ƏVVƏLCƏDƏN yoxlayır və audit yazır.
    Mərhələ 2-nin qrup reyestri servisi gələndə bu funksiya ORAYA köçürülüb
    burada fasadla əvəz oluna bilər — çağırış səthi dəyişməz qalsın deyə
    imza qəsdən sadədir.
    """
    from apps.organizations.models import OrgUnit

    label = str(name or "").strip()
    if not label:
        raise ValueError("group_name_required")
    if specialty_unit is None or specialty_unit.organization_id != organization.pk:
        raise ValueError("specialty_outside_tenant")
    if OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.GROUP, name=label).exists():
        raise ValueError("group_name_taken")

    try:
        limit = int(capacity)
    except (TypeError, ValueError):
        limit = DEFAULT_GROUP_CAPACITY
    limit = max(1, min(limit, 200))

    return OrgUnit.objects.create(
        organization=organization,
        parent=specialty_unit,
        unit_type=OrgUnitType.GROUP,
        name=label,
        code=str(code or "").strip()[:50],
        settings={"capacity": limit, "language_sector": str(sector or "").strip()},
        is_active=True,
    )


__all__ = [
    "DEFAULT_GROUP_CAPACITY",
    "create_group",
    "group_capacity",
    "group_options",
    "group_sector",
    "groups_under",
    "normalize_sector",
    "occupancy_map",
    "propose_group",
    "suggest_group_name",
]
