"""Ad moderasiyası — giriş mətninin normallaşdırılması və tokenlərə bölünməsi (2026-09-30).

SAF modul (Django / DB asılılığı yoxdur). Məqsəd: istifadəçinin gizlətmə
cəhdlərini («s.i.k», «$ht», «сyка», «𝐬𝐢𝐤», «s​i​k», «siiik», «fu ck») eyni
formaya salmaq, AMMA Azərbaycan / türk hərflərini QATLAMAMAQ — «ş», «ç», «ğ»,
«ə», «ı», «ö», «ü» olduğu kimi qalır. Qatlama lüğət tərəfində, qaydanın
özündə edilir (bax ``wordlist.py``): «ş» hərfli qayda girişdəki «s»-i tutur,
«s» hərfli qayda isə girişdəki «ş»-ni TUTMUR («sik» ≠ «şik»).

Addımlar:

1. NFKC (fullwidth, riyazi hərflər, dairəvi hərflər, ligaturlar → adi hərf) +
   ``casefold``;
2. nəzarət / format / görünməz simvollar (zero-width, bidi, Hangul filler)
   atılır; qorunan hərflərdən başqa bütün diakritiklər silinir («fück» → «fuck»,
   kiril «й» → «и», «ё» → «е»); dekorativ birləşən işarələr («s̶i̶k̶») atılır;
3. tokenlərə bölünür: boşluq və durğu işarələri ayırır, ``* ' ` ^ ~`` isə söz
   DAXİLİNDƏ silinir («f*ck» → «fck»); tək hərfli ardıcıl tokenlər birləşir
   («s i k t i r» → «siktir»);
4. hər token üçün formalar: leetspeak (0→o 1→i/l 3→e 4→a 5→s 7→t 6/8→b @→a $→s,
   kiril tokendə 3→з 6→б 4→ч 9→я), kənar rəqəm/simvolların atıldığı variant,
   qarışıq əlifba tokenində kiril↔latın homoqlif və fonetik oxunuşlar.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

#: Uzun giriş kəsilir — ad sahələri 150 simvoldan uzun deyil.
MAX_INPUT_LENGTH = 300

#: Diakritiki SİLİNMƏYƏN hərflər (Azərbaycan / türk əlifbası).
PROTECTED_LETTERS = frozenset("əıöüşçğ")

_STRIPPED_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co"})
_MARK_CATEGORIES = frozenset({"Mn", "Me", "Mc"})
#: Kateqoriyası Cf olmayan, amma görünməz render olunan simvollar (text_safety ilə eyni).
_INVISIBLE = frozenset(
    {0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x180B, 0x180C, 0x180D, 0x180E, 0x180F, 0x2800, 0x3164, 0xFFA0}
)

#: Söz DAXİLİNDƏ silinən (ayırmayan) simvollar.
_JOIN_CHARS = frozenset("*'`´ʼʻ’‘^~¨°")
#: Hərf yerinə yazılan simvollar (latın tokeni).
_LEET_LATIN = {
    "0": "o",
    "3": "e",
    "4": "a",
    "5": "s",
    "6": "b",
    "7": "t",
    "8": "b",
    "@": "a",
    "$": "s",
    "€": "e",
    "£": "l",
    "!": "i",
}
#: Hərf yerinə yazılan simvollar (kiril tokeni).
_LEET_CYRILLIC = {"0": "о", "3": "з", "4": "ч", "6": "б", "9": "я", "@": "а", "$": "с"}
#: İki cür oxunan simvollar: «1» / «|» → i və ya l.
_AMBIGUOUS = frozenset("1|")
_SYMBOL_CHARS = frozenset(_LEET_LATIN) | frozenset(_LEET_CYRILLIC) | _AMBIGUOUS

#: Kiril → latın VİZUAL homoqliflər («сука» → «cyka», «ѕһіt» → «shit»).
CYRILLIC_TO_LATIN_VISUAL = {
    "а": "a",
    "в": "b",
    "е": "e",
    "к": "k",
    "м": "m",
    "н": "h",
    "о": "o",
    "р": "p",
    "с": "c",
    "т": "t",
    "у": "y",
    "х": "x",
    "і": "i",
    "ј": "j",
    "ѕ": "s",
    "һ": "h",
    "ԁ": "d",
    "ӏ": "l",
    "ԛ": "q",
    "ԝ": "w",
    "ү": "y",
}
#: Kiril → latın FONETİK oxunuş (yalnız QARIŞIQ tokenlərdə; saf kiril sözü
#: fonetik oxunmur — «шить» → «shit» kimi saxta uyğunluq verərdi).
CYRILLIC_TO_LATIN_PHONETIC = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    "і": "i",
    "ј": "j",
    "һ": "h",
}
#: Latın → kiril VİZUAL homoqliflər (qarışıq token: «cукa» → «сука»).
LATIN_TO_CYRILLIC_VISUAL = {
    "a": "а",
    "b": "в",
    "c": "с",
    "e": "е",
    "h": "н",
    "k": "к",
    "m": "м",
    "o": "о",
    "p": "р",
    "t": "т",
    "x": "х",
    "y": "у",
    "u": "и",
}
#: Latın → kiril FONETİK oxunuş (qarışıq token: «пиzда» → «пизда», «бlядь» → «блядь»).
LATIN_TO_CYRILLIC_PHONETIC = {
    "a": "а",
    "b": "б",
    "c": "с",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "х",
    "i": "и",
    "j": "и",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "v": "в",
    "x": "х",
    "y": "у",
    "z": "з",
}
#: Yunan homoqlifləri → latın.
GREEK_TO_LATIN = {
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
    "ω": "w",
}


def is_cyrillic(char: str) -> bool:
    return "Ѐ" <= char <= "ԯ"


def fold_char_marks(char: str) -> str:
    """Qorunan hərflər qalır; digərlərinin diakritiki silinir («é» → «e», «й» → «и»)."""
    if char in PROTECTED_LETTERS or char.isascii():
        return char
    return "".join(
        part for part in unicodedata.normalize("NFD", char) if unicodedata.category(part) not in _MARK_CATEGORIES
    )


def canonical_text(value) -> str:
    """Addım 1–2: NFKC + casefold + görünməzlərin / diakritiklərin atılması."""
    text = unicodedata.normalize("NFKC", str(value or "")[:MAX_INPUT_LENGTH]).casefold()
    kept: list[str] = []
    for char in text:
        if char.isspace():
            kept.append(" ")
            continue
        category = unicodedata.category(char)
        if category in _STRIPPED_CATEGORIES or category in _MARK_CATEGORIES or ord(char) in _INVISIBLE:
            continue
        if 0xFE00 <= ord(char) <= 0xFE0F or 0xE0100 <= ord(char) <= 0xE01EF:
            continue
        kept.append(fold_char_marks(char))
    return "".join(kept)


def normalize_cyrillic(token: str) -> str:
    """Kiril tokeni/lüğət sözü üçün: ё→е, й→и (``fold_char_marks`` edir), ь atılır."""
    return token.replace("ь", "")


def raw_tokens(text: str) -> list[str]:
    """Addım 3: hərf/rəqəm/leet simvolu ardıcıllıqları; tək simvollu run-lar birləşir."""
    tokens: list[str] = []
    current: list[str] = []
    for char in text:
        if char.isalnum() or char in _SYMBOL_CHARS:
            current.append(char)
        elif char in _JOIN_CHARS:
            continue
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    merged: list[str] = []
    run: list[str] = []
    for token in tokens:
        if len(token) == 1:
            run.append(token)
            continue
        if run:
            merged.append("".join(run))
            run = []
        merged.append(token)
    if run:
        merged.append("".join(run))
    return merged


@dataclass
class TokenForms:
    """Bir tokenin latın və kiril mühərrikləri üçün formaları (ilk element = əsas forma)."""

    latin: list[str] = field(default_factory=list)
    cyrillic: list[str] = field(default_factory=list)

    def add_latin(self, value: str) -> None:
        if value and value not in self.latin:
            self.latin.append(value)

    def add_cyrillic(self, value: str) -> None:
        value = normalize_cyrillic(value) if value else value
        if value and value not in self.cyrillic:
            self.cyrillic.append(value)


def _strip_edges(token: str) -> str:
    start, end = 0, len(token)
    while start < end and not token[start].isalpha():
        start += 1
    while end > start and not token[end - 1].isalpha():
        end -= 1
    return token[start:end]


def _latin_reading(token: str, ambiguous: str, cyrillic_map: dict | None) -> str | None:
    """Tokenin latın oxunuşu; ``cyrillic_map`` yoxdursa kiril hərfli token oxunmur."""
    out: list[str] = []
    for char in token:
        if char.isalpha():
            if is_cyrillic(char):
                if cyrillic_map is None or char not in cyrillic_map:
                    return None
                out.append(cyrillic_map[char])
            else:
                out.append(GREEK_TO_LATIN.get(char, char))
        elif char in _AMBIGUOUS:
            out.append(ambiguous)
        else:
            out.append(_LEET_LATIN.get(char, ""))
    return "".join(out)


def _cyrillic_reading(token: str, latin_map: dict) -> str:
    out: list[str] = []
    for char in token:
        if char.isalpha():
            if is_cyrillic(char):
                out.append(char)
            else:
                latin = GREEK_TO_LATIN.get(char, char)
                out.append(latin_map.get(latin, latin))
        else:
            out.append(_LEET_CYRILLIC.get(char, ""))
    return "".join(out)


def token_forms(raw: str) -> TokenForms | None:
    """Addım 4: bir xam token → mühərrik formaları (hərfsiz token → ``None``)."""
    forms = TokenForms()
    variants = [raw]
    stripped = _strip_edges(raw)
    if stripped and stripped != raw:
        variants.append(stripped)
    for variant in variants:
        letters = [char for char in variant if char.isalpha()]
        if not letters:
            continue
        has_cyrillic = any(is_cyrillic(char) for char in letters)
        has_latin = any(not is_cyrillic(char) for char in letters)
        for ambiguous in ("i", "l"):
            if not has_cyrillic:
                forms.add_latin(_latin_reading(variant, ambiguous, None))
                continue
            # Saf kiril: yalnız VİZUAL oxunuş (hamısı homoqlifdirsə); qarışıq: hər ikisi.
            forms.add_latin(_latin_reading(variant, ambiguous, CYRILLIC_TO_LATIN_VISUAL) or "")
            if has_latin:
                forms.add_latin(_latin_reading(variant, ambiguous, CYRILLIC_TO_LATIN_PHONETIC) or "")
        if has_cyrillic:
            forms.add_cyrillic(_cyrillic_reading(variant, LATIN_TO_CYRILLIC_VISUAL))
            if has_latin:
                forms.add_cyrillic(_cyrillic_reading(variant, LATIN_TO_CYRILLIC_PHONETIC))
    if not forms.latin and not forms.cyrillic:
        return None
    return forms


def tokenize(value) -> list[TokenForms]:
    """Mətn → token formaları siyahısı (sıra saxlanılır)."""
    result: list[TokenForms] = []
    for raw in raw_tokens(canonical_text(value)):
        forms = token_forms(raw)
        if forms is not None:
            result.append(forms)
    return result


__all__ = [
    "MAX_INPUT_LENGTH",
    "PROTECTED_LETTERS",
    "TokenForms",
    "canonical_text",
    "fold_char_marks",
    "is_cyrillic",
    "normalize_cyrillic",
    "raw_tokens",
    "token_forms",
    "tokenize",
]
