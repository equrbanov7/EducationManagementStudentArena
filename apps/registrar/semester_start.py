"""Semestrin başlanğıcı — «ondan əvvəlki tarixə jurnalda heç nə yazılmır» qaydasının ortaq köməkçiləri.

Sahib 2026-11-08 / 2026-11-14: «ayın 15-dən tez jurnala nə isə yazıla bilməz». Dərs yaradılması / tarixinin
dəyişməsi :func:`apps.registrar.gradebook_lessons.ensure_not_before_period`-dədir; bu modul həmin qaydanı dərsdən
başqa yazı yollarına (xana yazısı, sənədli bal düzəlişi, köhnə sistemdən delta köçürməsi) daşıyır.
"""

from __future__ import annotations

import datetime


def period_start(offering) -> datetime.date | None:
    """Açılışın dövrünün başlanğıc tarixi (yoxdursa ``None``)."""
    start = getattr(getattr(offering, "period", None), "start_date", None)
    if isinstance(start, str):
        try:
            return datetime.date.fromisoformat(start[:10])
        except ValueError:
            return None
    return start


def before_start(offering, day) -> datetime.date | None:
    """``day`` semestrin başlanğıcından əvvəldirsə başlanğıc tarixi, əks halda ``None``."""
    start = period_start(offering)
    return start if (start and day and day < start) else None


def mark_message(start) -> str:
    return (
        f"Semestr {start:%d.%m.%Y} tarixində başlayıb — bu tarixdən əvvəlki dərsə qeyd yazmaq olmaz. "
        "Dərs daha gec keçirilibsə, onu düzgün tarixlə daxil edin."
    )


__all__ = ["before_start", "mark_message", "period_start"]
