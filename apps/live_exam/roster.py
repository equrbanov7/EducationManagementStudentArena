"""
Oyunçu siyahısı qaydaları — kim oyundadır, kim cari suala cavab verməlidir (2026-10-08).

* **Gec qoşulma (L3)** — oyun başlayandan sonra qoşulan oyunçunun ``active_from_index``-i növbəti
  sualın indeksidir: cari sualda cavab vermir, onun cavabını görmür, «hamı cavab verdi» sayına
  (``eligible``) düşmür. Lobbidə qoşulanlar üçün 0.

Sorğular say/siyahı üçün TƏK sorğudur (qoşulma kilidinin qısalığı və host keçidləri üçün vacibdir).
"""

from __future__ import annotations

from django.db.models import QuerySet, Subquery

from apps.live_exam.models import LivePlayer, LiveSession


def late_join_index(session: LiveSession) -> int:
    """Yeni oyunçunun ``active_from_index``-i: lobbidə 0, oyun gedərkən NÖVBƏTİ sual."""
    if session.state in (LiveSession.STATE_QUESTION, LiveSession.STATE_REVEAL):
        return int(session.current_index or 0) + 1
    return 0


def is_pending(player, session: LiveSession) -> bool:
    """Oyunçu hələ cari sualda iştirak etmir (gec qoşulub, növbəti sualı gözləyir)."""
    if session.state not in (LiveSession.STATE_QUESTION, LiveSession.STATE_REVEAL):
        return False
    return int(getattr(player, "active_from_index", 0) or 0) > int(session.current_index or 0)


def eligible_players(session_id: int, question_index: int) -> QuerySet:
    """``question_index`` sualına cavab verməli olan oyunçular."""
    return LivePlayer.objects.filter(session_id=session_id, active_from_index__lte=int(question_index or 0))


def eligible_count_for_current(session_id: int) -> int:
    """Sessiyanın CARİ sualı üçün cavab verməli oyunçu sayı (bir sorğu; sessiya alt-sorğuda)."""
    current_index = LiveSession.objects.filter(pk=session_id).values("current_index")[:1]
    return LivePlayer.objects.filter(session_id=session_id, active_from_index__lte=Subquery(current_index)).count()
