"""Ad moderasiyası — lüğət fayllarının oxunması və qaydaların regex-ə çevrilməsi (2026-09-30).

SAF modul. Lüğətlər ``core/moderation/data/<dil>.txt`` fayllarındadır (kodda
səpələnmir); format hər faylın başlığında izah olunub. Hər qayda iki mühərrikdən
birinə düşür:

* LATIN mühərriki — latın hərfli qaydalar (az / tr / en və rus translit);
  qaydanın hərfləri «qatlama siniflərinə» çevrilir (``ə`` → ``[əea]`` və s.) —
  qatlama ASİMMETRİKDİR: lüğətdəki ``s`` girişdəki ``ş``-ni tutmur;
* KİRİL mühərriki — kiril hərfli qaydalar (rus); hərflər olduğu kimi.

Hər iki halda hərf təkrarı tutulur («siiik»): lüğətdəki N dəfəlik hərf girişdə
ən azı N dəfə olmalıdır («yarrak» ≠ «yaraq»).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from itertools import groupby
from pathlib import Path

from .normalize import canonical_text, is_cyrillic, normalize_cyrillic

DATA_DIR = Path(__file__).resolve().parent / "data"
LANGUAGES = ("az", "tr", "en", "ru")
ALLOW_FILE = "allow.txt"

KIND_WORD = "word"
KIND_PREFIX = "prefix"
KIND_SUBSTRING = "substring"
KIND_PHRASE = "phrase"

#: Lüğət hərfi → girişdə qəbul olunan variantlar (yalnız latın, «sərt» olmayan qayda).
LATIN_FOLDING = {
    "ə": "[əea]",
    "ı": "[ıi]",
    "ş": "(?:ş|sh|s)",
    "ç": "(?:ç|ch|c)",
    "ğ": "(?:ğ|gh|g)",
    "ö": "(?:ö|oe|o)",
    "ü": "(?:ü|ue|u)",
    "q": "[qgk]",
    "k": "[kq]",
    "x": "(?:x|kh|h)",
    "y": "[yij]",
}


@dataclass(frozen=True)
class Rule:
    """Bir lüğət sətri."""

    term: str
    language: str
    kind: str
    pattern: str
    cyrillic: bool


def _char_pattern(char: str, *, fold: bool) -> str:
    if fold and char in LATIN_FOLDING:
        return LATIN_FOLDING[char]
    return re.escape(char)


def word_pattern(word: str, *, fold: bool) -> str:
    """Bir sözü regex-ə çevirir: hər hərf (və ya qatlama sinfi) təkrar oluna bilər."""
    parts: list[str] = []
    for char, run in groupby(word):
        count = len(list(run))
        body = _char_pattern(char, fold=fold)
        if count == 1:
            parts.append(f"(?:{body})+")
        else:
            parts.append(f"(?:{body}){{{count},}}")
    return "".join(parts)


def _normalize_term(word: str) -> str:
    text = canonical_text(word).strip()
    return normalize_cyrillic(text) if any(is_cyrillic(char) for char in text) else text


def parse_rule(line: str, language: str) -> Rule | None:
    """Bir lüğət sətri → ``Rule`` (şərh / boş sətir → ``None``)."""
    raw = line.split("#", 1)[0].strip()
    if not raw:
        return None
    strict = raw.startswith("=")
    body = raw[1:] if strict else raw
    fold = not strict
    words = body.split()
    if len(words) > 1:
        kind = KIND_PHRASE
    elif body.startswith("*") and body.endswith("*") and len(body) > 2:
        kind = KIND_SUBSTRING
    elif body.endswith("*"):
        kind = KIND_PREFIX
    else:
        kind = KIND_WORD
    pieces = []
    for index, word in enumerate(words):
        last = index == len(words) - 1
        clean = _normalize_term(word.strip("*"))
        if not clean:
            return None
        piece = word_pattern(clean, fold=fold)
        if kind == KIND_PHRASE and last and word.endswith("*"):
            piece += r"\S*"
        pieces.append(piece)
    if kind == KIND_PHRASE:
        # Ardıcıl tokenlər; boşluqsuz birləşmə də («ananısikim») tutulur.
        pattern = r"(?<!\S)" + "(?: )?".join(pieces)
        if not words[-1].endswith("*"):
            pattern += r"(?!\S)"
    else:
        pattern = pieces[0]
    cyrillic = any(is_cyrillic(char) for char in body)
    return Rule(term=raw, language=language, kind=kind, pattern=pattern, cyrillic=cyrillic)


def read_rules(language: str, *, data_dir: Path = DATA_DIR) -> list[Rule]:
    path = data_dir / f"{language}.txt"
    rules = []
    for line in path.read_text(encoding="utf-8").splitlines():
        rule = parse_rule(line, language)
        if rule is not None:
            rules.append(rule)
    return rules


def read_allowlist(*, data_dir: Path = DATA_DIR) -> tuple[frozenset[str], tuple[str, ...]]:
    """``(bütöv tokenlər, köklər)`` — normallaşdırılmış formada."""
    exact: set[str] = set()
    prefixes: list[str] = []
    for line in (data_dir / ALLOW_FILE).read_text(encoding="utf-8").splitlines():
        raw = line.split("#", 1)[0].strip()
        if not raw:
            continue
        clean = _normalize_term(raw.rstrip("*"))
        if not clean:
            continue
        if raw.endswith("*"):
            prefixes.append(clean)
        else:
            exact.add(clean)
    return frozenset(exact), tuple(prefixes)


class Engine:
    """Bir əlifba üçün qaydalar + birləşdirilmiş (sürətli ilk keçid) regex-lər."""

    def __init__(self, rules: list[Rule], allow_exact: frozenset[str], allow_prefixes: tuple[str, ...]):
        self.allow_exact = allow_exact
        self.allow_prefixes = allow_prefixes
        self.rules = {
            kind: [rule for rule in rules if rule.kind == kind]
            for kind in (KIND_WORD, KIND_PREFIX, KIND_SUBSTRING, KIND_PHRASE)
        }
        self.compiled = {
            kind: [(re.compile(rule.pattern), rule) for rule in items] for kind, items in self.rules.items()
        }
        self.combined = {
            kind: re.compile("|".join(f"(?:{rule.pattern})" for rule in items)) if items else None
            for kind, items in self.rules.items()
        }

    def is_allowed(self, token: str) -> bool:
        if token in self.allow_exact:
            return True
        return bool(self.allow_prefixes) and token.startswith(self.allow_prefixes)

    def _first(self, kind: str, method: str, text: str) -> Rule | None:
        combined = self.combined[kind]
        if combined is None or getattr(combined, method)(text) is None:
            return None
        for regex, rule in self.compiled[kind]:
            if getattr(regex, method)(text) is not None:
                return rule
        return None

    def match_token(self, token: str) -> Rule | None:
        if not token:
            return None
        rule = self._first(KIND_WORD, "fullmatch", token)
        if rule is not None or self.is_allowed(token):
            return rule
        return self._first(KIND_PREFIX, "match", token) or self._first(KIND_SUBSTRING, "search", token)

    def match_sequence(self, tokens: list[str]) -> Rule | None:
        """İfadə qaydaları (tokenlər boşluqla) və «içində» qaydaları (boşluqsuz birləşmə)."""
        if not tokens:
            return None
        rule = self._first(KIND_PHRASE, "search", " ".join(tokens))
        if rule is not None:
            return rule
        for compact in _split_word_runs([token for token in tokens if not self.is_allowed(token)]):
            rule = self._first(KIND_SUBSTRING, "search", compact)
            if rule is not None:
                return rule
        return None


#: Parçalanmış söz («s i k t i r», «fu ck») yalnız QISA tokenlər arasında birləşdirilir.
SPLIT_TOKEN_MAX = 3


def _split_word_runs(tokens: list[str]) -> list[str]:
    """Qonşu tokenlərdən ən azı biri qısadırsa (≤ ``SPLIT_TOKEN_MAX``) birləşdirilmiş ardıcıllıqlar.

    Təhlükəsizlik baxışı 2026-09-30: bütün tokenləri birləşdirmək ad+soyad sərhədində
    saxta uyğunluq yaradırdı («Isik Tiryaki» → *siktir*, «Yusif Uckun» → *fuck*). İki
    uzun söz arasındakı sərhəd birləşdirilmir; tək tokenlər ``match_token``-də yoxlanır.
    """
    runs: list[str] = []
    current: list[str] = tokens[:1]
    for previous, token in zip(tokens, tokens[1:]):
        if min(len(previous), len(token)) <= SPLIT_TOKEN_MAX:
            current.append(token)
            continue
        if len(current) > 1:
            runs.append("".join(current))
        current = [token]
    if len(current) > 1:
        runs.append("".join(current))
    return runs


@lru_cache(maxsize=1)
def engines() -> tuple[Engine, Engine]:
    """``(latın, kiril)`` mühərrikləri — ilk çağırışda bir dəfə qurulur."""
    rules: list[Rule] = []
    for language in LANGUAGES:
        rules.extend(read_rules(language))
    allow_exact, allow_prefixes = read_allowlist()
    latin = Engine([rule for rule in rules if not rule.cyrillic], allow_exact, allow_prefixes)
    cyrillic = Engine([rule for rule in rules if rule.cyrillic], allow_exact, allow_prefixes)
    return latin, cyrillic


__all__ = [
    "DATA_DIR",
    "KIND_PHRASE",
    "KIND_PREFIX",
    "KIND_SUBSTRING",
    "KIND_WORD",
    "LANGUAGES",
    "LATIN_FOLDING",
    "SPLIT_TOKEN_MAX",
    "Engine",
    "Rule",
    "engines",
    "parse_rule",
    "read_allowlist",
    "read_rules",
    "word_pattern",
]
