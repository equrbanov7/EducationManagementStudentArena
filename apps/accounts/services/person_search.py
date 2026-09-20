"""Şəxs axtarışı — ad/soyad/istifadəçi adı üzrə DÖZÜMLÜ uyğunluq (sahib 2026-09-21).

Sahibin şikayəti: «Ad Soyad» (boşluqla) yazanda tapılmır; az/ing klaviatura
səhvləri (ı↔i, ə↔e, ş↔s, ç↔c, ğ↔g, ö↔o, ü↔u) nəticəni sıfırlayır — adam var,
tək-tək baxanda tapılır.

Qayda:
* sorğu boşluqla TOKENLƏRƏ bölünür (ən çoxu ``MAX_TOKENS``); hər token
  sahələrdən HƏR HANSI birində tapılmalıdır, tokenlər arasında VƏ — «Aydan
  Alyarova», «Alyarova Aydan», «aydan.alyarova» hamısı eyni adamı tapır;
* hər token diakritikaya dözümlü regex-ə çevrilir: ``i``/``ı``/``İ``/``I`` bir
  sinifdir, ``e``/``ə``, ``s``/``ş``, ``c``/``ç``, ``g``/``ğ``, ``o``/``ö``,
  ``u``/``ü`` də eləcə — «Huseynov» «Hüseynov»u, «Ismayil» «İsmayıl»ı tapır;
* uyğunluq ``__iregex`` ilə gedir (PostgreSQL ``~*``); regex metasimvolları
  qaçırılır, ona görə istifadəçi girişi şablonu poza bilmir.

Yalnız Q obyekti qurur — hansı sahələrə tətbiq olunacağını çağıran verir
(``view_as``, qlobal axtarış, tələbə reyestri…).
"""

from __future__ import annotations

import re

from django.db.models import Q

MAX_TOKENS = 4
MAX_QUERY_LENGTH = 120

#: Bir-birinin əvəzinə yazılan hərf qrupları (hər iki registr açıq yazılır ki,
#: nəticə DB-nin lokal case-folding qaydasından asılı olmasın).
_EQUIVALENTS = (
    "iıİI",
    "eəEƏ",
    "sşSŞ",
    "cçCÇ",
    "gğGĞ",
    "oöOÖ",
    "uüUÜ",
)
_CLASS_FOR_CHAR = {ch: f"[{group}]" for group in _EQUIVALENTS for ch in group}


def tokens_of(query: str) -> list[str]:
    """Boşluqla bölünmüş, boş olmayan tokenlər (ən çoxu ``MAX_TOKENS``)."""
    text = str(query or "").strip()[:MAX_QUERY_LENGTH]
    return [token for token in text.split() if token][:MAX_TOKENS]


def tolerant_regex(token: str) -> str:
    """«ismayil» → ``[iıİI][sşSŞ]m a y [iıİI] l`` (mətn, ``re`` qaçırılmış)."""
    return "".join(_CLASS_FOR_CHAR.get(ch, re.escape(ch)) for ch in token)


def person_q(query: str, fields: tuple[str, ...] | list[str]) -> Q | None:
    """Tokenləşmiş, diakritikaya dözümlü Q; sorğu boşdursa ``None``.

    ``fields`` — ``first_name``, ``student__last_name`` kimi lookup prefiksləri
    (hər birinə ``__iregex`` əlavə olunur).
    """
    tokens = tokens_of(query)
    if not tokens or not fields:
        return None
    combined = Q()
    for token in tokens:
        pattern = tolerant_regex(token)
        any_field = Q()
        for field in fields:
            any_field |= Q(**{f"{field}__iregex": pattern})
        combined &= any_field
    return combined
