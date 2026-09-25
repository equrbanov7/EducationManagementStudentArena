"""Mətn axtarışının KANONİK köməkçisi — az/ing hərflərinə və ayırıcılara dözümlü (sahib 2026-09-21, 2026-09-26).

Sahib (2026-09-26): «qruplar və bütün search yerlərində az dili hərfləri ilə
yazmağı nəzərə al, en dilə olan nəticə də gəlsin; qrup «234 K ing»dir,
«234king» və s. kombinasiyada da işləsin».

Yeganə ictimai API
==================
* ``tolerant_q(query, fields, *, compact=False, compact_fields=())`` → ``Q | None``
  — sorğu boşluqla TOKENLƏRƏ bölünür (ən çoxu ``MAX_TOKENS``), tokenlər arasında
  VƏ, hər token sahələr arasında VƏ YA; uyğunluq ``__iregex`` (PostgreSQL ARE
  ``~*``). ``compact=True`` bütün sahələri, ``compact_fields`` isə yalnız
  sadalananları «kod» rejimində yoxlayır (qarışıq sahələr üçün).
* ``fold_regex(token, *, compact=False)`` — bir token üçün şablon mətni;
  ``code_regex(token)`` — kod sahəsi üçün (``compact`` yalnız «kod kimi» tokendə, aşağıya bax).
* ``tolerant_match(query, text, *, compact=False)`` — eyni qayda Python-da
  (yaddaşdakı siyahılar üçün); ``static/js/search_fold.js`` (``EMSSearch``) bunun
  brauzer əkizidir — paritet testi ``core/tests/test_search_text_js_parity.py``.

Hərf qatlama (hər iki istiqamət, registrsiz; siniflər AÇIQ yazılır ki, nəticə
DB collation/ctype-dan asılı olmasın)
------------------------------------------------------------------------------
* ``i``/``ı``/``İ``/``I`` — bir sinif;
* ``e``/``ə``; ``ə`` həm də ``a`` ilə (pasport transliterasiyası «Əliyev» →
  «Aliyev»): sorğuda ``a`` → ``[aAəƏ]``, ``ə`` → ``[əƏeEaA]``, ``e`` → ``[eEəƏ]``
  (``e`` ↔ ``a`` YOX);
* ``ş``/``s`` və ``ş`` ↔ «sh»; ``ç``/``c`` və ``ç`` ↔ «ch»; ``ğ``/``g`` və
  ``ğ`` ↔ «gh»;
* ``ö``/``o``, ``ü``/``u``;
* ``x`` ↔ «kh» — QƏBUL EDİLİB («Xəlilov» ↔ «Khalilov»): «kh» az mətnində demək
  olar ki, yoxdur, yalan-müsbət riski azdır.
* ``q`` ↔ ``g`` («Qasımov» ↔ «Gasimov») və ``c`` ↔ ``j`` («Cəfərov» ↔
  «Jafarov») — QƏSDƏN YOX: tək hərf səviyyəsində çox geniş sinif verir
  (hər ``g`` hər ``q``-nu tapar); sahib istəsə ayrıca qərar.

Kod rejimi (``compact``)
------------------------
Qrup adı, fənn kodu, tələbə nömrəsi, otaq kimi sahələr üçün: sorğudakı
ayırıcılar (boşluq, ``-``, ``_``, ``.``, ``/``) atılır, simvollar arasında isə
ixtiyari sayda ayırıcıya icazə verilir — «234king», «234 king», «234-K-ing»,
«234k ing» hamısı «234 K ing»i, «234k1» «234 K-1»i tapır.

Yalan-müsbətə qarşı: kod rejimi yalnız «kod kimi» tokenə tətbiq olunur — içində
rəqəm var, ya da ən azı ``COMPACT_MIN_CHARS`` (4) simvoldur. Qısa hərf tokeni
(«PA», «vb») kod sahəsində də adi (bitişik) axtarılır — yoxsa «pa» «Qrup A»dakı
«p A»nı tapardı. Çox tokenli sorğu kod sahələrində həm də BİTİŞDİRİLMİŞ halda
yoxlanır («234 kin g» → «234king» → «234 K ing»).

Yaddaşda (``tolerant_match``/JS) mətndəki birləşən nöqtə U+0307 atılır:
``"İ".lower()`` → «i̇» olur və əks halda «ismayil» «i̇smayıl»ı tapmazdı.

Təhlükəsizlik: regex metasimvolları qaçırılır; sorğu ``MAX_QUERY_LENGTH``,
token ``MAX_TOKEN_LENGTH`` ilə kəsilir; şablonda iç-içə kəmiyyət yoxdur (yalnız
simvol sinfi + ``[ayırıcı]*``), PostgreSQL ARE (DFA) üçün ReDoS riski yoxdur.
İndeks: ``~*`` B-tree işlətmir; lazım olarsa ``pg_trgm`` GIN indeksi regex-i
dəstəkləyir (ayrıca miqrasiya qərarı).
"""

