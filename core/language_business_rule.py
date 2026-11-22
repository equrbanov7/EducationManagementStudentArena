"""«Xarici dildə işgüzar (və akademik) kommunikasiya -1/-2/-3 (səviyyə)» — qiymətləndirmə profili (sahib 2026-11-22).

Sahib (RİM rəhbəri): «Dil fənlərində 10 bal sərbəst iş, 10 bal davamiyyət, 10 bal midterm. Midterm 10 balının
yazılması üçün xana da olmalıdır. Midterm balı köçürüləndə 10, finalda bunlar üçün 70 bal köçürüləcək».

Bu fənlər xarici dil SƏVİYYƏ fənlərinin (:mod:`core.language_level_rule`, 10 + 10 + 10 / 70) ALT DƏSTİDİR — midterm
tavanı 10, imtahan 70, 11-ci q/b qaydası, imtahan körpüləri olduğu kimi səviyyə qaydasından gəlir. Fərq yalnız:

* **Aktivlik (praktiki məşğələ ortası) YOXDUR** — onun 10 balı **sərbəst işdir** (mövcud sərbəst iş kodu:
  jurnalın «Sərbəst iş» tabı, fənn qovluğu, :mod:`apps.registrar.selfwork_points`; RİM-in ümumi
  ``academic.selfwork_enabled`` açarından asılı deyil — bu fənlərdə həmişə açıqdır);
* **Midterm xanası müəllimə açıqdır** — İmtahan Mərkəzinin pəncərəsi olmasa da müəllim 0–10 balı jurnalda yazır
  (digər jurnal ballarının redaktə müddəti ilə; açıq pəncərədə əvvəlki kimi pəncərə qaydası).

Qayda fənn ADINDAN çıxır (köçürülmüş fənlərdə kod sabit deyil). Yazı variantları: böyük/kiçik hərf, «ə/e», «ş/s»,
«ü/u», «İ/I/i», tire/boşluq, «və» / «akademik» sözləri olan və olmayan ad, kataloqdakı «(pre-intermadiate)» xətası.
Səviyyə yalnız dördüdür (Beginner / Elementary / Pre-intermediate / Intermediate); başqa səviyyə adı olan fənn
(«upper-intermediate», «A1» …) əvvəlki səviyyə qaydasında qalır.

RİM «Sistem tənzimləmələri»: ``academic.language_business_profile`` (defolt yanılı) — söndürüləndə bu fənlər yenə
adi səviyyə qaydası ilə (davamiyyət + praktiki məşğələ + midterm / 70) hesablanır. Bu modul ``apps``-dan heç nə
import etmir — registrar, fənn qovluğu və ``core.academic_rules`` eyni cavabı buradan oxuyur.
"""

from __future__ import annotations

import re

#: Profilin tavanları (cəm 100): sərbəst iş 10 + davamiyyət 10 + midterm 10 = 30, yekun imtahan 70.
SELFWORK_MAX = 10
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
    r"\( ?(?:beginner|elementary|pre ?-? ?interm[ae]diate|interm[ae]diate) ?\)$"
)


def fold(name) -> str:
    """Ad → müqayisə forması: Azərbaycan hərfləri ASCII-yə, kiçik hərf, tire variantları «-», tək boşluq."""
    text = str(name or "").translate(_FOLD).lower()
    return re.sub(r"\s+", " ", text).strip()


def is_business_name(name) -> bool:
    """Fənn adı «Xarici dildə işgüzar (və akademik) kommunikasiya -1/-2/-3 (dörd səviyyədən biri)»-dirmi."""
    return bool(BUSINESS_RE.match(fold(name)))


def profile_enabled() -> bool:
    """RİM açarı — söndürülübsə profil heç yerdə tətbiq olunmur (fənlər adi səviyyə qaydasına qayıdır)."""
    from core import runtime_settings

    return runtime_settings.get_bool(SETTING_KEY)


def applies_to_name(name) -> bool:
    """Ad + RİM açarı (dövr qapısı registrar-dadır — ``apps.registrar.language_business_grading.is_business``)."""
    return is_business_name(name) and profile_enabled()


def offering_subject_name(offering) -> str:
    subject = getattr(offering, "subject", None) if offering is not None else None
    return str(getattr(subject, "name", "") or "")


__all__ = [
    "ATTENDANCE_MAX",
    "BUSINESS_RE",
    "ENTRY_MAX",
    "EXAM_MAX",
    "MIDTERM_MAX",
    "SELFWORK_MAX",
    "SETTING_KEY",
    "applies_to_name",
    "fold",
    "is_business_name",
    "offering_subject_name",
    "profile_enabled",
]
