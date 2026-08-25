"""Deterministic text/code normalisation for legacy structure sources.

The legacy dump carries HTML-escaped Azerbaijani names (``&amp;#601;`` double
encodings), trailing ``\\t`` pollution inside ``speciality_code`` and NBSP-padded
labels.  Cleaning happens on the way to a TARGET field only: ``source_row_hash``
keeps digesting the raw projected value through ``stable_source_value``, so a
change to a cleaning rule can never rewrite the evidence of what the source
actually contained.  Everything here is a pure function of its input.
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


def clean_text(value: object, *, max_length: int) -> tuple[str, bool]:
    """Return ``(cleaned, truncated)`` for one legacy free-text value.

    ``None`` is the only accepted non-``str`` input: a ``bytes`` column would be
    a driver misconfiguration, so it fails closed instead of being coerced.
    """

    limit = _validated_max_length(max_length)
    if value is None:
        return "", False
    if type(value) is not str:
        raise LegacyRehearsalEvidenceError(_TYPE_INVALID)
    text = value
    for _attempt in range(MAX_ENTITY_UNESCAPE_PASSES):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    text = unicodedata.normalize("NFC", text)
    text = "".join(" " if unicodedata.category(char) in _BLANK_CATEGORIES else char for char in text)
    text = " ".join(text.split())
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
    "clean_text",
    "legacy_slug",
]
