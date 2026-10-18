"""Publik səhifədə göstərilən fakt açarları və etiketləri.

``DocumentSeal.payload["facts"]`` — ``[[açar, dəyər], ...]`` siyahısıdır; etiket buraxılış anında DEYİL,
baxış anında ziyarətçinin dilində qurulur. Siyahıda olmayan açar publik səhifədə GÖSTƏRİLMİR (yeni sənəd
növü əlavə ediləndə açar burada açıq-aydın icazələndirilməlidir — təsadüfi PII sızmasın).
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

_CTX = "verification.fact"

FACT_LABELS = {
    "program": pgettext_lazy(_CTX, "İxtisas"),
    "degree": pgettext_lazy(_CTX, "Təhsil pilləsi"),
    "credits": pgettext_lazy(_CTX, "Toplanmış kredit"),
    "gpa": pgettext_lazy(_CTX, "Kumulyativ ÜOMG"),
    "ects": pgettext_lazy(_CTX, "Məzuniyyət yükü (ECTS)"),
    "document_number": pgettext_lazy(_CTX, "Sənəd №"),
}


def labelled(facts) -> list[tuple[str, str]]:
    """``[[açar, dəyər]]`` → ``[(etiket, dəyər)]`` — yalnız icazəli açarlar, boş dəyərlər atılır."""
    out = []
    for item in facts or []:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        key, value = item
        if key in FACT_LABELS and value not in (None, ""):
            out.append((str(FACT_LABELS[key]), str(value)))
    return out


__all__ = ["FACT_LABELS", "labelled"]
