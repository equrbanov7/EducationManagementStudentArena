"""Sual məzmununa aid olmayan sənəd başlıqlarını deterministik tanıyır."""

from __future__ import annotations

import re

_SECTION_HEADING_RE = re.compile(
    r"^\s*(?:Раздел|Section|Chapter|Bölmə|Bölüm|Fəsil)\s+" r"(?:\d+|[IVXLCDM]+)\b",
    re.IGNORECASE,
)


def is_section_heading(value: object) -> bool:
    """Standalone bölmə/fəsil başlığıdırsa ``True`` qaytar."""

    return bool(_SECTION_HEADING_RE.match(str(value or "")))


__all__ = ["is_section_heading"]
