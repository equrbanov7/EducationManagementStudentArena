"""
Sualın oyunçuya ÇATMASI (LXNET 2026-10-02) — zəif şəbəkədə ədalət və host sayğacı.

Problem: zəif internetli telefon sualı gec alır (TCP təkrar ötürmə, Wi-Fi qopması, yenidən
qoşulma). Sual cavab pəncərəsi açılandan SONRA çatırsa, köhnə qaydada sürət balı ``answer_starts_at``-dan
ölçülürdü → gecikmə birbaşa bal itkisi idi.

Qayda (yalnız server vaxtı, klient saatına etibar YOXDUR):

* **Çatma sübutu** — serverin öz saatı ilə, İLK qeyd qalib gəlir (``cache.add``):
  (a) oyunçunun play socket-i ``question_published``-i ötürdükdən sonra klientin ``seen`` təsdiqi
      serverə çatan an (yalnız bu consumer-in ötürdüyü sual üçün);
  (b) ``GET /live/state/<pin>/`` sualı həmin oyunçuya verdiyi an (WS qopuq olanda HTTP yolu).
* **Fərdi anker** — sübut ``answer_starts_at``-dan GEC-dirsə, sürət balı üçün vaxt
  ``answer_starts_at + min(gecikmə, tavan)``-dan ölçülür. Tavan:
  ``min(LATE_DELIVERY_CAP_SECONDS, LATE_DELIVERY_CAP_FRACTION × pəncərə)`` (15 s sualda 3 s).
  Sübut yoxdursa / vaxtında çatıbsa — dəyişiklik YOXDUR (köhnə davranış).
* **Pəncərə dəyişmir** — cavab yenə ``[answer_starts_at, ends_at + 0.5 s]`` arasında və yalnız
  ``question`` vəziyyətində qəbul olunur; reveal vaxtı, düzgün cavab, sızma qaydaları toxunulmazdır.

Sui-istifadə sərhədi: təsdiqi qəsdən gecikdirən (DevTools) klient ən çox «tavan» qədər əlavə
düşünmə vaxtı qazanır; maksimal bal (vaxt əmsalı 1.0) yenə də eynidir və intro zamanı onsuz da
əlçatandır. Adi klient təsdiqi avtomatik göndərir. Keş əlçatmazdırsa anker = köhnə qayda.
"""

from __future__ import annotations

import logging
from datetime import datetime

from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

#: Gec çatma kompensasiyasının mütləq tavanı (saniyə) və pəncərəyə nisbəti.
LATE_DELIVERY_CAP_SECONDS = 3.0
LATE_DELIVERY_CAP_FRACTION = 0.2
#: Çatma qeydlərinin keşdə ömrü — bir sualın ömründən (≤ ~2 dəq) xeyli uzun.
SEEN_TTL_SECONDS = 30 * 60


def _seen_key(pin: str, question_id: int, player_id: int) -> str:
    return f"live_exam:seen:{pin}:{int(question_id)}:{int(player_id)}"


def _count_key(pin: str, question_id: int) -> str:
    return f"live_exam:seen_count:{pin}:{int(question_id)}"


def record_question_seen(pin: str, question_id: int, player_id: int, *, at: datetime | None = None) -> int | None:
    """İlk çatma sübutunu yazır. Bu çağırış YAZDISA → sualı alan oyunçu sayı, əks halda ``None``."""
    at = at or timezone.now()
    count_key = _count_key(pin, question_id)
    try:
        if not cache.add(_seen_key(pin, question_id, player_id), at.isoformat(), SEEN_TTL_SECONDS):
            return None
        cache.add(count_key, 0, SEEN_TTL_SECONDS)
        return int(cache.incr(count_key))
    except ValueError:  # sayğac açarı yoxdur (evict / dummy keş) — host sayğacı sadəcə yenilənmir
        return None
    except Exception:  # keş əlçatmazdır — ədalət ankeri sadəcə işləmir (köhnə qayda)
        logger.warning("live delivery record failed", extra={"pin": pin, "question_id": question_id})
        return None


def question_seen_at(pin: str, question_id: int, player_id: int) -> datetime | None:
    try:
        raw = cache.get(_seen_key(pin, question_id, player_id))
    except Exception:
        return None
    value = parse_datetime(raw) if isinstance(raw, str) else None
    return value if isinstance(value, datetime) else None


def received_count(pin: str, question_id: int) -> int:
    try:
        return int(cache.get(_count_key(pin, question_id)) or 0)
    except Exception:
        return 0


def late_delivery_cap_ms(total_ms: int) -> int:
    return max(0, int(min(LATE_DELIVERY_CAP_SECONDS * 1000, LATE_DELIVERY_CAP_FRACTION * max(0, int(total_ms)))))


def late_delivery_shift_ms(*, seen_at: datetime | None, answer_starts_at: datetime, total_ms: int) -> int:
    """Sürət balı ankerinin sürüşməsi (ms): sual pəncərə açılandan sonra çatıbsa, tavanla."""
    if seen_at is None or answer_starts_at is None or seen_at <= answer_starts_at:
        return 0
    late_ms = int((seen_at - answer_starts_at).total_seconds() * 1000)
    return max(0, min(late_ms, late_delivery_cap_ms(total_ms)))


def build_delivery_progress_payload(*, question_id: int, received: int) -> dict:
    """Yalnız HOST-a: sualı neçə telefon aldı («27/30 aldı»)."""
    return {
        "type": "delivery_progress",
        "server_time": timezone.now().isoformat(),
        "question_id": int(question_id),
        "received_count": int(received),
    }