from __future__ import annotations

import re

from django.db.models import Q

MAX_TOKENS = 4
MAX_QUERY_LENGTH = 120
MAX_TOKEN_LENGTH = 40
COMPACT_MIN_CHARS = 4

# Kod rejimində simvollar arasında ixtiyari ayırıcı (PG ARE, Python re və JS üçün eyni sintaksis).
SEPARATOR_CLASS = r"[\s._/-]"
_SEPARATORS = frozenset(" \t\r\n\f\v._/-")

# Tək hərf → sinif (açıq, hər iki registr).
_SINGLE = {
    "a": "[aAəƏ]",
    "ə": "[əƏeEaA]",
    "e": "[eEəƏ]",
    "i": "[iıİI]",
    "ı": "[iıİI]",
    "s": "[sSşŞ]",
    "ş": "(?:[sS][hH]|[sSşŞ])",
    "c": "[cCçÇ]",
    "ç": "(?:[cC][hH]|[cCçÇ])",
    "g": "[gGğĞ]",
    "ğ": "(?:[gG][hH]|[gGğĞ])",
    "o": "[oOöÖ]",
    "ö": "[oOöÖ]",
    "u": "[uUüÜ]",
    "ü": "[uUüÜ]",
    "x": "(?:[xX]|[kK][hH])",
}
# İki hərfli ingilis yazılışı → az hərfi (sorğuda «sh» → «ş» də tapılsın).
_DIGRAPHS = {
    "sh": "(?:[sS][hH]|[şŞ])",
    "ch": "(?:[cC][hH]|[çÇ])",
    "gh": "(?:[gG][hH]|[ğĞ])",
    "kh": "(?:[kK][hH]|[xX])",
}
_LOWER = {"İ": "i", "I": "i", "Ə": "ə", "Ş": "ş", "Ç": "ç", "Ğ": "ğ", "Ö": "ö", "Ü": "ü"}


def _low(ch: str) -> str:
    """Türk/az registri: «I» → «i» (``str.lower`` «İ»-ni «i̇»yə çevirir — işlətmirik)."""
    return _LOWER.get(ch) or (ch.lower() if len(ch.lower()) == 1 else ch)


def _char_pattern(ch: str) -> str:
    low = _low(ch)
    if low in _SINGLE:
        return _SINGLE[low]
    upper = low.upper()
    if low.isalpha() and len(upper) == 1 and upper != low:
        return f"[{low}{upper}]"
    return re.escape(ch)


def tokens_of(query: str) -> list[str]:
    """Boşluqla bölünmüş, boş olmayan tokenlər (ən çoxu ``MAX_TOKENS``, hər biri ``MAX_TOKEN_LENGTH``)."""
    text = str(query or "").strip()[:MAX_QUERY_LENGTH]
    return [token[:MAX_TOKEN_LENGTH] for token in text.split() if token][:MAX_TOKENS]


