"""Sorğu qurucusu (2026-09-30) — ümumi sorğu cavabının SERVER yoxlaması (JS yalnız rahatlıqdır).

Sahə adı ``q_<code>`` (müəllim formasındakı kimi); çox seçim — eyni adla bir neçə dəyər.
Qaytarılan ``cleaned`` sətri: ``(question, number, choices, text)`` —
Likert 1–5 / NPS 0–10 / bəli 1, xeyr 0 → ``number``; tək/çox seçim → ``choices`` (sabit açarlar);
qısa/uzun mətn → ``text``. Boş, məcburi olmayan sual yazılmır.
"""

from __future__ import annotations

from django.utils.translation import pgettext

from ..constants import NUMBER_RANGES, SHORT_TEXT_MAX_LENGTH, TEXT_MAX_LENGTH, QuestionKind

_CTX = "surveys.form"


def field_name(question) -> str:
    return f"q_{question.code}"


def _values(data, name) -> list:
    if hasattr(data, "getlist"):
        raw = data.getlist(name)
    else:
        raw = data.get(name)
        raw = raw if isinstance(raw, list) else ([] if raw in (None, "") else [raw])
    return [str(item).strip() for item in raw if str(item).strip()]


def choice_keys(question) -> list:
    options = question.options if isinstance(question.options, dict) else {}
    return [item.get("key") for item in options.get("choices") or [] if isinstance(item, dict) and item.get("key")]


def _number(question, raw, errors):
    low, high = NUMBER_RANGES[question.kind]
    try:
        number = int(raw)
    except ValueError:
        number = None
    if number is None or not low <= number <= high:
        errors[question.code] = pgettext(_CTX, "Cavab %(low)s ilə %(high)s arasında olmalıdır.") % {
            "low": low,
            "high": high,
        }
        return None
    return number


def _multi(question, picked, errors):
    keys = choice_keys(question)
    if any(key not in keys for key in picked) or len(set(picked)) != len(picked):
        errors[question.code] = pgettext(_CTX, "Seçim etibarsızdır — səhifəni yeniləyin.")
        return None
    options = question.options if isinstance(question.options, dict) else {}
    low, high = options.get("min"), options.get("max")
    if low and len(picked) < low:
        errors[question.code] = pgettext(_CTX, "Ən azı %(n)s seçim edin.") % {"n": low}
        return None
    if high and len(picked) > high:
        errors[question.code] = pgettext(_CTX, "Ən çoxu %(n)s seçim edə bilərsiniz.") % {"n": high}
        return None
    return [key for key in keys if key in picked]  # sabit sıra


def validate_answers(questions, data):
    """``(cleaned, errors, values)`` — ``values`` formanın təkrar göstərilməsi üçün xam dəyərlər."""
    cleaned, errors, values = [], {}, {}
    for question in questions:
        picked = _values(data, field_name(question))
        kind = question.kind
        if kind == QuestionKind.MULTI:
            values[question.code] = picked
        else:
            values[question.code] = picked[0] if picked else ""
        if not picked:
            if question.required:
                errors[question.code] = (
                    pgettext(_CTX, "Bu sual məcburidir.")
                    if kind in (QuestionKind.TEXT, QuestionKind.SHORT_TEXT)
                    else pgettext(_CTX, "Bir cavab seçin.")
                )
            continue
        if kind in (QuestionKind.TEXT, QuestionKind.SHORT_TEXT):
            text = picked[0]
            limit = SHORT_TEXT_MAX_LENGTH if kind == QuestionKind.SHORT_TEXT else TEXT_MAX_LENGTH
            if len(text) > limit:
                errors[question.code] = pgettext(_CTX, "Mətn %(limit)s simvoldan uzun ola bilməz.") % {"limit": limit}
                continue
            cleaned.append((question, None, [], text))
        elif kind == QuestionKind.SINGLE:
            if len(picked) != 1 or picked[0] not in choice_keys(question):
                errors[question.code] = pgettext(_CTX, "Seçim etibarsızdır — səhifəni yeniləyin.")
                continue
            cleaned.append((question, None, [picked[0]], ""))
        elif kind == QuestionKind.MULTI:
            keys = _multi(question, picked, errors)
            if keys is not None:
                cleaned.append((question, None, keys, ""))
        elif kind in NUMBER_RANGES:
            number = _number(question, picked[0], errors)
            if number is not None:
                cleaned.append((question, number, [], ""))
        else:  # naməlum növ — heç vaxt yazılmır
            errors[question.code] = pgettext(_CTX, "Seçim etibarsızdır — səhifəni yeniləyin.")
    return cleaned, errors, values


def draft_values(data) -> dict:
    """Qaralama JSON-u (``{name: value | [values]}``) — yalnız ``q_`` sahələri, ölçü məhdud."""
    result = {}
    if not isinstance(data, dict):
        return result
    for name, value in list(data.items())[:200]:
        if not isinstance(name, str) or not name.startswith("q_") or len(name) > 70:
            continue
        if isinstance(value, list):
            result[name] = [str(item)[:TEXT_MAX_LENGTH] for item in value[:40]]
        elif value is not None:
            result[name] = str(value)[:TEXT_MAX_LENGTH]
    return result
