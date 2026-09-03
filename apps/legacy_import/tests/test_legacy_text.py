"""Legacy text/code normalisation (SPEC §3.5).

Pure functions only: no database, no Django settings, no source connection.
Every case here is a shape the real MariaDB dump actually contains — double
HTML-escaped Azerbaijani letters, ``\\t``-polluted ``speciality_code`` values,
NBSP padding and CRLF line breaks inside a department name.
"""

import pytest

from apps.legacy_import.services.legacy_text import (
    MAX_ENTITY_UNESCAPE_PASSES,
    canonical_settings_digest,
    clean_code,
    clean_multiline_text,
    clean_text,
    legacy_slug,
)
from apps.legacy_import.services.rehearsal_contracts import LegacyRehearsalEvidenceError, canonical_json_digest

_TYPE_INVALID = "legacy_structure_source_value_type_invalid"


# ---------------------------------------------------------------------------
# clean_text
# ---------------------------------------------------------------------------


def test_clean_text_accepts_none_as_the_only_non_string():
    assert clean_text(None, max_length=255) == ("", False)


@pytest.mark.parametrize("value", [b"Kollec", bytearray(b"Kollec"), 7, 7.0, True, ["Kollec"]])
def test_clean_text_refuses_every_other_type(value):
    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        clean_text(value, max_length=255)

    assert exc_info.value.code == _TYPE_INVALID


def test_clean_text_unescapes_double_encoded_entities_to_a_fixed_point():
    # "&amp;#601;" needs two passes: &amp; → & first, then &#601; → ə.
    assert clean_text("M&amp;#601;kt&amp;#601;b", max_length=255) == ("Məktəb", False)
    assert clean_text("&amp;amp;#601;", max_length=255) == ("ə", False)


def test_clean_text_unescape_is_bounded_by_the_pass_cap():
    # Four levels of escaping cannot fully resolve in three passes; the result
    # is deterministic rather than "keep unescaping until something stops".
    assert MAX_ENTITY_UNESCAPE_PASSES == 3
    over_escaped = "&amp;amp;amp;#601;"

    cleaned, truncated = clean_text(over_escaped, max_length=255)

    assert cleaned == "&#601;"
    assert truncated is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("İnformasiya\ttexnologiyaları", "İnformasiya texnologiyaları"),
        ("Kollec\r\nİkinci", "Kollec İkinci"),
        (" Kafedra  adı ", "Kafedra adı"),
        ("  Bölmə   3  ", "Bölmə 3"),
        ("Zero\u200bwidth", "Zero width"),  # U+200B (Cf) becomes one space
        ("Qrup\xa0101", "Qrup 101"),  # NBSP (Zs) is collapsed, not stripped
    ],
)
def test_clean_text_collapses_every_control_and_separator_run(raw, expected):
    assert clean_text(raw, max_length=255) == (expected, False)


def test_clean_text_normalises_to_nfc_and_is_idempotent():
    decomposed = "U\u0308mumi"  # "U" + COMBINING DIAERESIS: 6 code points

    cleaned, truncated = clean_text(decomposed, max_length=255)

    assert cleaned == "\u00dcmumi"
    assert len(cleaned) == 5 and truncated is False
    # A second pass over an already-cleaned value must be a no-op.
    assert clean_text(cleaned, max_length=255) == (cleaned, False)


def test_clean_text_reports_and_applies_truncation():
    assert clean_text("Kimya fakültəsi", max_length=5) == ("Kimya", True)
    assert clean_text("Kimya", max_length=5) == ("Kimya", False)
    # The flag is derived AFTER collapsing, so padding alone never truncates.
    assert clean_text("   Kimya   ", max_length=5) == ("Kimya", False)


@pytest.mark.parametrize("max_length", [0, -1, "255", 255.0, None, True])
def test_clean_text_refuses_an_invalid_max_length(max_length):
    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        clean_text("Kollec", max_length=max_length)

    assert exc_info.value.code == _TYPE_INVALID


# ---------------------------------------------------------------------------
# clean_multiline_text
# ---------------------------------------------------------------------------

#: One real ``sillabus_derslikler.name`` shape: the whole numbered literature
#: list lives in ONE column, ``1.`` + TAB, entries separated by CRLF.  Live
#: measurement (2026-08-30): 2,508 / 16,476 rows in that table carry a line
#: break, 23,574 rows across the eleven syllabus satellites.
_LITERATURE_COLUMN = (
    "1.\tSpeak Out, Pre-Intermediate, Students&rsquo; Book\r\n"
    "2.\tBasic English Grammar, 4th Edition\r\n"
    "3.\tİngilis dili &uuml;zr&#601; praktikum"
)


def test_clean_multiline_text_keeps_the_line_structure_a_list_is_made_of():
    cleaned, truncated = clean_multiline_text(_LITERATURE_COLUMN, max_length=65_535)

    assert truncated is False
    assert cleaned.split("\n") == [
        "1. Speak Out, Pre-Intermediate, Students\u2019 Book",
        "2. Basic English Grammar, 4th Edition",
        "3. İngilis dili üzrə praktikum",
    ]
    # The flat cleaner is exactly the silent damage this function exists to stop:
    # three entries become one paragraph, with no truncation and no issue code.
    flat, flat_truncated = clean_text(_LITERATURE_COLUMN, max_length=65_535)
    assert "\n" not in flat and flat_truncated is False


