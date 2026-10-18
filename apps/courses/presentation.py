"""Kursun vizual kimliyi — deterministik aksent tonu və fənn ikonu (2026-10-18).

Niyə deterministik? «Kurslarım» kartları əvvəl hamısı eyni solğun narıncı qapaqla
gəlirdi; təsadüfi rəng isə hər açılışda dəyişərdi. Ton kursun FƏNNİNDƏN (bağlı
sillabus varsa onun fənn kodu/adı), yoxdursa adından ``crc32`` ilə seçilir: eyni
fənnin kursları eyni rəngdə, panel və kart bir-biri ilə uyğun olur.

Rəng BURADA YOXDUR — yalnız ton adı. Ton → token xəritəsi
``courses/css/course_accent.css``-dədir (``crs-accent--<ad>`` → ``--ems-*``), kontrast
(100 fonda 800 mətn ≥ 7:1, 600 üzərində ağ ikon ≥ 3:1) orada izah olunub.
"""

from __future__ import annotations

import re
import zlib

#: Kurasiya olunmuş tonlar — sıra DƏYİŞMƏMƏLİDİR (mövcud kursların rəngi sürüşər).
ACCENTS: tuple[str, ...] = ("blue", "teal", "violet", "amber", "rose", "sky", "emerald", "indigo")

#: Fənn adında açar söz → Font Awesome ikonu (ilk uyğunluq qalib gəlir; az/en/ru/tr kökləri).
_ICON_RULES: tuple[tuple[str, str], ...] = (
    (r"verilən|baza|sql|database|данн|veritaban", "fa-database"),
    (r"şəbək|network|сет", "fa-network-wired"),
    (r"alqoritm|algorithm|алгоритм|struktur", "fa-diagram-project"),
    (r"veb|web|html|front", "fa-globe"),
    (r"proqram|python|java|kod|code|program|програм|yazılım", "fa-code"),
    (r"riyaz|math|матем|statist|hesab|diskret|calculus", "fa-square-root-variable"),
    (r"fizik|physic|физ|kimya|chem|хим|biolog", "fa-flask"),
    (r"dil|ingilis|english|language|язык|rus|alman|türk", "fa-language"),
    (r"iqtisad|econom|экон|mühasib|account|maliyy|financ", "fa-chart-line"),
    (r"tarix|history|истор|fəlsəf|philosoph", "fa-landmark"),
    (r"təhlükəsiz|security|kiber|cyber", "fa-shield-halved"),
    (r"dizayn|design|qrafik|graphic", "fa-pen-ruler"),
)
_DEFAULT_ICON = "fa-graduation-cap"


def _subject_of(course):
    syllabus = getattr(course, "syllabus", None) if getattr(course, "syllabus_id", None) else None
    return getattr(syllabus, "subject", None) if syllabus is not None else None


def accent_seed(course) -> str:
    """Tonun hesablandığı sabit açar: fənn kodu → fənn adı → kurs adı."""
    subject = _subject_of(course)
    if subject is not None:
        return (getattr(subject, "code", "") or getattr(subject, "name", "") or "").strip().casefold()
    return re.sub(r"\s+", " ", (getattr(course, "title", "") or "").strip()).casefold()


def accent_for(seed: str) -> str:
    return ACCENTS[zlib.crc32(seed.encode("utf-8")) % len(ACCENTS)]


def icon_for(text: str) -> str:
    lowered = (text or "").casefold()
    for pattern, icon in _ICON_RULES:
        if re.search(pattern, lowered):
            return icon
    return _DEFAULT_ICON


def course_identity(course) -> dict:
    """``{"accent": "teal", "icon": "fa-database"}`` — sorğusuz (fənn ``select_related`` ilə gəlir)."""
    subject = _subject_of(course)
    label = getattr(subject, "name", "") if subject is not None else ""
    return {"accent": accent_for(accent_seed(course)), "icon": icon_for(f"{label} {course.title}")}


def decorate(courses) -> list:
    """Kart siyahısına ``ui_accent`` / ``ui_icon`` atributları yazır (yerində)."""
    for course in courses:
        identity = course_identity(course)
        course.ui_accent = identity["accent"]
        course.ui_icon = identity["icon"]
    return courses


__all__ = ["ACCENTS", "accent_for", "accent_seed", "course_identity", "decorate", "icon_for"]
