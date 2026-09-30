"""Ad moderasiyası — nalayiq ifadə detektoru (saf funksiyalar, 2026-09-30).

İstifadə::

    from core.moderation import find_profanity
    match = find_profanity("Siktir")      # ProfanityMatch(term="*siktir*", language="az", kind="substring")
    find_profanity("Səmədov") is None     # True

Dizayn — AŞAĞI YANLIŞ POZİTİV: default qayda bütöv sözdür, kök qaydaları yalnız
təmiz sözdə rast gəlinməyən köklər üçündür, «içində» qaydaları isə yalnız çox
fərqli köklər üçündür (bax ``data/az.txt`` başlığı). Hər yeni qayda
``core/tests/test_moderation_detector.py``-dakı real ad / söz siyahısına qarşı
yoxlanılır.
"""

from __future__ import annotations

from dataclasses import dataclass

from .normalize import tokenize
from .wordlist import Rule, engines

#: Maskalanmış dəyərin yuxarı həddi (audit qeydi üçün).
MASK_MAX_LENGTH = 40


@dataclass(frozen=True)
class ProfanityMatch:
    """Tapılan qayda — ``term`` lüğət sətridir (log-da MASKALANIR)."""

    term: str
    language: str
    kind: str

    @classmethod
    def from_rule(cls, rule: Rule) -> "ProfanityMatch":
        return cls(term=rule.term, language=rule.language, kind=rule.kind)


def find_profanity(value) -> ProfanityMatch | None:
    """Mətndə nalayiq ifadə varsa ilk uyğun qaydanı, yoxdursa ``None`` qaytarır."""
    tokens = tokenize(value)
    if not tokens:
        return None
    latin_engine, cyrillic_engine = engines()
    for token in tokens:
        for form in token.latin:
            rule = latin_engine.match_token(form)
            if rule is not None:
                return ProfanityMatch.from_rule(rule)
        for form in token.cyrillic:
            rule = cyrillic_engine.match_token(form)
            if rule is not None:
                return ProfanityMatch.from_rule(rule)
    for engine, primary in (
        (latin_engine, [token.latin[0] for token in tokens if token.latin]),
        (cyrillic_engine, [token.cyrillic[0] for token in tokens if token.cyrillic]),
    ):
        rule = engine.match_sequence(primary)
        if rule is not None:
            return ProfanityMatch.from_rule(rule)
    return None


def contains_profanity(value) -> bool:
    return find_profanity(value) is not None


def mask_value(value, *, max_length: int = MASK_MAX_LENGTH) -> str:
    """İlk hərf + ulduzlar («Siktir» → «S*****»); boşluqlar saxlanılır, uzunluq tavanlı."""
    text = " ".join(str(value or "").split())[:max_length]
    if not text:
        return ""
    return text[0] + "".join(" " if char == " " else "*" for char in text[1:])


__all__ = ["MASK_MAX_LENGTH", "ProfanityMatch", "contains_profanity", "find_profanity", "mask_value"]
