"""Test köməkçisi: tələbə formunun göndərdiyi option dəyəri (Audit 2026-09-28 EX28-01).

``take_exam`` artıq xam ``option.id`` deyil, attempt-ə bağlı token qəbul edir.
"""

from apps.exams.services.option_tokens import option_token


def option_value(attempt, option) -> str:
    """``attempt`` üçün ``option``-un POST dəyəri (brauzerin göndərəcəyi token)."""
    return option_token(getattr(attempt, "pk", attempt), getattr(option, "pk", option))


__all__ = ["option_value"]
