"""
Oyunçu səhifələrinin dili — aparıcının «Dil» ayarı (2026-10-08).

Tənzimləmə çekməcəsindəki ``language`` (system/az/en/ru/tr) əvvəl heç yerdə tətbiq olunmurdu: müəllim
«AZ» seçsə də ingiliscə telefonlarda qoşulma / oyun səhifəsi ingiliscə, imtahan məzmunu və bəzi
mətnlər isə Azərbaycanca idi (qarışıq dil). İndi «system» deyilsə oyunçu səhifələri (qoşulma, gözləmə
otağı, oyun ekranı) və onların JSON mesajları həmin dildə qurulur. Əlavə sorğu yoxdur — sessiya
görünüş funksiyasında artıq yüklənib.
"""

from __future__ import annotations

from contextlib import nullcontext

from django.utils import translation

SESSION_LANGUAGES = frozenset({"az", "en", "ru", "tr"})


def session_language(session) -> str | None:
    """Aparıcının seçdiyi dil və ya ``None`` («system» — brauzer/istifadəçi dili)."""
    raw = getattr(session, "host_settings", None) or {}
    value = str(raw.get("language") or "").strip().lower() if isinstance(raw, dict) else ""
    return value if value in SESSION_LANGUAGES else None


def player_language(session):
    """``with player_language(session): …`` — sessiyanın dili (yoxdursa heç nə dəyişmir)."""
    language = session_language(session)
    return translation.override(language) if language else nullcontext()
