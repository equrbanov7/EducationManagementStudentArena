"""Sillabus siyahısı dözümlü axtarış (sahib 2026-09-26): az/ing hərfləri + şifr ayırıcıya dözümlü."""

from __future__ import annotations

import pytest

from apps.syllabus.tests.test_search_by_program_code import CURRENT_CODE, _draft, _list_codes, world  # noqa: F401

pytestmark = pytest.mark.django_db


def test_programme_name_is_found_with_an_english_keyboard(world):  # noqa: F811
    _draft(world)
    for query in ("Dunya iqtisadiyyati", "DÜNYA", "dunya iqtis"):
        assert _list_codes(world, query).count() == 1, query


def test_programme_code_is_found_with_separators(world):  # noqa: F811
    _draft(world)
    spaced = f"{CURRENT_CODE[:4]} {CURRENT_CODE[4:]}"
    assert _list_codes(world, spaced).count() == 1
    assert _list_codes(world, f"{CURRENT_CODE[:4]}-{CURRENT_CODE[4:]}").count() == 1


def test_unrelated_name_matches_nothing(world):  # noqa: F811
    _draft(world)
    assert _list_codes(world, "Kimya").count() == 0