@pytest.mark.parametrize(
    "raw",
    [
        "Kimya fakültəsi",
        "  İnformasiya\ttexnologiyaları  ",
        "M&amp;#601;kt&amp;#601;b",
        "Qrup\xa0101",
        "",
        None,
    ],
)
def test_clean_multiline_text_agrees_with_clean_text_on_single_line_values(raw):
    """Bölünmə GENİŞLƏNMƏDİR: sətir sonu olmayan dəyərdə iki funksiya eynidir.

    J11 ``movzu``-nu ``clean_text``-də saxlayır (131,056 sətrin heç birində
    sətir sonu yoxdur); bu bərabərlik həmin qərarın davranış dəyişikliyi
    OLMADIĞINI kilidləyir.
    """
    assert clean_multiline_text(raw, max_length=255) == clean_text(raw, max_length=255)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # CRLF, lone CR and the Unicode line separators all become one "\n".
        ("a\r\nb", "a\nb"),
        ("a\rb", "a\nb"),
        ("a\u2028b", "a\nb"),
        ("a\u2029b", "a\nb"),
        ("a\x0bb", "a\nb"),
        # Blank-line runs collapse to ONE (the old editor padded with \r\n\r\n\r\n).
        ("a\r\n\r\n\r\nb", "a\n\nb"),
        # Leading/trailing blank lines are dropped entirely.
        ("\r\n\r\n  a  \r\n  \r\n", "a"),
        # Inside a line nothing changes: tabs and NBSP still collapse to a space.
        ("a\tb\r\nc\xa0\xa0d", "a b\nc d"),
    ],
)
def test_clean_multiline_text_normalises_breaks_without_erasing_them(raw, expected):
    assert clean_multiline_text(raw, max_length=255) == (expected, False)


def test_clean_multiline_text_is_idempotent_and_reports_truncation():
    cleaned, _truncated = clean_multiline_text(_LITERATURE_COLUMN, max_length=65_535)
    assert clean_multiline_text(cleaned, max_length=65_535) == (cleaned, False)
    assert clean_multiline_text("Kimya\r\nfizika", max_length=5) == ("Kimya", True)


@pytest.mark.parametrize("value", [b"Kollec", 7, 7.0, ["Kollec"]])
def test_clean_multiline_text_refuses_every_non_string_but_none(value):
    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        clean_multiline_text(value, max_length=255)

    assert exc_info.value.code == _TYPE_INVALID


# ---------------------------------------------------------------------------
# clean_code
# ---------------------------------------------------------------------------


def test_clean_code_strips_the_trailing_tab_pollution_and_upper_cases():
    assert clean_code("050632\t", max_length=50) == ("050632", False)
    assert clean_code(" 05 06 32 ", max_length=50) == ("050632", False)
    assert clean_code("ti-b", max_length=50) == ("TI-B", False)


def test_clean_code_treats_blank_and_none_alike():
    assert clean_code("", max_length=30) == ("", False)
    assert clean_code("\t\r\n ", max_length=30) == ("", False)
    assert clean_code(None, max_length=30) == ("", False)


def test_clean_code_never_exceeds_max_length_even_when_upper_casing_expands():
    # "ß".upper() is "SS": the clamp is what keeps a base code inside the 30
    # characters a "-M" suffix needs to stay within Program.code's 32.
    cleaned, truncated = clean_code("ß" * 20, max_length=30)

    assert cleaned == "S" * 30
    assert truncated is True


def test_clean_code_refuses_a_non_string():
    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        clean_code(b"050632", max_length=50)

    assert exc_info.value.code == _TYPE_INVALID


# ---------------------------------------------------------------------------
# legacy_slug
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "legacy_pk", "expected"),
    [("dep", 1, "myedu-dep-1"), ("spec", 83, "myedu-spec-83"), ("grp", 766, "myedu-grp-766")],
)
def test_legacy_slug_is_ascii_and_legacy_keyed(kind, legacy_pk, expected):
    slug = legacy_slug(kind, legacy_pk)

    assert slug == expected
    assert slug.isascii() and len(slug) <= 255


def test_legacy_slug_separates_two_identically_named_units():
    # Two departments are both literally named "Kollec"; a name-derived slug
    # would collide on the OrgUnit (organization, slug) unique constraint.
    assert legacy_slug("dep", 4) != legacy_slug("dep", 9)


@pytest.mark.parametrize(
    ("kind", "legacy_pk"),
    [
        ("faculty", 1),
        ("", 1),
        ("DEP", 1),
        ("dep", 0),
        ("dep", -3),
        ("dep", "1"),
        ("dep", 1.0),
        ("dep", True),
        ("dep", None),
    ],
)
def test_legacy_slug_fails_closed_on_an_invalid_key(kind, legacy_pk):
    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        legacy_slug(kind, legacy_pk)

    assert exc_info.value.code == _TYPE_INVALID


# ---------------------------------------------------------------------------
# canonical_settings_digest
# ---------------------------------------------------------------------------


def test_canonical_settings_digest_is_key_order_independent():
    left = {"education_form": "full_time", "legacy": {"id": 7, "table": "groups"}, "sector": "az"}
    right = {"sector": "az", "legacy": {"table": "groups", "id": 7}, "education_form": "full_time"}

    assert canonical_settings_digest(left) == canonical_settings_digest(right)
    assert canonical_settings_digest(left) == canonical_json_digest(left)
    assert len(canonical_settings_digest(left)) == 64


def test_canonical_settings_digest_separates_a_null_admission_year_from_a_zero():
    assert canonical_settings_digest({"admission_year": None}) != canonical_settings_digest({"admission_year": 0})


@pytest.mark.parametrize("payload", [None, "settings", [("sector", "az")], 7])
def test_canonical_settings_digest_refuses_a_non_mapping(payload):
    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        canonical_settings_digest(payload)

    assert exc_info.value.code == "legacy_rehearsal_digest_payload_invalid"
