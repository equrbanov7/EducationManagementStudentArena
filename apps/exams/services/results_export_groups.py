"""Stable group tabs and subject ordering for evaluated results exports."""

import re
import unicodedata
from collections import defaultdict

AZ_ALPHABET = "abcçdeəfgğhxıijkqlmnoöprsştuüvyz"
AZ_ORDER = {letter: index for index, letter in enumerate(AZ_ALPHABET)}


def result_sort_key(value):
    """Azerbaijani alphabet, with numeric runs sorted as numbers (G2 before G10)."""
    text = unicodedata.normalize("NFC", str(value or "")).replace("İ", "i").replace("I", "ı").casefold()
    return tuple(
        (0, int(part)) if part.isdigit() else (1, tuple(AZ_ORDER.get(ch, 1000 + ord(ch)) for ch in part))
        for part in re.split(r"(\d+)", text)
    )


def grouped_result_rows(rows):
    # The collector's authoritative current group label is one grouping value;
    # never split punctuation in names or duplicate a result into several tabs.
    groups = defaultdict(list)
    for row in rows:
        groups[str(row.get("groups") or "")].append(row)
    if not groups:
        return [("Nəticələr", [])]
    return [
        (
            group or "Qrupsuz",
            sorted(
                groups[group],
                key=lambda row: tuple(
                    result_sort_key(row.get(field)) for field in ("subject", "title", "student", "username")
                ),
            ),
        )
        for group in sorted(groups, key=result_sort_key)
    ]
