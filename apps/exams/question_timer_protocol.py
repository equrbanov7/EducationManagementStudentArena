"""Per-question timer protokolunun geriyə-uyğun versiya markeri."""

QUESTION_TIMER_PROTOCOL_KEY = "_protocol_version"
QUESTION_TIMER_PROTOCOL_VERSION = 2


def default_question_timing():
    """Yeni attempt-ləri strict server-timer protokoluna daxil et.

    Miqrasiyadan əvvəlki sətirlərin JSON-u boş qalır; beləliklə köhnə
    client/attempt geriyə-uyğun davranışı saxlayır, yeni attempt isə
    ``question-seen`` olmadan vaxtlı cavab yaza bilmir.
    """
    return {QUESTION_TIMER_PROTOCOL_KEY: QUESTION_TIMER_PROTOCOL_VERSION}


def uses_strict_question_timer(question_timing) -> bool:
    try:
        return int((question_timing or {}).get(QUESTION_TIMER_PROTOCOL_KEY, 0)) >= QUESTION_TIMER_PROTOCOL_VERSION
    except (TypeError, ValueError):
        return False


__all__ = [
    "QUESTION_TIMER_PROTOCOL_KEY",
    "QUESTION_TIMER_PROTOCOL_VERSION",
    "default_question_timing",
    "uses_strict_question_timer",
]
