"""Oyunçu mətninin gigiyenası — ləqəb və yazılı cavab (Audit 2026-09-28 LX-SEC).

SAF funksiyalardır (DB / Django asılılığı yoxdur) — ``auth.clean_nickname`` və
LX-BE-nin yazılı cavab axını (``typed_answers``) eyni qaydanı işlədir.

Qayda RFC 8266 (PRECIS «Nickname» profili) ruhundadır:

* nəzarət (Cc), format (Cf — zero-width, bidi override/isolate, BOM, soft hyphen),
  surrogate / private-use simvollar və «boş görünən» hərflər (Hangul filler,
  Braille blank, variation selector) ATILIR — PostgreSQL NUL-u qəbul etmir (500),
  görünməz / RTL-override ləqəblər isə mövcud adın «dublikatı» kimi görünürdü;
* bütün Unicode boşluqları adi boşluğa çevrilir, sıxılır, kənarlardan kəsilir;
* birləşən işarə (Mn/Me) seriyası 2 ilə məhdudlaşır («Zalgo» mətn proyektorda
  qonşu sətirlərin üstünə daşırdı);
* uzunluq normallaşmadan SONRA kəsilir (NFKC mətni uzada bilər).

Ləqəb üçün əlavə olaraq NFKC (fullwidth «Ａｌｉ» → «Ali») və HTML-həssas
``< > " ` `` simvolları atılır: bəzi JS render-ləri ``esc()``-in dırnağı
qaçırmadığı atribut kontekstlərində ləqəb işlədir (bax SECURITY_REVIEW.md LXS-04).
Yazılı cavabda isə NFC saxlanılır (``x²``, ``a < b`` mənası dəyişməməlidir).
"""

from __future__ import annotations

import re
import unicodedata

NICKNAME_MAX_LENGTH = 32
TYPED_ANSWER_MAX_LENGTH = 60

_STRIPPED_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co"})
_COMBINING_CATEGORIES = frozenset({"Mn", "Me"})
_MAX_COMBINING_RUN = 2

#: Kateqoriyası Cf olmayan, amma görünməz / «boş» render olunan simvollar.
_INVISIBLE_CODEPOINTS = frozenset(
    {0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x180B, 0x180C, 0x180D, 0x180E, 0x180F, 0x2800, 0x3164, 0xFFA0}
    | set(range(0xFE00, 0xFE10))
    | set(range(0xE0100, 0xE01F0))
)

_NICKNAME_FORBIDDEN = frozenset('<>"`')
_SPACES_RE = re.compile(r" {2,}")

#: Kiril / yunan hərfləri → vizual eyni latın hərfi (yalnız UNİKALLIQ açarı üçün;
#: saxlanılan ad dəyişmir). ``casefold``-dan SONRA tətbiq olunur.
_CONFUSABLES = str.maketrans(
    {
        "а": "a",
        "в": "b",
        "е": "e",
        "ё": "ë",
        "і": "i",
        "ї": "ï",
        "ј": "j",
        "к": "k",
        "м": "m",
        "н": "h",
        "о": "o",
        "р": "p",
        "с": "c",
        "т": "t",
        "у": "y",
        "х": "x",
        "ѕ": "s",
        "ԁ": "d",
        "һ": "h",
        "ӏ": "l",
        "ԛ": "q",
        "ԝ": "w",
        "ү": "y",
        "α": "a",
        "β": "b",
        "ε": "e",
        "ζ": "z",
        "η": "h",
        "ι": "i",
        "κ": "k",
        "μ": "m",
        "ν": "v",
        "ο": "o",
        "ρ": "p",
        "τ": "t",
        "υ": "u",
        "χ": "x",
        "ǀ": "l",
    }
)
_COMBINING_DOT_ABOVE = "̇"


def sanitize_player_text(value, *, max_length: int, normalization: str = "NFC", forbidden=frozenset()) -> str:
    """Oyunçu mətnini təhlükəsiz göstərilə bilən formaya salır (bax modul sənədi)."""
    text = unicodedata.normalize(normalization, str(value or ""))
    kept: list[str] = []
    combining_run = 0
    for char in text:
        if char.isspace():
            kept.append(" ")
            combining_run = 0
            continue
        category = unicodedata.category(char)
        if category in _STRIPPED_CATEGORIES or ord(char) in _INVISIBLE_CODEPOINTS or char in forbidden:
            continue
        if category in _COMBINING_CATEGORIES:
            if combining_run >= _MAX_COMBINING_RUN or not kept or kept[-1] == " ":
                continue
            combining_run += 1
        else:
            combining_run = 0
        kept.append(char)
    cleaned = _SPACES_RE.sub(" ", "".join(kept)).strip()
    return cleaned[:max_length].strip()


def clean_nickname(name) -> str:
    """Ləqəb: NFKC + görünməz/bidi/nəzarət/HTML-həssas simvollar atılır, ≤ 32 simvol."""
    return sanitize_player_text(
        name, max_length=NICKNAME_MAX_LENGTH, normalization="NFKC", forbidden=_NICKNAME_FORBIDDEN
    )


def clean_typed_answer(value) -> str:
    """Yazılı cavab: NFC + görünməz/bidi/nəzarət simvollar atılır, ≤ 60 simvol (``<``/``>`` qalır)."""
    return sanitize_player_text(value, max_length=TYPED_ANSWER_MAX_LENGTH, normalization="NFC")


def nickname_match_key(name) -> str:
    """Unikallıq açarı: təmizlənmiş ad → casefold → homoglif xəritəsi («Аli» == «Ali» == «ALİ»)."""
    folded = clean_nickname(name).casefold().replace(_COMBINING_DOT_ABOVE, "")
    return folded.translate(_CONFUSABLES)


__all__ = [
    "NICKNAME_MAX_LENGTH",
    "TYPED_ANSWER_MAX_LENGTH",
    "clean_nickname",
    "clean_typed_answer",
    "nickname_match_key",
    "sanitize_player_text",
]
