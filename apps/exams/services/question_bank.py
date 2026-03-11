import re


def normalize_question_text(text: str) -> str:
    if not text:
        return ""
    normalized = text.strip().lower()
    return re.sub(r"\s+", " ", normalized)


__all__ = [
    "normalize_question_text",
]
