"""``mark_exam_halls`` komandası üçün korpus/otaq uyğunlaşdırması (sahib 2026-10-01).

Sahib otaqları danışıq dilində adlandırır: «B korpusunda 03, 28, 38». Reyestrdə isə:

* korpus ``ExamRoom.building`` mətnidir — istehsalda «Korpus B (Yüksək
  texnologiyalar)» (``scripts/ops/seed_qku_campuses_rooms.py``), QA klonda
  legacy ``bina`` rəqəmi («3»);
* otaq ADI legacy mətnidir — «03/2», «28», «-101», «AA», «akt zalı»; kod
  ``myedu-room-<legacy id>``.

Korpus açarları: tam ad, mötərizəsiz ad, mötərizə içi, «korpus/bina» sözləri
atılmış qalıq («b»). Otaq tokeni üçün pillələr (ən yaxşı pillə qalib gəlir,
eyni pillədə birdən çox namizəd → QEYRİ-MÜƏYYƏN, heç nə yazılmır):

0. dəqiq ad və ya kod (böyük/kiçik hərf, AZ hərfləri fərqsiz);
1. rəqəm bərabərliyi — aparıcı sıfırlar fərqsiz («03» = «3»);
2. əsas nömrə + şəkilçi — «03» → «03/2», «28» → «28A» (yalnız TƏK namizəd olanda).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

_WS = re.compile(r"\s+")
_PAREN = re.compile(r"\(([^)]*)\)")
_BUILDING_WORDS = re.compile(r"\b(korpus|korpusu|bina|binasi|building|block|blok)\b")
_NON_WORD = re.compile(r"[^\w]+")
_BASE_NUMBER = re.compile(r"^(\d+)\D")

TIER_EXACT = 0
TIER_NUMERIC = 1
TIER_BASE_NUMBER = 2


def fold(value) -> str:
    """Müqayisə açarı: kiçik hərf (AZ «İ/ı» daxil), diakritiksiz, tək boşluq."""
    text = str(value or "").replace("İ", "i").replace("I", "ı").lower()
    text = text.replace("ə", "e").replace("ı", "i")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return _WS.sub(" ", text).strip()


def building_keys(label) -> set[str]:
    folded = fold(label)
    if not folded:
        return set()
    keys = {folded}
    keys.update(part.strip() for part in _PAREN.findall(folded))
    base = _WS.sub(" ", _PAREN.sub(" ", folded)).strip()
    keys.add(base)
    residue = _WS.sub(" ", _NON_WORD.sub(" ", _BUILDING_WORDS.sub(" ", base))).strip()
    keys.add(residue)
    return {key for key in keys if key}


def building_matches(label, wanted) -> bool:
    return bool(building_keys(label) & building_keys(wanted))


def parse_room_tokens(raw) -> list[str]:
    """«03, 28 ,38» → ["03", "28", "38"] (boşlar atılır, sıra və təkrarsızlıq saxlanır)."""
    seen: list[str] = []
    for part in str(raw or "").split(","):
        token = part.strip()
        if token and token not in seen:
            seen.append(token)
    return seen


def room_match_tier(name, code, token):
    """Otaq tokenə uyğundursa pillə (0/1/2), deyilsə ``None``."""
    n = fold(name)
    t = fold(token)
    if not t:
        return None
    if n == t or fold(code) == t:
        return TIER_EXACT
    if t.isdigit():
        if n.isdigit() and int(n) == int(t):
            return TIER_NUMERIC
        base = _BASE_NUMBER.match(n)
        if base and int(base.group(1)) == int(t):
            return TIER_BASE_NUMBER
    return None


@dataclass
class TokenMatch:
    token: str
    room: object = None
    tier: int | None = None
    candidates: list = field(default_factory=list)

    @property
    def ambiguous(self) -> bool:
        return self.room is None and len(self.candidates) > 1


def match_room_tokens(rooms, tokens) -> list[TokenMatch]:
    """Hər token üçün ən yaxşı pillədəki namizədləri tapır (tək namizəd → ``room``)."""
    rooms = list(rooms)
    results: list[TokenMatch] = []
    for token in tokens:
        scored = [(tier, room) for room in rooms if (tier := room_match_tier(room.name, room.code, token)) is not None]
        if not scored:
            results.append(TokenMatch(token=token))
            continue
        best = min(tier for tier, _room in scored)
        picks = [room for tier, room in scored if tier == best]
        results.append(TokenMatch(token=token, room=picks[0] if len(picks) == 1 else None, tier=best, candidates=picks))
    return results


__all__ = [
    "TIER_BASE_NUMBER",
    "TIER_EXACT",
    "TIER_NUMERIC",
    "TokenMatch",
    "building_keys",
    "building_matches",
    "fold",
    "match_room_tokens",
    "parse_room_tokens",
    "room_match_tier",
]