def fold_regex(token: str, *, compact: bool = False) -> str:
    """Bir token üçün dözümlü şablon: «is» → ``[iıİI][sSşŞ]``; ``compact`` ilə simvollar arası ``[ayırıcı]*``."""
    chars = [ch for ch in str(token or "")[:MAX_TOKEN_LENGTH] if not (compact and ch in _SEPARATORS)]
    parts: list[str] = []
    index = 0
    while index < len(chars):
        pair = "".join(_low(ch) for ch in chars[index : index + 2])
        if pair in _DIGRAPHS:
            parts.append(_DIGRAPHS[pair])
            index += 2
            continue
        parts.append(_char_pattern(chars[index]))
        index += 1
    return f"{SEPARATOR_CLASS}*".join(parts) if compact else "".join(parts)


def tolerant_regex(token: str, *, loose_spaces: bool = False) -> str:
    """Geriyə uyğunluq: ``fold_regex`` (``loose_spaces`` = ``compact``)."""
    return fold_regex(token, compact=loose_spaces)


def _compact_eligible(token: str) -> bool:
    """Kod rejimi yalnız rəqəmli və ya ≥ ``COMPACT_MIN_CHARS`` simvollu tokenə (qısa hərf tokeni bitişik qalır)."""
    chars = [ch for ch in str(token or "") if ch not in _SEPARATORS]
    return any(ch in "0123456789" for ch in chars) or len(chars) >= COMPACT_MIN_CHARS


def code_regex(token: str) -> str:
    """Kod sahəsi üçün token şablonu: uyğun tokendə ``compact``, qısa hərf tokenində adi (``tolerant_q`` bunu işlədir)."""
    return fold_regex(token, compact=_compact_eligible(token))


def _glued(tokens: list[str]) -> str | None:
    """Çox tokenli sorğunun bitişik (kod) şablonu; tək token və ya uyğunsuz → ``None``."""
    if len(tokens) < 2:
        return None
    glued = "".join(tokens)[:MAX_TOKEN_LENGTH]
    return fold_regex(glued, compact=True) if _compact_eligible(glued) else None


def tolerant_q(query: str, fields=(), *, compact: bool = False, compact_fields=()) -> Q | None:
    """Tokenləşmiş, dözümlü Q; sorğu və ya sahə yoxdursa ``None``.

    ``fields`` — ``first_name``, ``student__last_name`` kimi lookup prefiksləri (hər birinə
    ``__iregex``); ``compact=True`` onları kod rejimində yoxlayır. ``compact_fields`` — əlavə,
    HƏMİŞƏ kod rejimində yoxlanan sahələr (qrup adı + şəxs adı kimi qarışıq axtarış).
    """
    tokens = tokens_of(query)
    plain = tuple(fields or ())
    coded = tuple(compact_fields or ())
    if compact:
        plain, coded = (), plain + coded
    if not tokens or not (plain or coded):
        return None
    combined = Q()
    for token in tokens:
        any_field = Q()
        if plain:
            pattern = fold_regex(token)
            for field in plain:
                any_field |= Q(**{f"{field}__iregex": pattern})
        if coded:
            pattern = code_regex(token)
            for field in coded:
                any_field |= Q(**{f"{field}__iregex": pattern})
        combined &= any_field
    glued = _glued(tokens) if coded else None
    if glued:
        any_glued = Q()
        for field in coded:
            any_glued |= Q(**{f"{field}__iregex": glued})
        combined = combined | any_glued
    return combined


def tolerant_match(query: str, *texts, compact: bool = False) -> bool:
    """Yaddaşda uyğunluq (``tolerant_q`` ilə eyni qayda): hər token mətnlərdən hər hansı birində.

    Boş sorğu → ``True`` (süzgəc yoxdur).
    """
    tokens = tokens_of(query)
    if not tokens:
        return True
    haystack = [str(text).replace("\u0307", "") for text in texts if text not in (None, "")]

    def _hit(pattern: str) -> bool:
        rx = re.compile(pattern, re.IGNORECASE)
        return any(rx.search(text) for text in haystack)

    if all(_hit(code_regex(token) if compact else fold_regex(token)) for token in tokens):
        return True
    glued = _glued(tokens) if compact else None
    return bool(glued) and _hit(glued)
