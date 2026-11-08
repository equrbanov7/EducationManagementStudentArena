"""Xarici dil SƏVİYYƏ fənlərinin qaydası — TƏK reyestr (sahib 2026-11-01, təsdiq və genişləndirmə 2026-11-08).

Fənn adında mötərizədə səviyyə olan fənlər — «Xarici dildə işgüzar və akademik kommunikasiya-1(elementary)»,
«…-1 (Beginner)», «…-1(pre-intermediate)», «…-1(intermediate)» və yazın «-2 …» cütləri (tədris şöbəsi onları
Beginner / Elementary / … kimi bölür):

* **Qiymətləndirmə** — davamiyyət 10 + praktiki məşğələ (aktivlik) 10 + midterm 10 = imtahana qədər 30;
  yekun imtahan 70; cəm 100. Qalan fənlər universitet standartında qalır (10 + 10 + 30 = 50, imtahan 50).
* **Dərs növü** — bu fənlərin «Seminar»ı «Praktiki məşğələ»dir (yalnız görünüş adı: saxlanan növ ``seminar``
  qalır — bax :mod:`apps.registrar.practical_label`). Açılış bayrağı / kafedra yoxlaması tələb olunmur.

Qərar fənn ADINDAN çıxır (köçürülmüş fənlərdə kod sabit deyil — «QKU-N»; ad isə köhnə sistemdən olduğu kimi gəlir).
Yazı variantları normallaşdırılır: böyük/kiçik hərf, «pre intermediate» / «pre-intermediate», kataloqdakı
«(pre-intermadiate)» yazı xətası. Bu modul ``apps``-dan heç nə import etmir — registrar, sillabus və kabinet
eyni cavabı buradan oxuyur (:mod:`apps.registrar.language_levels`, :mod:`apps.registrar.language_level_grading`,
:mod:`apps.syllabus.assessment_formula`).
"""

from __future__ import annotations

import re

#: Səviyyə fənninin bal tavanları (sahib 2026-11-08: «10 davamiyyət, 10 seminar, 10 midterm, imtahan 70»).
ATTENDANCE_MAX = 10
ACTIVITY_MAX = 10
MIDTERM_MAX = 10
ENTRY_MAX = ATTENDANCE_MAX + ACTIVITY_MAX + MIDTERM_MAX
EXAM_MAX = 100 - ENTRY_MAX
#: Səviyyə fənnində imtahana buraxılış sayla ölçülür: 10 q/b icazəlidir, 11-ci q/b kəsir.
ABSENCE_LIMIT = 10

# Kataloqda «(pre-intermadiate)» yazı xətası da var (2026-10-27: 30 açılış səviyyə sayılmırdı) — «interm[ae]diate».
LEVEL_RE = re.compile(
    r"\(\s*(beginner|elementary|pre[- ]?interm[ae]diate|interm[ae]diate|upper[- ]?interm[ae]diate|advanced|[abc][12])"
    r"\s*\)",
    re.IGNORECASE,
)


def level_of(name) -> str:
    """Fənn adındakı səviyyə («elementary» …) və ya boş sətir; yazı variantları kanonik formaya salınır."""
    match = LEVEL_RE.search(str(name or ""))
    if not match:
        return ""
    value = re.sub(r"[\s-]+", "-", match.group(1).lower()).replace("intermadiate", "intermediate")
    return {"preintermediate": "pre-intermediate", "upperintermediate": "upper-intermediate"}.get(value, value)


def is_level_name(name) -> bool:
    """Fənn səviyyə fənnidirmi (qiymətləndirmə 10/10/10/70 + «Praktiki məşğələ»)."""
    return bool(level_of(name))


def level_family(name) -> str:
    """Səviyyə atılmış fənn ailəsi: «Xarici dil-1(elementary)» = «xarici dil-1»."""
    return re.sub(r"\s+", " ", LEVEL_RE.sub("", str(name or ""))).strip().lower()


def is_practical_name(name) -> bool:
    """Bu fənnin seminarı həmişə «Praktiki məşğələ» adlanırmı (sahib 2026-11-08: səviyyə fənləri praktikidir)."""
    return is_level_name(name)


__all__ = [
    "ABSENCE_LIMIT",
    "ACTIVITY_MAX",
    "ATTENDANCE_MAX",
    "ENTRY_MAX",
    "EXAM_MAX",
    "LEVEL_RE",
    "MIDTERM_MAX",
    "is_level_name",
    "is_practical_name",
    "level_family",
    "level_of",
]
