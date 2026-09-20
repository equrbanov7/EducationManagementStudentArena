"""Mətn axtarışı üçün DÖZÜMLÜ regex qurucusu (sahib 2026-09-21).

* ``tolerant_regex(token)`` — az/ing klaviatura fərqlərinə dözümlü sinif
  (``ı``/``i``/``İ``/``I``, ``ə``/``e``, ``ş``/``s``, ``ç``/``c``, ``ğ``/``g``,
  ``ö``/``o``, ``ü``/``u``); regex metasimvolları qaçırılır.
* ``loose_spaces=True`` — simvollar arasında ixtiyari boşluğa icazə verir:
  «234k» → «234 K», «233KE» → «233 KE» (qrup adı axtarışı).

Yalnız şablon mətni qaytarır; çağıran onu ``__iregex`` ilə işlədir (PostgreSQL
``~*``). Hər iki registr sinifdə açıq yazılır ki, nəticə DB lokal case-folding
qaydasından asılı olmasın.
"""

from __future__ import annotations

import re

MAX_TOKENS = 4
MAX_QUERY_LENGTH = 120

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


def tolerant_regex(token: str, *, loose_spaces: bool = False) -> str:
    """«ismayil» → ``[iıİI][sşSŞ]may[iıİI]l``; ``loose_spaces`` ilə simvollar arası ``\\s*``."""
    chars = [ch for ch in str(token or "") if not (loose_spaces and ch.isspace())]
    parts = [_CLASS_FOR_CHAR.get(ch, re.escape(ch)) for ch in chars]
    return r"\s*".join(parts) if loose_spaces else "".join(parts)
