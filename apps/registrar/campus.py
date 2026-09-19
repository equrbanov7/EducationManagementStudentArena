"""Korpus (kampus) defoltu — açılışın qrupu hansı ixtisasdadırsa, dərs modalında
o ixtisasın korpusu ƏVVƏLCƏDƏN seçilir (sahib qərarı 2026-09-20: «hansı qrupun
dərsidirsə ixtisası əsas olaraq korpus seçilmiş görünsün, istəsə müəllim dəyişə
bilər»).

Korpus ayrıca model DEYİL — ``exams.ExamRoom.building`` mətnidir (bax
:mod:`apps.registrar.lesson_rooms`). Xəritə isə DATA-dır, kod deyil:
``Organization.settings["campuses"]`` siyahısı::

    [
      {"building": "Korpus B", "address": "Əhməd Rəcəbli küç., III Paralel, 21",
       "units": ["Kompüter mühəndisliyi", "İnformasiya texnologiyaları", …]},
      …
    ]

``units`` — struktur vahidinin (ixtisas / kafedra / fakültə) ADI. Uyğunluq
qrupun ata zənciri üzrə AŞAĞIDAN YUXARI axtarılır: əvvəl ixtisas, tapılmasa
kafedra, sonra fakültə/məktəb. Beləcə «Ekologiya» ixtisası A korpusunda, amma
eyni fakültənin «Kompüter mühəndisliyi» ixtisası B korpusunda ola bilir.
Adlar normallaşdırılır (böyük/kiçik hərf, «ı/i», artıq boşluq) ki, ATİS/legacy
yazılış fərqləri uyğunluğu pozmasın.

Fail-open: xəritə yoxdursa və ya uyğunluq tapılmırsa ``""`` — modal əvvəlki kimi
korpussuz açılır; heç bir yazı əməli bundan asılı deyil.
"""

from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")


def normalize_unit_name(value) -> str:
    """Ad müqayisəsi üçün açar: kiçik hərf (AZ «İ/ı» daxil), diakritiksiz, tək boşluq."""
    text = str(value or "").replace("İ", "i").replace("I", "ı").lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("ə", "e").replace("ö", "o").replace("ü", "u").replace("ğ", "g").replace("ş", "s")
    text = text.replace("ç", "c").replace("ı", "i")
    return _WS.sub(" ", text).strip()


def campus_entries(organization) -> list[dict]:
    """Təşkilatın korpus xəritəsi — yalnız düzgün formalı sətirlər."""
    raw = (getattr(organization, "settings", None) or {}).get("campuses") or []
    entries = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        building = str(item.get("building") or "").strip()
        if not building:
            continue
        units = [str(u).strip() for u in (item.get("units") or []) if str(u or "").strip()]
        entries.append({"building": building, "address": str(item.get("address") or "").strip(), "units": units})
    return entries


def _unit_index(entries) -> dict[str, str]:
    index: dict[str, str] = {}
    for entry in entries:
        for unit in entry["units"]:
            index.setdefault(normalize_unit_name(unit), entry["building"])
    return index


def default_building_for_group(organization, group) -> str:
    """Qrupun (və ata zəncirinin) korpusu — tapılmasa ``""``."""
    if group is None:
        return ""
    index = _unit_index(campus_entries(organization))
    if not index:
        return ""
    node = group
    seen = 0
    while node is not None and seen < 12:  # ata zənciri qısa olur; sonsuz dövrə qapısı
        key = normalize_unit_name(getattr(node, "name", ""))
        if key in index:
            return index[key]
        node = getattr(node, "parent", None)
        seen += 1
    return ""


def default_building_for_offering(offering) -> str:
    """Açılışın qrupuna görə korpus defoltu (bax :func:`default_building_for_group`)."""
    return default_building_for_group(offering.organization, getattr(offering, "group", None))
