"""Language counterevidence for group presentation, never a metadata repair.

Only explicit terminal language tags are read from a name. They can block a
contradiction, but cannot supply missing structured language evidence.
"""

import re
import unicodedata

ALIASES = {
    "az": "az",
    "aze": "az",
    "azərbaycan": "az",
    "azərbaycan dili": "az",
    "azerbaijani": "az",
    "en": "en",
    "eng": "en",
    "ing": "en",
    "english": "en",
    "ingilis": "en",
    "ingilis dili": "en",
    "ru": "ru",
    "rus": "ru",
    "russian": "ru",
    "rus dili": "ru",
    "русский": "ru",
}
KEYS = ("sector", "language_sector", "language")
TAG = r"(?i:az|aze|en|eng|ing|ru|rus)"
DELIMITED = re.compile(r"(?:^|[\s(\[-])(?P<tag>" + TAG + r")(?:[)\]]|[- ]\d+)?$")
# Attached tags are accepted only on the observed numeric + uppercase code
# shape (233KEing / 235İT-1az), never a fuzzy suffix of arbitrary words.
ATTACHED = re.compile(r"^[\d/ .-]+[A-ZƏİÖÜÇŞĞ]+(?:-\d+)?(?P<tag>" + TAG + r")(?:-\d+)?$")


def _normal(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().replace("\u0307", "").split())


def evidence(name, settings):
    raw = settings if isinstance(settings, dict) else {}
    invalid = bool(settings) and not isinstance(settings, dict)
    values = set()
    for key in KEYS:
        value = raw.get(key)
        if value in (None, ""):
            continue
        if not isinstance(value, str):
            invalid = True
            continue
        normalized = _normal(value)
        if normalized:
            values.add(ALIASES.get(normalized, normalized))
    text = unicodedata.normalize("NFKC", str(name or "")).strip()
    marker = DELIMITED.search(text) or ATTACHED.fullmatch(text)
    label = ALIASES.get(_normal(marker.group("tag")), "") if marker else ""
    reasons = []
    if invalid or len(values) > 1:
        reasons.append("structured_language_conflict_or_invalid")
    if label and values and label not in values:
        reasons.append("structured_language_name_conflict")
    return {
        "structured": next(iter(values)) if len(values) == 1 else "",
        "explicit_name_tag": label,
        "reasons": reasons,
    }


def group_language_issues(groups, *, require_structured=False):
    rows = [(group, evidence(group.name, group.settings)) for group in groups]
    issues = [(str(group.pk), reason) for group, row in rows for reason in row["reasons"]]
    if require_structured:
        issues.extend((str(group.pk), "structured_language_missing") for group, row in rows if not row["structured"])
        issues.extend(
            (str(group.pk), "structured_language_unknown")
            for group, row in rows
            if row["structured"] and row["structured"] not in set(ALIASES.values())
        )
    known = {value for _, row in rows for value in (row["structured"], row["explicit_name_tag"]) if value}
    if len(known) > 1:
        issues.extend((str(group.pk), "group_language_evidence_disagrees") for group, _ in rows)
    return issues
