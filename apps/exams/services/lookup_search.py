"""İmtahan formasındakı fənn / qrup seçicilərinin axtarışı — «tam formada» (sahib 2026-10-21).

Sahib: «Orda fənn search edərkən və ya qrup — tam formada işləsin, yəni qrupun, fənnin adını aralı yazarkən də
problem olmasın, rahatlıqla tapılsın.»

Kanonik qatlama ``core.search_text``-dədir (az/ing hərfləri: ə/e/a, ı/i/İ/I, ö/o, ü/u, ş/s, ç/c, ğ/g; söz
başlanğıcı; kod rejimi). Əvvəlki sorğular iki yerdə yarımçıq idi:

* fənn: ``ad_bütün_tokenlər | kod_bütün_tokenlər`` — «634 Qrafik» (634 kodda, Qrafik adda) heç nə tapmırdı;
* qrup: etiket «634 ing — Dizayn (Qrafik)»-dur, amma ixtisas (ana qrup) adı axtarılmırdı;
* «634Qrafik» (bitişik rəqəm+hərf), «Qrafik/dizayn», «qrafik-dizayn» tokenləri adda tapılmırdı.

Bu modul ``core.search_text``-in ictimai köməkçiləri üzərində TOKEN-SAHƏ sorğusu qurur:

* sorğu hərf və rəqəm qaçışlarına bölünür (boşluq, ``/``, ``-``, ``_``, ``.``, mötərizə və s. ayırıcıdır;
  rəqəm↔hərf keçidi də) — söz sırası fərq etmir;
* hər token sahələrdən HƏR HANSI birində olmalıdır (tokenlər arası VƏ);
* ad sahələrində token SÖZ BAŞLANĞICINDA (hərf tokeni hərf olmayan simvoldan, rəqəm tokeni rəqəm olmayan
  simvoldan sonra — «Qrafik634»-də də tapılır); ≥ 4 simvollu token adda ayırıcıya dözümlüdür («qrafikdizayn» →
  «Qrafik dizayn»); qısa token kod rejiminə düşmür («vo» «Devops»-u tapmır — 2026-10-08 qaydası qalır);
* kod sahələrində token istənilən yerdə (``core.search_text.code_regex``).

Nəticə köhnə sorğu ilə VƏ YA birləşdirilir — əvvəl tapılan heç nə itmir.
"""

from __future__ import annotations

import re

from django.db.models import Q

from core.search_text import MAX_QUERY_LENGTH, MAX_TOKEN_LENGTH, code_regex, fold_regex, tolerant_q

#: Bölünmüş tokenlərin yuxarı həddi (``core.search_text.MAX_TOKENS`` boşluq tokenləri üçündür).
MAX_SPLIT_TOKENS = 6
_RUN_RE = re.compile(r"[^\W\d_]+|\d+")
#: Az hərfləri sinifdə açıq — nəticə DB ctype-dan asılı olmasın (``core.search_text.WORD_START`` kimi).
_LETTER_START = r"(?:^|[^A-Za-zəƏıİöÖüÜğĞşŞçÇ])"
_DIGIT_START = r"(?:^|[^0-9])"
_COMPACT_NAME_MIN = 4


def split_tokens(query) -> list[str]:
    """«634Qrafik / dizayn» → ``["634", "Qrafik", "dizayn"]`` (ən çoxu ``MAX_SPLIT_TOKENS``)."""
    text = str(query or "")[:MAX_QUERY_LENGTH].replace("̇", "")
    runs = [run[:MAX_TOKEN_LENGTH] for run in _RUN_RE.findall(text)]
    return runs[:MAX_SPLIT_TOKENS]


def word_token_regex(token: str) -> str:
    """Ad sahəsi üçün token şablonu (söz başlanğıcı; uzun tokendə ayırıcıya dözümlü)."""
    if token.isdigit():
        return _DIGIT_START + fold_regex(token)
    return _LETTER_START + fold_regex(token, compact=len(token) >= _COMPACT_NAME_MIN)


def token_field_q(query, word_fields=(), code_fields=()) -> Q | None:
    """Hər bölünmüş token ``word_fields`` (söz başlanğıcı) və ya ``code_fields`` (istənilən yer) birində."""
    tokens = split_tokens(query)
    word_fields, code_fields = tuple(word_fields or ()), tuple(code_fields or ())
    if not tokens or not (word_fields or code_fields):
        return None
    combined = Q()
    for token in tokens:
        any_field = Q()
        for field in word_fields:
            any_field |= Q(**{f"{field}__iregex": word_token_regex(token)})
        for field in code_fields:
            any_field |= Q(**{f"{field}__iregex": code_regex(token)})
        combined &= any_field
    return combined


def subject_lookup_q(query) -> Q | None:
    """Fənn (registrar.Subject): ad (söz başlanğıcı) + kod — tokenlər iki sahə arasında paylana bilər."""
    new_q = token_field_q(query, ("name",), ("code",))
    if new_q is None:
        return None
    # Kodun ayırıcıya dözümlü bitişik forması («QKU1203» → «QKU-1203») — əvvəlki qayda.
    return new_q | (tolerant_q(query, (), compact_fields=("code",)) or Q(pk__in=[]))


def unit_lookup_q(query) -> Q | None:
    """Qrup reyestri (OrgUnit GROUP): ad + ixtisas (ana qrup) adı + kod; köhnə kompakt qayda ilə VƏ YA."""
    new_q = token_field_q(query, ("name", "parent__name"), ("code",))
    if new_q is None:
        return None
    return new_q | (tolerant_q(query, ("name", "code"), compact=True) or Q(pk__in=[]))


def legacy_group_lookup_q(query) -> Q | None:
    """Köhnə imtahan kohortu (StudentGroup): ad; köhnə kompakt qayda ilə VƏ YA."""
    new_q = token_field_q(query, ("name",), ())
    if new_q is None:
        return None
    return new_q | (tolerant_q(query, ("name",), compact=True) or Q(pk__in=[]))


def lookup_match(query, *, words=(), codes=()) -> bool:
    """``token_field_q``-nun yaddaş əkizi (testlər / yaddaşdakı siyahılar üçün)."""
    tokens = split_tokens(query)
    if not tokens:
        return True
    word_texts = [str(text).replace("̇", "") for text in words if text]
    code_texts = [str(text).replace("̇", "") for text in codes if text]

    def _hit(token):
        word_rx = re.compile(word_token_regex(token), re.IGNORECASE)
        code_rx = re.compile(code_regex(token), re.IGNORECASE)
        return any(word_rx.search(t) for t in word_texts) or any(code_rx.search(t) for t in code_texts)

    return all(_hit(token) for token in tokens)


__all__ = [
    "MAX_SPLIT_TOKENS",
    "legacy_group_lookup_q",
    "lookup_match",
    "split_tokens",
    "subject_lookup_q",
    "token_field_q",
    "unit_lookup_q",
    "word_token_regex",
]
