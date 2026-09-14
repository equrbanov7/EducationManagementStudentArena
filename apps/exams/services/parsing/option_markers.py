"""Variant sətrindəki düz-cavab markerləri (`*B)` prefiksi və `B) …*` sonluğu).

W4 2026-09-14 (w3sweep R5) — `_core.py` 600 sətir qapısına görə ayrıca modul.
"""

from __future__ import annotations

import re

# W4 2026-09-14 (w3sweep R5): sənəddə düz cavab `*B)` prefiksi ilə yazılır, amma
# müəllimlər tez-tez SONLUQ işarəsi işlədir («B) iki*»). Sətrin sonundakı tək
# `*` (boşluqla və ya boşluqsuz) düz cavab markeri sayılır və mətndən silinir.
_TRAILING_STAR_RE = re.compile(r"\s*\*$")


def _option_from_match(m_opt) -> tuple[str, str, bool]:
    """OPTION_RE uyğunluğundan (etiket, mətn, düzdür?) — prefiks `*` və ya sonluq `*`."""
    star = bool(m_opt.group(1))
    label = m_opt.group(2).upper()
    text = m_opt.group(3).strip()
    if _TRAILING_STAR_RE.search(text):
        stripped = _TRAILING_STAR_RE.sub("", text).strip()
        if stripped:
            text = stripped
            star = True
    return label, text, star


__all__ = ["_option_from_match"]
