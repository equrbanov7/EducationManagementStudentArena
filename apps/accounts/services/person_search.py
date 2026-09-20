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

from django.db.models import Q

from core.search_text import MAX_QUERY_LENGTH, MAX_TOKENS, tokens_of, tolerant_regex  # noqa: F401


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
