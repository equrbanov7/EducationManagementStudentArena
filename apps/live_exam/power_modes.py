"""Canlı oyunun «güc rejimləri» (sahib 2026-11-10): 💣 Bomba rejimi, ×2 Xal rejimi, final rəqs şousu.

* ``bomb_mode`` — açıq olanda NƏŞR olunan hər sual bomba sualıdır (per-sual ``bomb_questions``
  siyahısı ilə BİRLİKDƏ: hər ikisi «və ya» ilə birləşir). Səhv / qismən cavab bu oyundakı xalı
  sıfırlayır (bax :mod:`apps.live_exam.bombs`).
* ``double_mode`` — açıq olanda nəşr olunan sualda qazanılan xal ``DOUBLE_MULTIPLIER`` dəfə artır
  (düzgün və qismən düzgün cavab; səhv cavab onsuz da 0 xaldır). Bomba ilə birlikdə işləyə bilər:
  düzgün → 2×, səhv → sıfırlanma.
* ``finale_dance`` — final səhnəsində avatarların rəqs şousu (yalnız təqdimat qatı, bal yoxdur).

ƏDALƏT QAYDASI. Rejim bayraqları sual NƏŞR olunanda digər qaydalarla birgə ``_question_config``-da
dondurulur (``domain.question_config``). Aparıcı rejimi oyun gedərkən dəyişsə:

* cari suala HƏLƏ heç bir cavab qəbul olunmayıbsa (giriş sayı, oxunma vaxtı, pəncərənin ilk anları) —
  dondurulmuş qayda yenilənir və hamıya ``question_modifiers`` hadisəsi gedir (ekranlar dərhal dəyişir);
* ən azı bir cavab varsa — cari sualın qaydası DƏYİŞMİR (hamı eyni qayda ilə qiymətləndirilir), yeni
  dəyər növbəti sualdan keçərlidir; aparıcıya «növbəti sualdan» bildirişi qaytarılır.

Rəsmi imtahan / nəticə modelləri burada oxunmur və yazılmır.
"""

from __future__ import annotations

from typing import Any

DOUBLE_MULTIPLIER = 2

#: Ayarlar → dondurulan qayda açarları.
POWER_MODE_SETTING_KEYS = ("bomb_mode", "double_mode")


def apply_double_points(config, score: dict[str, Any]) -> dict[str, Any]:
    """``double_mode`` dondurulmuşsa qazanılan xalı ``DOUBLE_MULTIPLIER`` dəfə artırır (yerində).

    Yalnız müsbət xal çarpılır — səhv cavab 0 qalır, bomba sıfırlanması sonra tətbiq olunur.
    """
    if not getattr(config, "is_double", False):
        score["points_multiplier"] = 1
        return score
    awarded = int(score.get("awarded_points") or 0)
    score["awarded_points"] = awarded * DOUBLE_MULTIPLIER if awarded > 0 else 0
    score["points_multiplier"] = DOUBLE_MULTIPLIER
    return score


def modifier_fields(config) -> dict[str, Any]:
    """Reveal / nəticə paketlərinə əlavə olunan rejim sahələri."""
    is_double = bool(getattr(config, "is_double", False))
    return {
        "is_bomb": bool(getattr(config, "is_bomb", False)),
        "is_double": is_double,
        "points_multiplier": DOUBLE_MULTIPLIER if is_double else 1,
    }


def build_question_modifiers_payload(question_id: int, config, *, applied: bool) -> dict[str, Any]:
    """``question_modifiers`` hadisəsi (host + oyunçu play qrupları və HTTP cavabı).

    ``applied=False`` — cari suala cavab var, qayda dəyişmədi (dəyər növbəti sualdan).
    """
    from django.utils import timezone

    return {
        "type": "question_modifiers",
        "server_time": timezone.now().isoformat(),
        "question_id": int(question_id),
        "applied": bool(applied),
        **modifier_fields(config),
    }
