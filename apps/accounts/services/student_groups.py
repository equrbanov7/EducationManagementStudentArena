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

import re
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
    "azərbaycan dili": "az",
    "azerbaycan dili": "az",
    "ingilis dili": "en",
    "i̇ngilis dili": "en",
    "de": "de",
    "alman": "de",
    "alman dili": "de",
    "german": "de",
    "ru": "ru",
    "rus dili": "ru",
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
    """İxtisasın altındakı AKTİV akademik qruplar (materiallaşdırılmış yol).

    ``is_service_unit=True`` qruplar (köçürmədən gələn dil-kursu koqortası,
    status konteyneri və s. — bax ``OrgUnit.is_service_unit``) BURADA
    süzülür: onlar həqiqi akademik qrup deyil, seçicidə göstərilmir. Mövcud
    ``StudentAcademicRecord.group`` istinadları toxunulmur — yalnız YENİ
    seçim üçün gizlədilir.
    """
    from apps.organizations.models import OrgUnit

    if specialty_unit is None:
        return OrgUnit.objects.none()
    prefix = f"{specialty_unit.path}/"
    return OrgUnit.objects.filter(
        organization=organization,
        unit_type=OrgUnitType.GROUP,
        is_active=True,
        is_service_unit=False,
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


_GROUP_YEAR_RE = re.compile(r"^(?:\d/)?(\d{3,4})")


def group_admission_year(unit) -> int | None:
    """Qrupun qəbul ili: ad şablonundan; şablonsuz addan yalnız etibarlı ayar.

    QKU şablonu: «236 K» / «536 Bİ» / «2236 M» / «3/336 F» — rəqəm blokunun SON
    rəqəmi ilin son rəqəmidir (233 → 2023 … 236 → 2026). Onilliyi cari ildən
    götürürük (on ildən köhnə qruplar reyestrdə qalmır).
    """
    settings = getattr(unit, "settings", None) or {}
    match = _GROUP_YEAR_RE.match(str(getattr(unit, "name", "") or "").strip())
    if not match:
        # Ad şablonsuz qrup: ayar YALNIZ köçürmə («legacy») damğası yoxdursa etibarlıdır —
        # köçürülmüş qruplarda `admission_year` idxal ili ilə doldurulub (2026-09-19 tapıntısı).
        raw = settings.get("admission_year") if "legacy" not in settings else None
        try:
            return int(raw) if raw else None
        except (TypeError, ValueError):
            return None
    digit = int(match.group(1)[-1])
    from datetime import date

    decade = date.today().year // 10 * 10
    year = decade + digit
    return year if year <= date.today().year + 1 else year - 10


_MASTER_NAME_RE = re.compile(r"^(?:\d{4}\b|\d{3}/\d)")


def group_degree_level(unit) -> str:
    """Qrupun səviyyəsi: `settings.degree_level`, yoxdursa QKU ad şablonu.

    Magistr qrupları 4 rəqəmlə («2236 M», «2536 MRK») və ya «NNN/N» («631/6 K»,
    «510/6 E») yazılır; bakalavr 3 rəqəmlə («236 K») və ya «N/NNN» («3/336 F»).
    Tanınmasa boş sətir (süzülmür).
    """
    settings = getattr(unit, "settings", None) or {}
    name = str(getattr(unit, "name", "") or "").strip()
    if _MASTER_NAME_RE.match(name):
        return "master"
    if re.match(r"^(?:\d/)?\d{3}\b", name):
        return "bachelor"
    # Şablonsuz ad: ayar yalnız köçürmə damğası yoxdursa (köçürülmüş qruplarda hamısı «bachelor»).
    raw = str(settings.get("degree_level") or "").strip().lower() if "legacy" not in settings else ""
    return raw


def group_options(
    organization, specialty_unit, *, sector: str = "", admission_year=None, degree_level: str = ""
) -> list:
    """Qrup seçicisinin sətirləri: ad, tutum, doluluq, boş yer, sektor.

    Sektor verilibsə UYĞUN gələnlər ƏVVƏLƏ çıxır (süzülmür — operator qarışıq
    sektorlu qrupa da təyin edə bilməlidir, amma default təklif düzgün olsun).
    ``admission_year`` verilibsə ili məlum olub FƏRQLİ olan qruplar atılır (2026-09-19:
    ATİS idxalı 2026 tələbəsini boş yeri olan 2025 qrupuna yığmasın); ili ad
    şablonundan/ayardan bilinməyən qrup qalır.
    """
    units = list(groups_under(organization, specialty_unit).only("id", "name", "code", "settings", "path"))
    if admission_year:
        try:
            wanted_year = int(str(admission_year).strip().split(".")[0])
        except (TypeError, ValueError):
            wanted_year = None
        if wanted_year:
            # İli məlum olan və FƏRQLİ olan qruplar atılır. İxtisasda ili məlum qrup
            # VARSA yalnız həmin ilinkilər qalır («Xaric olunanlar» kimi xidməti/ilsiz
            # adlar təklif olunmur); heç birinin ili bilinmirsə hamısı qalır.
            years = {unit.pk: group_admission_year(unit) for unit in units}
            if any(year is not None for year in years.values()):
                units = [unit for unit in units if years[unit.pk] == wanted_year]
    if degree_level:
        wanted_level = "master" if str(degree_level).lower().startswith("m") else "bachelor"
        units = [unit for unit in units if group_degree_level(unit) in ("", wanted_level)]
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


def propose_group(rows, *, needed: int = 1, allow_full: bool = False) -> dict | None:
    """Avtomatik təklif: sektoru uyğun, BOŞ YERİ ÇATAN ilk qrup.

    ``None`` — uyğun qrup yoxdur (UI «Yeni qrup yarat» addımını göstərir).
    ``allow_full`` (ATİS toplu idxalı, 2026-09-19): sektoru uyğun qrupların hamısı
    doludursa ən az dolu olan təklif olunur — tutum yumşaq həddir, kafedra sonra
    bölür; tələbə qrupsuz qalmır.
    """
    for row in rows:
        if row["free"] >= needed:
            return row
    if allow_full:
        matching = [row for row in rows if row["sector_match"]] or list(rows)
        if matching:
            return min(matching, key=lambda row: (row["taken"] - row["capacity"], row["name"]))
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
