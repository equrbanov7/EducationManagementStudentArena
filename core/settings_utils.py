"""Runtime setting oxunuşu üçün təhlükəsiz çeviricilər (Faza 5, audit 2026-07-02).

Əvvəllər eyni `_safe_int_setting` / `_safe_float_setting` funksiyaları
`core/middleware.py` və `apps/exams/services/attempts.py` daxilində ayrı-ayrı
nüsxə idi. settings dəyəri yanlış tipdə/formатda olsa belə istisna atmadan
default-a düşür və opsional minimum sərhədini tətbiq edir.
"""

from django.conf import settings


def safe_int_setting(name: str, default: int, *, minimum: int | None = None) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def safe_float_setting(name: str, default: float, *, minimum: float | None = None) -> float:
    try:
        value = float(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value
