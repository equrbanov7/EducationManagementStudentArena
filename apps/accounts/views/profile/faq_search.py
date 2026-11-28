"""Rank an already-authorized FAQ list and locate the relevant chapter in its own video."""

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from core.search_text import MAX_QUERY_LENGTH, MAX_TOKEN_LENGTH, clean_query

from .faq_catalog import BUILTIN_BY_KEY, Guide

_STOP = frozenset("ve ile ucun bu bir ne nece niye harada harda haradan hardan hara men mene olar mi".split())
_WORDS = re.compile(r"[^\W_]+", re.UNICODE)
_SYMBOLS = re.compile(r"\b(?:i\s*[/／]\s*e|q\s*[/／]\s*b)\b|\bpin[\s._-]+kod", re.IGNORECASE)
_DIGRAPHS = re.compile("sh|ch|gh|kh")
_DIGRAPH = {"sh": "s", "ch": "c", "gh": "g", "kh": "x"}

# Closed families prevent broad substring matches such as 'bal' inside 'balans'.
# Suffixes are applied only to known roots; arbitrary tenant titles still match literally or by typo.
_FAMILIES = (
    ("qiymet", "giymet"),
    ("netice", "natice"),
    ("qayib", "qaib", "gayib", "qayb", "qeyib"),
    ("sillabus", "silabus", "syllabus"),
    ("pinkod", "pin"),
    ("muellim", "muallim"),
    ("telebe", "talaba"),
    ("cedvel", "cadval"),
    ("apellyasiya", "apelyasiya", "appelyasiya"),
    ("parol", "sifre"),
    ("kocur",),
    ("movzu",),
    ("jurnal",),
    ("istirak",),
    ("davamiyyet",),
    ("imtahan",),
    ("ders",),
    ("material",),
    ("qovluq", "qovlug"),
    ("qrup",),
    ("hefte",),
    ("fenn",),
    ("bal",),
    ("musahide",),
    ("tapsiriq", "tapsirig"),
    ("merhele",),
    ("erize",),
    ("xerite",),
    ("tarix",),
    ("limit",),
    ("muraciet",),
    ("tercume",),
    ("yukle",),
    ("redakte",),
    ("tesdiq",),
    ("saxla",),
    ("yarat", "yarad"),
    ("gonder",),
    ("imtina",),
    ("bax",),
    ("gor",),
    ("yaz",),
    ("ac",),
    ("sec",),
    ("duzelis",),
    ("qiymetlendir",),
)
_ROOT = {word: family[0] for family in _FAMILIES for word in family}
_NOUN_END = re.compile(
    r"(?:lar|ler)?(?:[iu]?[mn](?:[iu]z)?|s?[iu]|si|su)?"
    r"(?:n?[ae]|y[ae]|n?[dt][ae]n?|n?[iu]|y[iu]|n?[iu]n|l[ae]|y?l[ae])?"
    r"(?:d[iu]r|m[iu])?"
)
_VERB_END = re.compile(
    r"(?:maq|mek|ma|me|yan|yen|an|en|[iyu]?[bm][ae]?[kq]?|[iyu]?n|[iyu]?m|"
    r"[diut]+m|maqda|mekde|diq|dik|masi|mesi|magi|meyi|maga|meye)"
)
_ROOTS_BY_INITIAL = {}
for _word in sorted(_ROOT, key=len, reverse=True):
    _ROOTS_BY_INITIAL.setdefault(_word[:2], []).append(_word)
_RELATED = ({"qb", "qayib"}, {"ie", "istirak"}, {"bal", "qiymet"}, {"yekun", "final"}, {"araliq", "midterm"})
_SYNONYMS = {word: family - {word} for family in _RELATED for word in family}
_PERSONAL = re.compile(r"(?:lar|ler)?[iu]?m(?:[aeiu]|d[ae]n?|[iu]n)?$")
_ACTIONS = frozenset("redakte tesdiq saxla yarat gonder yaz yukle duzelis qaytar imtina".split())


def search_words(text):
    folded = clean_query(text).casefold().replace("ə", "e").replace("ı", "i")
    folded = "".join(c for c in unicodedata.normalize("NFKD", folded) if not unicodedata.combining(c))
    folded = _SYMBOLS.sub(lambda m: "pinkod" if m[0].startswith("pin") else m[0][0] + m[0][-1], folded)
    return [_DIGRAPHS.sub(lambda m: _DIGRAPH[m[0]], word) for word in _WORDS.findall(folded)]


@lru_cache(maxsize=8192)
def _root(word):
    for base in _ROOTS_BY_INITIAL.get(word[:2], ()):
        if word.startswith(base):
            ending = word[len(base) :]
            if not ending or _NOUN_END.fullmatch(ending) or _VERB_END.fullmatch(ending):
                return _ROOT[base]
    return word


