"""Ad moderasiyası (nalayiq söz / ifadə filtri) — shared kernel paketi (2026-09-30).

* ``detector`` / ``normalize`` / ``wordlist`` — SAF (Django-suz) detektor;
  lüğətlər ``data/*.txt`` fayllarındadır;
* ``enforcement`` — view / servislər üçün ``screen_names`` (audit izi + rate-limit).

``enforcement`` Django modellərinə toxunduğu üçün TƏNBƏL ixrac olunur: saf
detektoru import etmək app registry-ni tələb etmir.
"""

from .detector import ProfanityMatch, contains_profanity, find_profanity, mask_value

_LAZY = {
    "NameRejection",
    "PROFANITY_RESOURCE_TYPE",
    "rate_limited_message",
    "rejection_message",
    "screen_name",
    "screen_names",
}


def __getattr__(name):
    if name in _LAZY:
        from . import enforcement

        return getattr(enforcement, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "NameRejection",
    "PROFANITY_RESOURCE_TYPE",
    "ProfanityMatch",
    "contains_profanity",
    "find_profanity",
    "mask_value",
    "rate_limited_message",
    "rejection_message",
    "screen_name",
    "screen_names",
]
