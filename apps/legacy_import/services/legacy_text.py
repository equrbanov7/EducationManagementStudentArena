"""Deterministic text/code normalisation for legacy structure sources.

The legacy dump carries HTML-escaped Azerbaijani names (``&amp;#601;`` double
encodings), trailing ``\\t`` pollution inside ``speciality_code`` and NBSP-padded
labels.  Cleaning happens on the way to a TARGET field only: ``source_row_hash``
keeps digesting the raw projected value through ``stable_source_value``, so a
change to a cleaning rule can never rewrite the evidence of what the source
actually contained.  Everything here is a pure function of its input.

TWO cleaners, because a line break is not always noise
======================================================
``clean_text`` flattens EVERY separator — a name, a room label or a weekly topic
is a single line by construction, so a stray newline there is dump pollution.

``clean_multiline_text`` keeps line breaks and normalises only what sits INSIDE
a line.  Free-form syllabus prose needs it: the legacy editor stored a whole
numbered literature list in ONE ``text`` column with ``\\r\\n`` between the
entries, and the reader downstream (``apps.syllabus.document._lines``) splits on
``"\\n"``.  Flattening such a column is a SILENT structural loss — the row still
looks complete, ``truncated`` stays ``False``, no issue code is raised, and the
student is shown one run-on paragraph instead of N literature entries.

Live measurement (2026-08-30, ``emsarena-legacy-source-rehearsal``) — rows whose
``name`` carries a line break, per satellite table::

    sillabus_yoxlama_formasi           4,842 / 8,261
    sillabus_eldeolunacaq_tecrubeler   4,791 / 8,261
    sillabus_tesviri_ve_meqsedi        4,652 / 6,491
    sillabus_dersin_islenme_formasi    4,574 / 8,261
    sillabus_derslikler                2,508 / 16,476
    sillabus_qarsilama_mesaji          1,724 / 4,676
    sillabus_elmi_maraq                  483 / 10,739
    sillabus_serbest_is / _imtahan_suallari / _certificates    0
    sillabus_sem_muh.movzu · .qeyd                            0 / 131,056

23,574 rows in total.  ``movzu`` carrying ZERO line breaks is why J11 could use
``clean_text`` there and why it KEEPS using it: the two cleaners agree on every
single-line value, so the split is a widening, not a behaviour change.
"""

from __future__ import annotations

import html
import unicodedata
from collections.abc import Mapping

from .rehearsal_contracts import LegacyRehearsalEvidenceError, canonical_json_digest

MAX_ENTITY_UNESCAPE_PASSES = 3
LEGACY_SLUG_KINDS = frozenset({"dep", "spec", "grp"})
MAX_LEGACY_SLUG_LENGTH = 255
# Cc/Cf control plus Zs/Zl/Zp separator: a tab, a CRLF and an NBSP therefore all
# collapse to the identical single U+0020 run.
_BLANK_CATEGORIES = frozenset({"Cc", "Cf", "Zs", "Zl", "Zp"})
_TYPE_INVALID = "legacy_structure_source_value_type_invalid"


def _validated_max_length(max_length: object) -> int:
    if type(max_length) is not int or max_length < 1:
        raise LegacyRehearsalEvidenceError(_TYPE_INVALID)
    return max_length


def _decoded(value: object) -> str:
    """Entity-unescape to a fixed point, then NFC.  Shared by both cleaners.

    ``None`` is the only accepted non-``str`` input: a ``bytes`` column would be
    a driver misconfiguration, so it fails closed instead of being coerced.
    """

    if value is None:
        return ""
    if type(value) is not str:
        raise LegacyRehearsalEvidenceError(_TYPE_INVALID)
    text = value
    for _attempt in range(MAX_ENTITY_UNESCAPE_PASSES):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    return unicodedata.normalize("NFC", text)


def _blanked(text: str) -> str:
    """Every control/separator character becomes one plain space."""

    return "".join(" " if unicodedata.category(char) in _BLANK_CATEGORIES else char for char in text)


def _collapsed_blank_lines(lines: list[str]) -> list[str]:
    """Drop leading/trailing empties and squeeze every blank run to ONE line.

    A blank line is a paragraph break the teacher typed; three of them are the
    old editor's ``\r\n\r\n\r\n`` padding (528 rows in ``sillabus_derslikler``
    alone).  Keeping one preserves the intent without preserving the noise, and
    makes the function idempotent — re-cleaning its own output is a no-op.
    """

    kept: list[str] = []
    for line in lines:
        if line:
            kept.append(line)
        elif kept and kept[-1]:
            kept.append("")
    while kept and not kept[-1]:
        kept.pop()
    return kept


def clean_text(value: object, *, max_length: int) -> tuple[str, bool]:
    """Return ``(cleaned, truncated)`` for one legacy SINGLE-LINE value.

    Every separator — tab, CRLF, NBSP — collapses into one space.  Use
    ``clean_multiline_text`` when the column holds free-form prose whose line
    breaks are content.
    """

    limit = _validated_max_length(max_length)
    text = " ".join(_blanked(_decoded(value)).split())
    return text[:limit], len(text) > limit


def clean_multiline_text(value: object, *, max_length: int) -> tuple[str, bool]:
    """``clean_text`` for free-form prose: LINE BREAKS SURVIVE.

    ``str.splitlines`` owns the line-break vocabulary, so ``\r\n``, a bare
    ``\r``, ``\x0b``/``\x0c``, ``\x85`` and U+2028/U+2029 all become one
    ``"\n"`` — the separator ``apps.syllabus.document._lines`` splits on.
    Everything INSIDE a line is collapsed exactly as ``clean_text`` does (the
    legacy list markers are ``"1.\t"``, so the tab must still become a space).

    The two cleaners return the identical string for any value without a line
    break, which is what lets J11's ``movzu`` keep the flat cleaner.
    """

    limit = _validated_max_length(max_length)
    lines = [" ".join(_blanked(line).split()) for line in _decoded(value).splitlines()]
    text = "\n".join(_collapsed_blank_lines(lines))
    return text[:limit], len(text) > limit


def clean_code(value: object, *, max_length: int) -> tuple[str, bool]:
    """``clean_text`` plus total whitespace removal and upper-casing."""

    text, truncated = clean_text(value, max_length=max_length)
    text = "".join(text.split()).upper()
    if len(text) > max_length:
        # Upper-casing can expand (``ß`` → ``SS``); the clamp is what callers
        # rely on when they append a ``-M`` suffix inside a 32-char column.
        return text[:max_length], True
    return text, truncated


def legacy_slug(kind: str, legacy_pk: int) -> str:
    """Legacy-keyed ASCII slug; name-derived slugs collide and drop ``ə``."""

    if kind not in LEGACY_SLUG_KINDS or type(legacy_pk) is not int or legacy_pk < 1:
        raise LegacyRehearsalEvidenceError(_TYPE_INVALID)
    slug = f"myedu-{kind}-{legacy_pk}"
    if len(slug) > MAX_LEGACY_SLUG_LENGTH:
        raise LegacyRehearsalEvidenceError(_TYPE_INVALID)
    return slug


def canonical_settings_digest(settings: Mapping[str, object]) -> str:
    """Digest one ``OrgUnit.settings`` payload for a target digest chain."""

    if not isinstance(settings, Mapping):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_digest_payload_invalid")
    return canonical_json_digest(settings)


__all__ = [
    "MAX_ENTITY_UNESCAPE_PASSES",
    "canonical_settings_digest",
    "clean_code",
    "clean_multiline_text",
    "clean_text",
    "legacy_slug",
]
