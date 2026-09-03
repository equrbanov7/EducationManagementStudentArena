"""Cədvəl sətirlərinin serializasiyası — avatar/baş hərflər, yaş, struktur adları.

**N+1 QADAĞASI.** Bu modul heç vaxt sətir-sətir DB-yə getmir. Struktur adları
(fakültə/kafedra) OrgUnit-in materiallaşdırılmış ``path``-indən çıxarılan
ULDUZ-ata id-lərinin TƏK toplu sorğusu ilə həll olunur
(:func:`resolve_unit_ancestors`) — sətir sayı artdıqca sorğu sayı SABİT qalır.
"""

from __future__ import annotations

from datetime import date

from .constants import FACULTY_UNIT_TYPES, KAFEDRA_UNIT_TYPES
from .filters import account_status_of


def initials_of(user) -> str:
    """Şəkli olmayan hesab üçün baş hərflər (məs. «Ə.Q.»).

    Köhnə sistemin şəkil FAYLLARI köçürməyə daxil deyil (yalnız fayl adları
    vardı), yəni 8 000+ hesabın ~93 %-i şəkilsizdir. Boş dairə əvəzinə baş
    hərflər göstərmək kataloqu oxunaqlı saxlayır.
    """
    first = (getattr(user, "first_name", "") or "").strip()
    last = (getattr(user, "last_name", "") or "").strip()
    letters = [part[0] for part in (last, first) if part]
    if not letters:
        username = (getattr(user, "username", "") or "").strip()
        letters = [username[0]] if username else ["?"]
    return "".join(letters[:2]).upper()


def avatar_url_of(profile) -> str:
    """Yüklənmiş avatarın URL-i; yoxdursa boş sətir (UI baş hərflərə keçir)."""
    avatar = getattr(profile, "avatar", None)
    if not avatar:
        return ""
    try:
        return avatar.url
    except (ValueError, AttributeError):  # fayl sahəsi boş / storage həll edə bilmir
        return ""


def age_of(birth_date, *, today: date | None = None):
    """Tam illə yaş; doğum tarixi yoxdursa ``None`` (təxmin EDİLMİR)."""
    if not birth_date:
        return None
    today = today or date.today()
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years if 0 <= years <= 150 else None


def full_name_of(user) -> str:
    name = (getattr(user, "get_full_name", lambda: "")() or "").strip()
    return name or (getattr(user, "username", "") or "")


def resolve_unit_ancestors(units, *, organization):
    """{unit_id: {"faculty": ..., "kafedra": ..., "unit": ...}} — TƏK sorğu ilə.

    ``units`` səhifədəki OrgUnit obyektləridir (müəllim üçün ``scope_unit``,
    tələbə üçün ``group``). Hər birinin ``path``-i «kök/…/özü» formatında UUID
    seqmentləridir; bütün seqmentlər yığılıb bir dəfə oxunur.
    """
    units = [unit for unit in units if unit is not None]
    if not units:
        return {}

    from apps.organizations.models import OrgUnit

    wanted_ids: set[str] = set()
    for unit in units:
        for segment in (unit.path or "").split("/"):
            segment = segment.strip()
            if segment:
                wanted_ids.add(segment)
        wanted_ids.add(str(unit.pk))

    lookup = {
        str(pk): (name, unit_type)
        for pk, name, unit_type in OrgUnit.objects.filter(organization=organization, pk__in=wanted_ids).values_list(
            "pk", "name", "unit_type"
        )
    }

    resolved: dict = {}
    for unit in units:
        segments = [segment for segment in (unit.path or "").split("/") if segment.strip()]
        if not segments:
            segments = [str(unit.pk)]
        faculty_name = ""
        kafedra_name = ""
        for segment in segments:
            row = lookup.get(segment)
            if row is None:
                continue
            name, unit_type = row
            if not faculty_name and unit_type in FACULTY_UNIT_TYPES:
                faculty_name = name
            elif not kafedra_name and unit_type in KAFEDRA_UNIT_TYPES:
                kafedra_name = name
        resolved[unit.pk] = {
            "faculty": faculty_name,
            "kafedra": kafedra_name,
            "unit": unit.name,
            "unit_type": unit.unit_type,
        }
    return resolved


def identity_row(user, *, actor, today: date | None = None) -> dict:
    """Hər iki kataloqun ORTAQ şəxsi bloku (ad, şəkil, status, əlaqə, demoqrafiya).

    Əlaqə və demoqrafiya sahələri AYRI icazə açarları ilə qapılıdır: siyahını
    görmək telefon nömrəsini və doğum tarixini görmək demək DEYİL.
    """
    profile = getattr(user, "profile", None)
    row = {
        "id": str(user.pk),
        "username": user.username,
        "full_name": full_name_of(user),
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "patronymic": (getattr(profile, "patronymic", "") or "") if profile is not None else "",
        "initials": initials_of(user),
        "avatar_url": avatar_url_of(profile),
        "status": account_status_of(user),
        "profile_url": "",
    }

    if actor.can_view_contacts:
        row["email"] = user.email or ""
        row["phone"] = (getattr(profile, "phone", "") or "") if profile is not None else ""
        row["fin"] = (getattr(profile, "fin", "") or "") if profile is not None else ""
    else:
        row["email"] = ""
        row["phone"] = ""
        row["fin"] = ""

    if actor.can_view_demographics and profile is not None:
        birth_date = getattr(profile, "birth_date", None)
        row["gender"] = getattr(profile, "gender", "") or "unspecified"
        row["birth_date"] = birth_date.isoformat() if birth_date else None
        row["age"] = age_of(birth_date, today=today)
    else:
        row["gender"] = ""
        row["birth_date"] = None
        row["age"] = None

    return row


__all__ = [
    "age_of",
    "avatar_url_of",
    "full_name_of",
    "identity_row",
    "initials_of",
    "resolve_unit_ancestors",
]
