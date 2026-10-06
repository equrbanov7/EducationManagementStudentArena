"""``apps.announcements`` PUBLIC API — «Elanlar» (sahib tələbi, 2026-10-06).

Digər modullar (accounts kabineti, badge borusu, base.html) YALNIZ bu fasaddan istifadə edir.

══════════════════════════════════════════════════════════════════════════════
MODEL VƏ AXINLAR
══════════════════════════════════════════════════════════════════════════════
* ``Announcement`` — başlıq, xülasə, düz mətn (``linebreaks``/``urlize``, HTML saxlanılmır),
  kateqoriya, prioritet, «sancılmış», vəziyyət (qaralama → dərc → arxiv), görünmə pəncərəsi
  (``publish_at`` … ``expires_at``), ``deadline_at`` («son tarix», geri sayım), ``show_as_popup``,
  auditoriya (rol ailələri × bölmələr), «Müraciət et» konfiqurasiyası, sənədlər.
* ``AnnouncementReceipt`` — istifadəçi × elan: ``popup_seen_at`` / ``read_at`` / ``applied_at``.

AUDİTORİYA: ``students`` / ``teachers`` / ``staff`` ailələri (rol adına görə) × bölmələr
(boş → bütün təşkilat; doludursa istifadəçinin bölməsi seçilmişin özü və ya alt-ağacıdır —
tələbə üçün qrupu, müəllim/heyət üçün üzvlüyün ``scope_unit``-i).

POPUP (birdəfəlik): aktiv, ünvanlanmış, ``show_as_popup`` elan qəbzində ``popup_seen_at``
yoxdursa növbəti TAM səhifə açılışında göstərilir (imtahan səhifələrində heç vaxt).
Gözləyən yoxdursa SIFIR sorğu (``Organization.settings`` xülasəsi + sessiya işarəsi).

İDARƏ: ``announcement.manage`` (struktur əhatəsinə tabe; dekan yalnız öz fakültəsinə).

SİLMƏ (2026-10-07): menecer əhatəsindəki İSTƏNİLƏN elanı silə bilər. Qəbzsiz qaralama
birdəfəlik silinir; qalanı YUMŞAQ (``is_deleted``) — bütün istifadəçi səthlərindən çıxır,
qəbzlər/sənədlər/yaradılmış müraciətlər saxlanılır, «Silinmişlər» filtrindən bərpa olunur
(→ qaralama). Silmə və bərpa audit jurnalına düşür.

══════════════════════════════════════════════════════════════════════════════
KABİNET (accounts) ÜÇÜN
══════════════════════════════════════════════════════════════════════════════
* ``PROFILE_SECTION = "announcements"`` — hər təşkilat üzvünün bölməsi; qeydiyyat 4 yerdə:
  ``sections_api.SECTION_PARTIALS`` / ``AJAX_SAFE_SECTIONS``, ``profile.html``
  ``data-ajax-sections`` və ``rbac_sections`` (``section_visible``).
* ``section_visible(user, organization)`` — menyu görünürlüyü (sıfır sorğu).
* ``badge_payload(user, organization, allowed_sections)`` → ``{"announcements_unread": n}``
  (badges API; aktiv elan yoxdursa sıfır sorğu, varsa Redis keşi 120 s).
* Şablon tag-ları (``{% load announcements_tags %}``): ``announcements_panel``,
  ``announcements_unread_count``, ``announcements_popup``.
"""

from __future__ import annotations

from .constants import PERM_MANAGE, PROFILE_SECTION
from .services.access import can_manage
from .services.popup import badge_count, pending_popups

BADGE_KEY = "announcements_unread"


def section_visible(user, organization) -> bool:
    """«Elanlar» — təşkilat konteksti olan hər daxil olmuş istifadəçi (boş siyahı da məlumatdır)."""
    return bool(organization is not None and user is not None and getattr(user, "is_authenticated", False))


def badge_payload(user, organization, allowed_sections) -> dict:
    """Sidebar sayğac borusu üçün (``profile_badges_api``) — bölmə görünmürsə boş lüğət."""
    if PROFILE_SECTION not in (allowed_sections or ()):
        return {}
    try:
        return {BADGE_KEY: int(badge_count(user, organization) or 0)}
    except Exception:  # noqa: BLE001 — badge heç vaxt səhifəni sındırmır
        import logging

        logging.getLogger(__name__).exception("announcements badge failed")
        return {}


__all__ = [
    "BADGE_KEY",
    "PERM_MANAGE",
    "PROFILE_SECTION",
    "badge_count",
    "badge_payload",
    "can_manage",
    "pending_popups",
    "section_visible",
]
