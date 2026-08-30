"""Legacy demoqrafiya çevrilmələri (``sex``/``birthday`` → profil sütunları).

Buradakı hər halın forması REAL MariaDB dump-ından götürülüb: ``DD/MM/YYYY``
üstünlük təşkil edir, amma ISO ``YYYY-MM-DD``, ``DD-MM-YYYY``, ``DD.MM.YYYY``,
kəsik ``20/05/79__`` və "sətrin yaradılma tarixi" sızması (``2026-02-17``) də
mövcuddur.  Testlərin çoxu təmiz funksiya testidir — baza tələb olunmur.
"""

import datetime

import pytest

from apps.accounts.models import UserProfile
from apps.legacy_import.services.legacy_demographics import (
    GENDER_FEMALE,
    GENDER_MALE,
    GENDER_UNSPECIFIED,
    KNOWN_SEX_CODES,
    MAX_PLAUSIBLE_AGE,
    MIN_PLAUSIBLE_AGE,
    Demographics,
    demographics_from_row,
    legacy_birth_date,
    legacy_gender,
)
from apps.legacy_import.services.rehearsal_contracts import LegacyRehearsalEvidenceError

_TYPE_INVALID = "legacy_demographics_source_value_type_invalid"
_TODAY = datetime.date(2026, 8, 30)


# ---------------------------------------------------------------------------
# Cins uyğunlaşması
# ---------------------------------------------------------------------------


def test_gender_tokens_match_the_profile_model():
    """Modul model importuna bağlanmır — bu qapı sətirlərin eyniliyini saxlayır."""

    assert GENDER_UNSPECIFIED == UserProfile.Gender.UNSPECIFIED.value
    assert GENDER_MALE == UserProfile.Gender.MALE.value
    assert GENDER_FEMALE == UserProfile.Gender.FEMALE.value


@pytest.mark.parametrize(
    ("code", "expected"),
    [(0, GENDER_UNSPECIFIED), (1, GENDER_MALE), (2, GENDER_FEMALE), (None, GENDER_UNSPECIFIED)],
)
def test_legacy_sex_codes_map_as_measured_in_the_source(code, expected):
    """1=kişi, 2=qadın — mənbədə ad histoqramı ilə təsdiqlənib (0 % çarpaz)."""

    assert legacy_gender(code) == expected


def test_the_known_sex_codes_are_exactly_the_ones_the_dump_contains():
    assert KNOWN_SEX_CODES == {0, 1, 2}


def test_an_unconfirmed_sex_code_asserts_nothing_instead_of_guessing():
    """Naməlum kod nə run çökdürür, nə də cins uydurur: sentinel qalır."""

    assert legacy_gender(3) == GENDER_UNSPECIFIED
    assert legacy_gender(-1) == GENDER_UNSPECIFIED


@pytest.mark.parametrize("value", ["1", b"1", 1.0, True, [1]])
def test_legacy_gender_refuses_non_integer_columns(value):
    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        legacy_gender(value)

    assert exc_info.value.code == _TYPE_INVALID


# ---------------------------------------------------------------------------
# Doğum tarixi
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("19/10/2003", datetime.date(2003, 10, 19)),
        ("2007-07-09", datetime.date(2007, 7, 9)),
        ("16-01-1988", datetime.date(1988, 1, 16)),
        ("13.05.1970", datetime.date(1970, 5, 13)),
        ("  08/07/2001  ", datetime.date(2001, 7, 8)),
    ],
)
def test_every_shape_the_dump_actually_contains_parses(raw, expected):
    assert legacy_birth_date(raw, today=_TODAY) == expected


@pytest.mark.parametrize("raw", ["", "   ", "0", "20/05/79__", "0_/__/____", "20/04/____", "13.05.70"])
def test_blank_and_truncated_values_fail_closed_to_null(raw):
    assert legacy_birth_date(raw, today=_TODAY) is None


def test_a_month_day_swap_is_refused_rather_than_repaired():
    """``12/16/2001`` yalnız MM/DD kimi oxuna bilər — amma onu qəbul etmək
    ``07/08/2022``-ni necə oxumaq lazım olduğuna dair təxminə çevrilərdi."""

    assert legacy_birth_date("12/16/2001", today=_TODAY) is None
    assert legacy_birth_date("07/30/1990", today=_TODAY) is None


def test_mixed_separators_are_not_a_date():
    assert legacy_birth_date("19/10-2003", today=_TODAY) is None


@pytest.mark.parametrize("raw", ["17/07/1487", "05/05/1555", "01/01/1891", "2026-02-17", "22/07/2023"])
def test_implausible_years_are_rejected(raw):
    """Yazı səhvləri və "sətir bu gün yaradılıb" sızması pəncərədən kənardır."""

    assert legacy_birth_date(raw, today=_TODAY) is None


def test_the_plausible_window_edges_are_inclusive():
    floor = datetime.date(_TODAY.year - MAX_PLAUSIBLE_AGE, 1, 1)
    ceiling = datetime.date(_TODAY.year - MIN_PLAUSIBLE_AGE, 12, 31)

    assert legacy_birth_date(floor.strftime("%d/%m/%Y"), today=_TODAY) == floor
    assert legacy_birth_date(ceiling.strftime("%d/%m/%Y"), today=_TODAY) == ceiling
    assert legacy_birth_date((floor - datetime.timedelta(days=1)).strftime("%d/%m/%Y"), today=_TODAY) is None
    assert legacy_birth_date((ceiling + datetime.timedelta(days=1)).strftime("%d/%m/%Y"), today=_TODAY) is None


def test_a_driver_returning_dates_is_accepted_unchanged():
    """Sürücü konfiqurasiyası dəyişib ``date`` qaytarsa forma yenə tanınır."""

    assert legacy_birth_date(datetime.date(2003, 10, 19), today=_TODAY) == datetime.date(2003, 10, 19)
    assert legacy_birth_date(datetime.datetime(2003, 10, 19, 7, 30), today=_TODAY) == datetime.date(2003, 10, 19)


@pytest.mark.parametrize("value", [b"19/10/2003", 20031019, 2003.0])
def test_legacy_birth_date_refuses_unsupported_column_types(value):
    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        legacy_birth_date(value, today=_TODAY)

    assert exc_info.value.code == _TYPE_INVALID


# ---------------------------------------------------------------------------
# Sətir → Demographics
# ---------------------------------------------------------------------------


def test_demographics_from_row_reads_the_existing_projection():
    row = {"sex": 2, "birthday": "19/10/2003"}

    assert demographics_from_row(row) == Demographics(
        gender=GENDER_FEMALE, birth_date=datetime.date(2003, 10, 19)
    )


def test_a_row_with_neither_field_is_blank():
    assert demographics_from_row({"sex": 0, "birthday": ""}).is_blank


def test_a_half_filled_row_is_not_blank():
    """Mənbədə cins 21 %, doğum tarixi 28 % doludur — yarımçıq sətir normadır."""

    assert not demographics_from_row({"sex": 1, "birthday": ""}).is_blank
    assert not demographics_from_row({"sex": 0, "birthday": "19/10/2003"}).is_blank
