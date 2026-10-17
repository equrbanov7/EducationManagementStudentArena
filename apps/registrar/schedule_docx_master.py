"""Magistratura dərs cədvəlinin (sahib 2026-10-17: «Magistratura şöbəsi», I/II kurs) xüsusi formatları — DB-siz.

``schedule_docx_parse`` bakalavr formatını oxuyur; bu modul magistratura sənədinin fərqlərini əlavə edir
(bakalavr hüceyrələrində «(N saat)» / elmi dərəcə yoxdur — onların oxunuşu DƏYİŞMİR):

QRUP BAŞLIĞI: «213/6BM ing (1)», «213/5 BM (1) intensiv», «209/5 KP (ing) (3)», «403/6MN (1) ing».
«/5», «/6» — qəbul ili kodu, qrupun kimliyinin hissəsidir («631/5K» ≠ «631/6K»); prod adları «631/5K»,
«631/5K ing», «505/6 MB» — boşluq/yazılış fərqi :func:`normalize_group_text` + rəqəm hissəsində
(``631 / 5`` → ``631/5``) aradan qalxır. «(N)» tələbə sayıdır (alt qrup DEYİL) — atılır; «intensiv»
atılır; «(ing)» → «ing» sektoru.

HÜCEYRƏ: «Fənn (45 saat) [dərəcə] Ad Soyad» — fənn, saat və TAM AD (ad + soyad, hər iki sıra:
«Qasımzadə Nail»). Dərəcə nişanları (t.ü.f.d., p.ü.f.d.,dos., fil.ü.f.d., i.e.n., k.e.n …), «intensiv»,
«/» atılır. «(45 saat intensiv)», «(15saat )», «(60 saəat)», bağlanmayan «(45 saat Ad Soyad» da oxunur.
Saat nişanı yoxdursa yalnız dərəcə nişanı + sonda TAM AD olan hüceyrə («Maliyyə auditi i.ü.f.d Əşrəf
Həsənov») bu formatla bölünür. Növ işarəsi yoxdur — növ tapşırıq sətrinin saat bölgüsündən gəlir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_UP = "A-ZƏÖÜĞŞÇİ"
_LOW = "a-zəöüğşçı"

_COUNT_RE = re.compile(r"\(\s*\d{1,3}\s*\)")
_INTENSIVE_RE = re.compile(r"(?<![^\W\d_])intensiv(?![^\W\d_])", re.IGNORECASE)
_PAREN_SECTOR_RE = re.compile(r"\(\s*(ing|rus|az|İng|İNG|ING)\s*\)", re.IGNORECASE)
#: «(45 saat)», «(45saat )», «(60 saəat)», «(45 saat intensiv)», bağlanmayan «(45 saat Ad Soyad».
_HOURS_RE = re.compile(r"\(\s*(\d{1,3})\s*sa[əe]?at(?![^\W\d_])\s*(intensiv)?\s*\)?", re.IGNORECASE)
#: Elmi dərəcə / ad: «t.ü.f.d.», «fil.ü.f.d», «i.e.n.», «k.e.n», «t.e.d.», «dos.», «prof.», «akad.».
_DEGREE_RE = re.compile(
    rf"(?<![{_UP}{_LOW}])(?:[{_LOW}]{{1,4}}\.\s*(?:ü\s*\.\s*f\s*\.\s*d|e\s*\.\s*n|e\s*\.\s*d)\.?|dos\.?|prof\.?|akad\.?)"
    rf"(?![{_UP}{_LOW}])",
    re.IGNORECASE,
)
_NAME_WORD_RE = re.compile(rf"^[{_UP}][{_LOW}'’-]+$")


def normalize_group_text(text: str) -> str:
    """Başlıqdan tələbə sayı «(N)», «intensiv» atılır; «(ing)» → « ing»."""
    body = _PAREN_SECTOR_RE.sub(lambda match: f" {match.group(1)} ", text)
    body = _COUNT_RE.sub(" ", body)
    body = _INTENSIVE_RE.sub(" ", body)
    return " ".join(body.split())


def has_hours_marker(text: str) -> bool:
    return bool(_HOURS_RE.search(str(text or "")))


@dataclass
class MasterCell:
    subject: str
    hours: int
    teacher: str
    intensive: bool
    teacher_unparsed: bool


def _full_name(text: str) -> tuple[str, bool]:
    """Dərəcə/«intensiv»/durğu atılmış hissə → («Ad Soyad», tanınmadımı)."""
    rest = _DEGREE_RE.sub(" ", text)
    rest = _INTENSIVE_RE.sub(" ", rest)
    words = [word for word in re.split(r"[\s,;/()]+", rest) if word.strip(" .")]
    words = [word.strip(".") for word in words]
    if not words:
        return "", False
    if len(words) == 2 and all(_NAME_WORD_RE.match(word) for word in words):
        return " ".join(words), False
    return "", True


def parse_master_cell(flat: str) -> MasterCell | None:
    """«Fənn (N saat) [dərəcə] Ad Soyad» → :class:`MasterCell`; format tanınmırsa ``None``."""
    match = _HOURS_RE.search(flat)
    if match:
        subject, tail, hours = flat[: match.start()], flat[match.end() :], int(match.group(1))
    else:
        degrees = list(_DEGREE_RE.finditer(flat))
        if not degrees or degrees[0].start() == 0:
            return None
        subject, tail, hours = flat[: degrees[0].start()], flat[degrees[0].start() :], 0
    teacher, unparsed = _full_name(tail)
    if not match and (not teacher or unparsed):
        return None  # saat nişanı yoxdursa yalnız «dərəcə + tam ad» halı bu formatdır
    intensive = bool(match and match.group(2)) or bool(_INTENSIVE_RE.search(tail + " " + subject))
    subject = " ".join(_INTENSIVE_RE.sub(" ", subject).split()).strip(" .,:;/")
    return MasterCell(subject=subject, hours=hours, teacher=teacher, intensive=intensive, teacher_unparsed=unparsed)


__all__ = ["MasterCell", "has_hours_marker", "normalize_group_text", "parse_master_cell"]
