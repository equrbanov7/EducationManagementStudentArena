"""Mətnin plagiat müqayisəsi üçün NORMALLAŞDIRILMASI (Azərbaycan dilinə uyğun).

Addımlar (sıra vacibdir):
  1. NFKC — tam/yarım enli simvollar, liqaturalar vahid formaya;
  2. görünməz simvollar (zero-width, soft hyphen) atılır — köçürməni gizlətmək
     üçün sözlərin arasına qoyulan «boşluqsuz boşluqlar» təsirsiz qalır;
  3. Azərbaycan hərf registri: ``I → ı``, ``İ → i`` (Python ``lower()`` bunu
     səhv edir: ``İ`` → ``i̇``);
  4. kiçik hərf; Kiril «oxşar hərflər» (а, е, о, р, с, х, у…) Latın qarşılığına —
     latın mətnə kiril hərfi qatıb yoxlamanı aldatmaq işləmir; iki sənəd EYNİ
     qaydadan keçdiyi üçün rus dilli mətnlərin müqayisəsi də pozulmur;
  5. klaviatura variantları birləşdirilir: ``ə→e ı→i ş→s ç→c ğ→g ö→o ü→u``
     («ə» yerinə «e» yazmaq fərq yaratmır);
  6. qalan diakritik işarələr atılır, yalnız hərf/rəqəm TOKENLƏRİ saxlanılır
     (durğu işarələri və boşluq sayı nəticəyə təsir etmir).
"""

from __future__ import annotations

import re
import unicodedata

_INVISIBLE = dict.fromkeys(map(ord, "​‌‍‎‏⁠⁡⁢⁣﻿­"), None)

#: Kiril → Latın (vizual oxşar hərflər; kiçik hərf mərhələsindən SONRA tətbiq olunur).
_HOMOGLYPHS = str.maketrans(
    {
        "а": "a",
        "в": "b",
        "е": "e",
        "ё": "e",
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
        "ә": "e",
        "ү": "u",
        "ө": "o",
        "һ": "h",
        "ғ": "g",
        "ҹ": "c",
        "ҝ": "g",
        "ы": "i",
    }
)

#: Azərbaycan/Türk hərfləri → baza Latın hərfi.
_FOLD = str.maketrans({"ə": "e", "ı": "i", "ş": "s", "ç": "c", "ğ": "g", "ö": "o", "ü": "u"})

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def normalize_text(text) -> str:
    """Müqayisə forması: kiçik hərfli, işarəsiz, tək boşluqla ayrılmış tokenlər."""
    value = unicodedata.normalize("NFKC", str(text or ""))
    value = value.translate(_INVISIBLE)
    value = value.replace("İ", "i").replace("I", "ı")
    value = value.lower().translate(_HOMOGLYPHS).translate(_FOLD)
    value = "".join(ch for ch in unicodedata.normalize("NFKD", value) if not unicodedata.combining(ch))
    return " ".join(_TOKEN_RE.findall(value))


def words_of(normalized: str) -> list[str]:
    return normalized.split() if normalized else []


__all__ = ["normalize_text", "words_of"]
