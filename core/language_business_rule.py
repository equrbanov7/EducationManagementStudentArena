"""«Xarici dildə işgüzar (və akademik) kommunikasiya -1/-2/-3» — qiymətləndirmə profili (sahib 2026-11-22).

Sahib (RİM rəhbəri): «Dil fənlərində 10 bal sərbəst iş, 10 bal davamiyyət, 10 bal midterm. Midterm 10 balının
yazılması üçün xana da olmalıdır. Midterm balı köçürüləndə 10, finalda bunlar üçün 70 bal köçürüləcək»; həmin gün
əlavə: «səviyyəsiz adlar da (…-1, …-2, …-3)» və «Praktiki məşğələ balını hesabla seminar kimi».

Profil xarici dil SƏVİYYƏ fənlərinin (:mod:`core.language_level_rule`, 10 + 10 + 10 / 70) QİYMƏTLƏNDİRMƏ qaydasını
alır — midterm tavanı 10, imtahan 70, 11-ci q/b qaydası, imtahan körpüləri. Mötərizədə səviyyəsi OLMAYAN ad
(«…kommunikasiya-2») da profildədir: o, yalnız QİYMƏTLƏNDİRMƏ yoluna əlavə olunur (:func:`graded_level_name`,
``apps.registrar.language_level_grading.is_level``) — səviyyə qrupları / kohortlar ``level_of`` ilə qalır. Fərq:

* **Üçüncü 10 bal = praktiki məşğələ + sərbəst iş** — praktiki (seminar) dərs ballarının ortası (səviyyə qaydası
  kimi, /10) ÜSTƏGƏL sərbəst iş balı (varsa), cəmi 10-la kəsilir. Sərbəst iş tabı / fənn qovluğu bu fənlərdə RİM-in
  ümumi ``academic.selfwork_enabled`` açarından asılı olmadan açıqdır;
* **Midterm xanası müəllimə açıqdır** — İmtahan Mərkəzinin pəncərəsi olmasa da müəllim 0–10 balı jurnalda yazır
  (digər jurnal ballarının redaktə müddəti ilə; açıq pəncərədə əvvəlki kimi pəncərə qaydası).

Qayda fənn ADINDAN çıxır (köçürülmüş fənlərdə kod sabit deyil). Yazı variantları: böyük/kiçik hərf, «ə/e», «ş/s»,
«ü/u», «İ/I/i», tire/boşluq, «və» / «akademik» sözləri olan və olmayan ad, kataloqdakı «(pre-intermadiate)» xətası.
Səviyyə ya yoxdur, ya da dördündən biridir (Beginner / Elementary / Pre-intermediate / Intermediate); başqa səviyyə
adı olan fənn («upper-intermediate», «A1» …) əvvəlki səviyyə qaydasında qalır.

RİM «Sistem tənzimləmələri»: ``academic.language_business_profile`` (defolt yanılı) — söndürüləndə səviyyəli adlar
adi səviyyə qaydasına (davamiyyət + praktiki məşğələ + midterm / 70), səviyyəsiz adlar universitet standartına qayıdır.
Bu modul ``apps``-dan heç nə import etmir — registrar, fənn qovluğu və ``core.academic_rules`` buradan oxuyur.
"""

from __future__ import annotations

import re
from functools import lru_cache

#: Profilin tavanları (cəm 100): davamiyyət 10 + praktiki / sərbəst iş 10 + midterm 10 = 30, yekun imtahan 70.
SELFWORK_MAX = 10
#: Praktiki məşğələ ortası + sərbəst iş birlikdə bu tavanla kəsilir.
PRACTICAL_SELFWORK_MAX = 10
ATTENDANCE_MAX = 10
MIDTERM_MAX = 10
ENTRY_MAX = SELFWORK_MAX + ATTENDANCE_MAX + MIDTERM_MAX
EXAM_MAX = 100 - ENTRY_MAX

#: RİM «Sistem tənzimləmələri» açarı (:mod:`core.runtime_settings_language_business`).
SETTING_KEY = "academic.language_business_profile"

_FOLD = str.maketrans(
    {
        "İ": "i",
        "I": "i",
        "ı": "i",
        "Ə": "e",
        "ə": "e",
        "Ş": "s",
        "ş": "s",
        "Ü": "u",
        "ü": "u",
        "Ç": "c",
        "ç": "c",
        "Ö": "o",
        "ö": "o",
        "Ğ": "g",
        "ğ": "g",
        "–": "-",
        "—": "-",
        "‑": "-",
    }
)

#: Normallaşdırılmış (ASCII, kiçik hərf, tək boşluq) ad üzərində işləyir — :func:`fold`.
BUSINESS_RE = re.compile(
    r"^xarici dilde isguzar (?:ve )?(?:akademik )?kom{1,2}unikasiya ?-? ?[123](?!\d) ?"
    r"(?:\( ?(?:beginner|elementary|pre ?-? ?interm[ae]diate|interm[ae]diate) ?\))?$"
)


def fold(name) -> str:
    """Ad → müqayisə forması: Azərbaycan hərfləri ASCII-yə, kiçik hərf, tire variantları «-», tək boşluq."""
    text = str(name or "").translate(_FOLD).lower()
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=4096)
def _matches(folded: str) -> bool:
    return bool(BUSINESS_RE.match(folded))


def is_business_name(name) -> bool:
    """Fənn adı «Xarici dildə işgüzar (və akademik) kommunikasiya -1/-2/-3 (dörd səviyyədən biri)»-dirmi."""
    return _matches(fold(name))


def profile_enabled() -> bool:
    """RİM açarı — söndürülübsə profil heç yerdə tətbiq olunmur (fənlər adi səviyyə qaydasına qayıdır)."""
    from core import runtime_settings

    return runtime_settings.get_bool(SETTING_KEY)


def applies_to_name(name) -> bool:
    """Ad + RİM açarı (dövr qapısı registrar-dadır — ``apps.registrar.language_business_grading.is_business``)."""
    return is_business_name(name) and profile_enabled()


def is_nolevel_business_name(name) -> bool:
    """Profil adı, amma mötərizədə səviyyə YOXDUR («…kommunikasiya-2») — səviyyə qrupuna düşmür, qiymətləndirməsi profildir."""
    from core.language_level_rule import level_of

    return is_business_name(name) and not level_of(name)


def graded_level_name(name) -> bool:
    """QİYMƏTLƏNDİRMƏ üçün səviyyə qaydası (10 + 10 + 10 / 70) bu ada aiddirmi: səviyyəli ad və ya profil adı (RİM
    açarı ilə). Kohort / səviyyə qrupu məntiqi bunu İŞLƏTMİR — orada ``core.language_level_rule.level_of``."""
    from core.language_level_rule import is_level_name

    return is_level_name(name) or applies_to_name(name)


def offering_subject_name(offering) -> str:
    subject = getattr(offering, "subject", None) if offering is not None else None
    return str(getattr(subject, "name", "") or "")


__all__ = [
    "ATTENDANCE_MAX",
    "BUSINESS_RE",
    "ENTRY_MAX",
    "PRACTICAL_SELFWORK_MAX",
    "EXAM_MAX",
    "MIDTERM_MAX",
    "SELFWORK_MAX",
    "SETTING_KEY",
    "applies_to_name",
    "fold",
    "graded_level_name",
    "is_business_name",
    "is_nolevel_business_name",
    "offering_subject_name",
    "profile_enabled",
]
