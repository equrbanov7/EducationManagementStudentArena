from decimal import Decimal

import pytest

from apps.legacy_import.services.legacy_grade_formula import (
    LegacyGradeFormulaInputError,
    calculate_legacy_entry_score,
    round_legacy_score,
)


def test_seminar_formula_matches_handwritten_contract():
    result = calculate_legacy_entry_score(
        seminar_scores=(8, 10),
        colloquium_scores=(7, 9),
        attendance_score=10,
        self_work_score=9,
    )

    assert result.activity_mode == "seminar"
    assert result.activity_average == Decimal("9")
    assert result.colloquium_average == Decimal("8")
    assert result.academic_part == Decimal("25.5")
    assert result.total == Decimal("44.5")


def test_lab_and_seminar_use_one_combined_activity_average():
    result = calculate_legacy_entry_score(
        seminar_scores=(8, 10),
        lab_scores=(6, 8),
        colloquium_scores=(7, 9),
        attendance_score=10,
        self_work_score=10,
    )

    assert result.activity_mode == "lab_and_seminar"
    assert result.activity_average == Decimal("8")
    assert result.total == Decimal("44")


def test_lab_without_seminar_uses_third_handwritten_variant():
    result = calculate_legacy_entry_score(
        lab_scores=(8, 10),
        colloquium_scores=(7, 9),
        attendance_score=9,
        self_work_score=8,
    )

    assert result.activity_mode == "lab_without_seminar"
    assert result.total == Decimal("42.5")


def test_formula_fails_closed_when_required_category_is_missing():
    with pytest.raises(LegacyGradeFormulaInputError, match="activity_missing"):
        calculate_legacy_entry_score(
            colloquium_scores=(8,),
            attendance_score=10,
            self_work_score=10,
        )

    with pytest.raises(LegacyGradeFormulaInputError, match="colloquium_missing"):
        calculate_legacy_entry_score(
            seminar_scores=(8,),
            colloquium_scores=(),
            attendance_score=10,
            self_work_score=10,
        )


def test_formula_does_not_clamp_and_rounding_is_explicit_half_up_inference():
    result = calculate_legacy_entry_score(
        seminar_scores=(10,),
        colloquium_scores=(10,),
        attendance_score=10,
        self_work_score=10,
    )

    assert result.total == Decimal("50")
    assert round_legacy_score("44.5") == Decimal("45")


@pytest.mark.parametrize("field", ("attendance_score", "self_work_score"))
def test_additive_components_are_limited_to_ten(field):
    kwargs = {
        "seminar_scores": (8,),
        "colloquium_scores": (8,),
        "attendance_score": 10,
        "self_work_score": 10,
    }
    kwargs[field] = 11

    with pytest.raises(LegacyGradeFormulaInputError, match="out_of_range"):
        calculate_legacy_entry_score(**kwargs)
