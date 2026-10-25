"""Xarici dil SƏVİYYƏ fənləri — «Xarici dildə … -1(elementary)» / «…(intermediate)» (sahib 2026-10-26).

Köhnə sistemdə səviyyə jurnalı bir neçə qrupu birləşdirir və yalnız həmin səviyyənin tələbələrini saxlayır;
qrupun bir hissəsi bir səviyyədə, digəri başqa səviyyədədir. Ona görə səviyyə fənninin qiyməti tələbənin hansı
QRUPA (alt qrupa) aid olduğunu göstərmir — yerləşdirmə sübutlarında nəzərə alınmır.
"""

from __future__ import annotations

import re

LEVEL_RE = re.compile(
    r"\(\s*(beginner|elementary|pre[- ]?intermediate|intermediate|upper[- ]?intermediate|advanced|[abc][12])\s*\)",
    re.IGNORECASE,
)


def level_of(name) -> str:
    """Fənn adındakı səviyyə («elementary» …) və ya boş sətir."""
    match = LEVEL_RE.search(str(name or ""))
    return re.sub(r"[\s-]+", "-", match.group(1).lower()) if match else ""


def is_level_subject(name) -> bool:
    return bool(level_of(name))


def level_family(name) -> str:
    """Səviyyə atılmış fənn ailəsi: «Xarici dil-1(elementary)» = «xarici dil-1»."""
    return re.sub(r"\s+", " ", LEVEL_RE.sub("", str(name or ""))).strip().lower()


__all__ = ["LEVEL_RE", "is_level_subject", "level_family", "level_of"]
