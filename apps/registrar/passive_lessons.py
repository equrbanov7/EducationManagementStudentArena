"""«Passiv» dərs — dərs saatı seçilərkən «Passiv» (sahib 2026-11-14).

Sahib: «solda qutu kimi “İntensiv tədris: passiv saat”ı yığışdır. Passiv saat dərs saatı seçilərkən götürülsün:
1, 2, və altında “Passiv” olsun; onu seçəndə passiv kimi düşsün — bu müəllimin saat hesabında, keçdiyi dərslərdə
hesablanmır, nəzərə alınmır. Keçilmiş dərslərə baxanda da görünsün, toplananda çıxsın (ayrıca). Jurnalda həmin
column bir rəngdə olsun, bilinsin ki elədir.»

ƏVVƏL (2026-11-12, MR-000303): jurnal başlığında ayrıca «Passiv saat» qutusu (``PassiveHour`` sətri: tarix + saat +
qeyd); adi jurnalda kafedra müdiri / RİM «İntensiv tədris: passiv saat» açarı ilə açırdı. Qutu yığışdırıldı, köhnə
sətirlər miqrasiya ``0124`` ilə passiv DƏRSƏ çevrildi (cədvəl arxiv kimi qalır, heç kim oxumur).

QAYDALAR
────────
* Saxlama: ``Lesson.is_passive`` + adi ``hours`` (göstəriş və ayrıca cəm üçün). Modalda «SAAT» seçimi ``1..2``
  (sahib 2026-11-15; köhnə 3–4 yalnız redaktədə) və
  altında «Passiv · N» (POST dəyəri ``p<N>``, :func:`parse_hours_choice`).
* Kim: dərs aça / redaktə edə bilən hər kəs, HƏR jurnalda (açar yığışdırıldı — sahib «dərs saatı seçilərkən»).
  İstisna: dil səviyyə kohortu (``LanguageLevelCohort`` — kontakt saatı DB trigger-i ilə qorunur).
* Passiv dərs DƏRS SAYILMIR: «Keçirilmiş X / Y», fənnin saat həddi (#6), qayıb məxrəci (``lesson_hours_for``
  fallback-i), mühasibat / dərs yükü / kabinet «keçirilmiş saat»ı, «Keçilmiş dərslər» əsas cəmi.
* Xana YAZILMIR (köhnə qutu kimi — davamiyyət / bal yoxdur): qrid xanası boz-kəhrəba «P», toplu i/e — q/b yoxdur,
  server ``save_marks`` / sənədli düzəliş passiv dərsi tapmır. Qeydi olan dərs passiv edilə bilməz.
* Görünür: jurnal sütunu rənglidir (``is-passive``), başlıqda «Passiv: N saat», «Keçilmiş dərslər»də nişan və
  ayrıca cəm, CSV / XLSX ixracında «Passiv» sütunu.
"""

from __future__ import annotations

from django.db.models import Q
from django.utils.translation import pgettext

_CTX = "registrar.passive_lessons"

#: Modalın «SAAT» seçimində passiv variantın prefiksi (``p2`` = passiv, 2 saat).
PREFIX = "p"


def counted_q(prefix: str = "") -> Q:
    """Sayılan (passiv OLMAYAN) dərslər; ``prefix`` əlaqə yolu üçün (``lesson__``)."""
    return Q(**{f"{prefix}is_passive": False})


def passive_q(prefix: str = "") -> Q:
    return Q(**{f"{prefix}is_passive": True})


def is_passive(lesson) -> bool:
    """Obyekt / ``SimpleNamespace`` üçün (``only()`` sorğusunda sahə yüklənməlidir — əks halda sətir başına sorğu)."""
    return bool(getattr(lesson, "is_passive", False))


def counted(lessons) -> list:
    return [lesson for lesson in lessons if not is_passive(lesson)]


def passive_hours(lessons) -> int:
    return sum(int(getattr(lesson, "hours", 0) or 0) for lesson in lessons if is_passive(lesson))


def available(offering) -> bool:
    """Bu jurnalda «Passiv» seçilə bilərmi (dil səviyyə kohortundan başqa hamısında)."""
    if offering is None or not getattr(offering, "pk", None):
        return False
    from .models import LanguageLevelCohort

    return not LanguageLevelCohort.objects.filter(offering_id=offering.pk).exists()


def parse_hours_choice(raw) -> tuple[int | None, bool, bool]:
    """POST ``lesson_hours`` → ``(saat | None, passiv, düzgün)``. Boş dəyər = standart saat (``None``, adi dərs)."""
    value = str(raw or "").strip().lower()
    passive = value.startswith(PREFIX)
    if passive:
        value = value[len(PREFIX) :]
    if not value:
        return None, passive, not passive  # «p» tək başına yanlışdır
    if not value.isdigit() or int(value) <= 0:
        return None, passive, False
    return int(value), passive, True


def not_available_message() -> str:
    return pgettext(_CTX, "Bu jurnalda passiv dərs açmaq olmaz (dil səviyyə qrupunun saatı sabitdir).")


def has_marks_message() -> str:
    return pgettext(_CTX, "Bu dərsdə qeyd (i/e, q/b, bal) var — passiv edilə bilməz. Əvvəl qeydləri təmizləyin.")


def locked_message() -> str:
    return pgettext(_CTX, "Dərsin «Passiv» seçimi yalnız redaktə pəncərəsində dəyişir — sənədli düzəlişdə dəyişmir.")


def ensure_can_switch(lesson, passive: bool) -> None:
    """Dərsi passiv etmək: jurnalda icazə olmalı və dərsin qeydi olmamalıdır (passiv dərsdə xana yoxdur)."""
    from .gradebook import LessonRuleError

    if not passive or is_passive(lesson):
        return
    if not available(lesson.offering):
        raise LessonRuleError(not_available_message())
    if lesson.marks.exists():
        raise LessonRuleError(has_marks_message())


def grid_cell(lesson, mark) -> dict:
    """Qridin passiv xanası: yazılmır, kilid dialoqu yoxdur (``gradebook.get_journal``)."""
    return {
        "lesson": lesson,
        "mark": mark,
        "allows_score": False,
        "locked": True,
        "lock_reason": "",
        "corrected": False,
        "writable": False,
        "passive": True,
    }


def label() -> str:
    return pgettext(_CTX, "Passiv")


def hours_note(hours: int) -> str:
    """«Passiv: N saat» — cəmlərin yanında (əsas cəmə daxil deyil)."""
    return pgettext(_CTX, "Passiv: %(hours)s saat") % {"hours": int(hours or 0)}


__all__ = [
    "PREFIX",
    "available",
    "counted",
    "counted_q",
    "ensure_can_switch",
    "grid_cell",
    "has_marks_message",
    "hours_note",
    "is_passive",
    "label",
    "locked_message",
    "not_available_message",
    "parse_hours_choice",
    "passive_hours",
    "passive_q",
]
