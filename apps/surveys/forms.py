"""Cavab formasının SERVER tərəfli yoxlaması (JS yalnız rahatlıqdır).

Sahə adı: ``q_<code>``. Likert 1–5, bal 1–10 tam ədəd; mətn ``TEXT_MAX_LENGTH``-ə
qədər (kəsilmir — uzun mətn xəta verir ki, tələbə nəyin itdiyini bilsin).
"""

from __future__ import annotations

from django.utils.translation import pgettext

from .constants import SCORE_RANGES, TEXT_MAX_LENGTH, QuestionKind

_CTX = "surveys.form"


def field_name(question) -> str:
    return f"q_{question.code}"


def validate_answers(questions, data):
    """``(cleaned, errors, values)``.

    ``cleaned`` — ``[(question, score | None, text)]`` (yalnız dolu cavablar);
    ``errors`` — ``{code: mesaj}``; ``values`` — formanın təkrar göstərilməsi üçün xam dəyərlər.
    """
    cleaned, errors, values = [], {}, {}
    for question in questions:
        raw = (data.get(field_name(question)) or "").strip()
        values[question.code] = raw
        if question.kind == QuestionKind.TEXT:
            if not raw:
                if question.required:
                    errors[question.code] = pgettext(_CTX, "Bu sual məcburidir.")
                continue
            if len(raw) > TEXT_MAX_LENGTH:
                errors[question.code] = pgettext(_CTX, "Mətn %(limit)s simvoldan uzun ola bilməz.") % {
                    "limit": TEXT_MAX_LENGTH
                }
                continue
            cleaned.append((question, None, raw))
            continue
        low, high = SCORE_RANGES.get(question.kind, (1, 5))
        if not raw:
            if question.required:
                errors[question.code] = pgettext(_CTX, "Bir cavab seçin.")
            continue
        try:
            score = int(raw)
        except ValueError:
            score = None
        if score is None or not (low <= score <= high):
            errors[question.code] = pgettext(_CTX, "Cavab %(low)s ilə %(high)s arasında olmalıdır.") % {
                "low": low,
                "high": high,
            }
            continue
        cleaned.append((question, score, ""))
    return cleaned, errors, values
