"""Xarici dil SƏVİYYƏ fənləri — «Xarici dildə … -1(elementary)» / «…(intermediate)» (sahib 2026-10-26).

Köhnə sistemdə səviyyə jurnalı bir neçə qrupu birləşdirir və yalnız həmin səviyyənin tələbələrini saxlayır;
qrupun bir hissəsi bir səviyyədə, digəri başqa səviyyədədir. Ona görə səviyyə fənninin qiyməti tələbənin hansı
QRUPA (alt qrupa) aid olduğunu göstərmir — yerləşdirmə sübutlarında nəzərə alınmır.

Regex, normallaşdırma və tavanlar :mod:`core.language_level_rule`-dadır (TƏK reyestr — sillabus və kabinet də oradan
oxuyur); bu modul köhnə import yollarını saxlayır.
"""

from __future__ import annotations

from core.language_level_rule import LEVEL_RE, is_level_name, level_family, level_of


def is_level_subject(name) -> bool:
    return is_level_name(name)


__all__ = ["LEVEL_RE", "is_level_subject", "level_family", "level_of"]
