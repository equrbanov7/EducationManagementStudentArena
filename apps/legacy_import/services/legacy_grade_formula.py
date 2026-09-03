"""Köhnə MyEdu giriş-balının ayrıca, kanonik olmayan hesab müqaviləsi.

Bu modul istifadəçinin təqdim etdiyi əl-yazma qaydanı ifadə edir. Yeni EMSArena
qiymətləndirməsi bu funksiyanı çağırmır; qayda yalnız legacy məlumatı izah etmək
və mənbədə hazır ``yekun.girish`` olmadıqda bərpa namizədi yaratmaq üçündür.

Əl-yazmada üç fəaliyyət variantı var::

    seminar olan:       ((seminar orta + kollokvium orta) / 2) * 3
    lab + seminar olan: (((lab + seminar) orta + kollokvium orta) / 2) * 3
    seminarı olmayan:   ((lab orta + kollokvium orta) / 2) * 3

Sonra davamiyyət (maksimum 10) və sərbəst iş (maksimum 10) əlavə olunur.
Yuvarlaqlaşdırma şəkildə göstərilməyib. Ona görə əsas funksiya yuvarlaqlaşdırmır;
``round_legacy_score`` ayrıca, məlumatdan çıxarılan (rəsmi sənəddə olmayan)
``ROUND_HALF_UP`` ehtimalını tətbiq edir.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Iterable

ZERO = Decimal("0")
TEN = Decimal("10")
THREE = Decimal("3")
TWO = Decimal("2")
INTEGER_QUANTUM = Decimal("1")


class LegacyGradeFormulaInputError(ValueError):
    """Hesab üçün mənbə kateqoriyası çatmır və ya dəyər etibarsızdır."""


@dataclass(frozen=True)
class LegacyEntryCalculation:
    """İzah edilə bilən legacy hesab nəticəsi; heç bir clamp tətbiq edilmir."""

    activity_mode: str
    activity_average: Decimal
    colloquium_average: Decimal
    academic_part: Decimal
    attendance_score: Decimal
    self_work_score: Decimal
    total: Decimal


def _decimal(value: object, *, field: str) -> Decimal:
    if isinstance(value, bool):
        raise LegacyGradeFormulaInputError(f"legacy_grade_formula_{field}_invalid")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise LegacyGradeFormulaInputError(f"legacy_grade_formula_{field}_invalid") from None
    if not parsed.is_finite():
        raise LegacyGradeFormulaInputError(f"legacy_grade_formula_{field}_invalid")
    return parsed


def _scores(values: Iterable[object], *, field: str) -> tuple[Decimal, ...]:
    parsed = tuple(_decimal(value, field=field) for value in values)
    if any(value < ZERO or value > TEN for value in parsed):
        raise LegacyGradeFormulaInputError(f"legacy_grade_formula_{field}_out_of_range")
    return parsed


def _average(values: tuple[Decimal, ...]) -> Decimal:
    return sum(values, ZERO) / Decimal(len(values))


def calculate_legacy_entry_score(
    *,
    seminar_scores: Iterable[object] = (),
    lab_scores: Iterable[object] = (),
    colloquium_scores: Iterable[object],
    attendance_score: object,
    self_work_score: object,
) -> LegacyEntryCalculation:
    """Əl-yazma düsturunu hesabla, çatışmayan kateqoriyanı uydurma.

    Fəaliyyət üçün seminar, lab və ya onların birləşmiş çoxluğu; kollokvium üçün
    isə ən azı bir bal tələb olunur. Davamiyyət və sərbəst iş 0..10 aralığında
    olmalıdır. Nəticə qəsdən nə yuvarlaqlaşdırılır, nə də 0..50-yə sıxışdırılır.
    """

    seminar = _scores(seminar_scores, field="seminar")
    lab = _scores(lab_scores, field="lab")
    colloquium = _scores(colloquium_scores, field="colloquium")
    attendance = _decimal(attendance_score, field="attendance")
    self_work = _decimal(self_work_score, field="self_work")
    if not ZERO <= attendance <= TEN:
        raise LegacyGradeFormulaInputError("legacy_grade_formula_attendance_out_of_range")
    if not ZERO <= self_work <= TEN:
        raise LegacyGradeFormulaInputError("legacy_grade_formula_self_work_out_of_range")
    if not colloquium:
        raise LegacyGradeFormulaInputError("legacy_grade_formula_colloquium_missing")

    if seminar and lab:
        activity_mode = "lab_and_seminar"
        activity = seminar + lab
    elif seminar:
        activity_mode = "seminar"
        activity = seminar
    elif lab:
        activity_mode = "lab_without_seminar"
        activity = lab
    else:
        raise LegacyGradeFormulaInputError("legacy_grade_formula_activity_missing")

    activity_average = _average(activity)
    colloquium_average = _average(colloquium)
    academic_part = ((activity_average + colloquium_average) / TWO) * THREE
    total = academic_part + attendance + self_work
    return LegacyEntryCalculation(
        activity_mode=activity_mode,
        activity_average=activity_average,
        colloquium_average=colloquium_average,
        academic_part=academic_part,
        attendance_score=attendance,
        self_work_score=self_work,
        total=total,
    )


def round_legacy_score(value: object) -> Decimal:
    """Məlumatdan çıxarılan, rəsmi şəkildə göstərilməyən tam-bal yuvarlaqlaşdırması."""

    return _decimal(value, field="rounding").quantize(INTEGER_QUANTUM, rounding=ROUND_HALF_UP)


__all__ = [
    "LegacyEntryCalculation",
    "LegacyGradeFormulaInputError",
    "calculate_legacy_entry_score",
    "round_legacy_score",
]
