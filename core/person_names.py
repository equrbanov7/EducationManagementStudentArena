"""Ad hissələrində idxal «boşluq doldurucuları» — göstərmədə boş sayılır (QA-1 F15).

Köhnə sistemdən gələn siyahılarda ata adı olmayanda ``-`` yazılırdı; jurnal sətri «Soyadov Ad -» kimi görünürdü.
Saxlanan dəyər dəyişmir — yalnız çıxışda atılır (jurnal adı, kadr/tələbə siyahıları, ``full_name_with_patronymic``).
"""

from __future__ import annotations

_PUNCTUATION_ONLY = frozenset("-–—−_.?/*,;:'\"`~ ")
_WORD_PLACEHOLDERS = frozenset({"n/a", "na", "none", "null", "yoxdur", "yox"})


def clean_name_part(value) -> str:
    """Kənar boşluqlar atılır; yalnız durğu işarəsindən ibarət («-», «--», «.») və ya «yoxdur» → ``""``."""
    text = (value or "").strip() if isinstance(value, str) or value is None else str(value).strip()
    if not text:
        return ""
    if all(char in _PUNCTUATION_ONLY for char in text) or text.casefold() in _WORD_PLACEHOLDERS:
        return ""
    return text


__all__ = ["clean_name_part"]