def _one_edit(a, b):
    """One insertion, deletion, substitution or adjacent transposition."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    if len(a) != len(b):
        return a[i:] == b[i + 1 :]
    return a[i + 1 :] == b[i + 1 :] or (
        i + 1 < len(a) and a[i] == b[i + 1] and a[i + 1] == b[i] and a[i + 2 :] == b[i + 2 :]
    )


def _quality(term, term_root, word):
    if term == word:
        return 7
    root = _root(word)
    if term_root == root:
        return 7 if _PERSONAL.search(term) and _PERSONAL.search(word) else 6
    if root in _SYNONYMS.get(term_root, ()):
        return 4
    if len(term) >= 4 and word.startswith(term) and term_root == term and term not in _ROOT:
        return 4
    if min(len(term), len(word)) >= 5 and term.isalpha() and word.isalpha() and _one_edit(term, word):
        return 3
    return 0


def _field(text):
    return tuple(word for word in search_words(text) if word not in _STOP)


@dataclass(frozen=True, slots=True)
class SearchHit:
    guide: Guide
    chapter_start: float | None = None
    chapter_title: str = ""


def _index(guide):
    return (
        _field(guide.title),
        _field(guide.topic),
        _field(guide.aliases),
        tuple(_field(step) for step in guide.steps),
        tuple((_field(c["title"]), c["title"], c["start"]) for c in guide.chapters),
    )


@lru_cache(maxsize=None)
def _builtin_index(key):
    return _index(BUILTIN_BY_KEY[key])


def rank_guides(visible_guides, query):
    """Keep catalogue order on ties. Only examine the effective guides supplied by the caller."""
    query = clean_query(query[:MAX_QUERY_LENGTH]).strip()
    if not query:
        return [SearchHit(guide) for guide in visible_guides]
    terms = tuple(dict.fromkeys(_field(query)))
    if not terms or len(terms) > 12 or any(len(term) > MAX_TOKEN_LENGTH for term in terms):
        return []
    roots = tuple(_root(term) for term in terms)
    n = len(terms)

    @lru_cache(maxsize=8192)
    def matches(word):
        return tuple((i, quality) for i, term in enumerate(terms) if (quality := _quality(term, roots[i], word)))

    @lru_cache(maxsize=4096)
    def evidence(words):
        best = [0] * n
        expected = set()
        phrase = False
        for word in words:
            following = set()
            for i, quality in matches(word):
                if quality > best[i]:
                    best[i] = quality
                if quality >= 5 and (i == 0 or i in expected):
                    if i + 1 == n:
                        phrase = True
                    else:
                        following.add(i + 1)
            expected = following
        return tuple(best), phrase

    def evaluate(guide):
        if BUILTIN_BY_KEY.get(guide.key) is guide:
            title, topic, aliases, steps, chapters = _builtin_index(guide.key)
        else:
            title, topic, aliases, steps, chapters = _index(guide)
        scores = [0] * n
        heading = [0] * n
        bonus = 0
        for text, weight in ((title, 10), (topic, 8), (aliases, 6)):
            qualities, phrase = evidence(text)
            for i, quality in enumerate(qualities):
                scores[i] = max(scores[i], quality * weight)
                if weight >= 8:
                    heading[i] = max(heading[i], quality)
            if all(qualities):
                # A whole topic such as “Nəticələrim” is stronger than a
                # passing mention of the result at the end of another question.
                whole_heading = phrase and len(text) == n and weight >= 8
                bonus = max(bonus, weight * (3 + 3 * phrase) + 32 * whole_heading)
        for step in steps:
            qualities, _ = evidence(step)
            for i, quality in enumerate(qualities):
                scores[i] = max(scores[i], quality * 3)
        score = sum(scores) + bonus if all(scores) else 0
        best_chapter, start, label = (0, 0, False), None, ""
        for words, chapter_title, timestamp in chapters:
            qualities, phrase = evidence(words)
            coverage = sum(bool(q) for q in qualities)
            if not coverage or not all(a or b for a, b in zip(qualities, scores)):
                continue
            # A partial chapter can refine a subject in the title, e.g.
            # “sillabusu redaktə” → the editing step of the syllabus lesson.
            contextual = all(a or b for a, b in zip(qualities, heading)) and any(
                q >= 5 and (not heading[i] or roots[i] in _ACTIONS) for i, q in enumerate(qualities)
            )
            if coverage < n and not contextual:
                continue
            chapter_bonus = 20 * (coverage == n) + 10 * phrase
            candidate = sum(max(value, q * 7) for value, q in zip(scores, qualities)) + max(bonus, chapter_bonus)
            score = max(score, candidate)
            specificity = (coverage, sum(qualities) + 3 * phrase, timestamp == guide.start)
            if specificity > best_chapter:
                best_chapter, start, label = specificity, timestamp, chapter_title
        return score, SearchHit(guide, start, label)

    ranked = [result for guide in visible_guides if (result := evaluate(guide))[0]]
    ranked.sort(key=lambda result: result[0], reverse=True)
    return [hit for _, hit in ranked]
