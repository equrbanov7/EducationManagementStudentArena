"""`state/<pin>/` OYUNÇU sorğusunun bütün oyunçular üçün EYNİ olan hissəsinə qısa ortaq keş (PERF-1 F-11).

300 oyunçu WS qopuq olanda hər 3 s-də bir sorğu atır (~100 sorğu/s); hər cavabın sual sayı, sual + variantlar
və «sualdan əvvəlki sıra» hissəsi eyni (sessiya, sual) üçün eynidir. Burada YALNIZ sual ərzində dəyişməyən
hissələr keşlənir:

* sual sayı (seçilmiş sual siyahısı boşdursa imtahanın sual sayı);
* cari sual + variantları (``ExamQuestion`` nümunəsi, pickle ilə — hər sorğu öz nüsxəsini alır);
* sualdan ƏVVƏLKİ sıra xəritəsi (açarda cavab verməli oyunçu sayı da var — oyunçu çıxarılanda/qoşulanda
  açar dəyişir).

Canlı sayğaclar (cavab verməli oyunçu sayı, cavab verənlərin sayı) və oyunçunun ÖZ sətri / cavabı HƏR
sorğuda bazadan oxunur. Açar sessiyanın PK-sı + vəziyyəti + sual indeksi + sualın başlama anı ilə qurulur:
keçid (növbəti sual, reveal, yenidən başlama) yeni açar deməkdir; köhnə dəyər TTL ilə ölür.

RLS: oxu artıq ``bypass_rls()`` içindədir və oyunçu tokeni keşdən ƏVVƏL yoxlanılır; dəyər yalnız həmin
sessiyanın oyunçularına göstərilən (sessiya-ictimai) məlumatdır, açar qlobal-unikal sessiya PK-sı daşıyır.
Host sorğusu keşdən KEÇMİR (aparıcı həmişə təzə görür). Redis əlçatmazdırsa hesablama birbaşa gedir.
"""

from __future__ import annotations

from typing import Any, Callable

from core.cache import _PREFIX, cached_or_compute

#: Ortaq hissənin ömrü (saniyə). Dəyərlər sual ərzində sabitdir; TTL yalnız keçiddən sonra köhnə açarı
#: təmizləmək və nadir redaktəni (sual mətni) tez göstərmək üçündür.
SHARED_TTL_SECONDS = 2


def _key(session, part: str) -> str:
    started = session.question_started_at.isoformat() if session.question_started_at else "-"
    return f"{_PREFIX}:live_exam:poll:{session.pk}:{session.state}:{int(session.current_index or 0)}:{started}:{part}"


def shared(session, part: str, compute: Callable[[], Any], *, enabled: bool = True) -> Any:
    """``part`` üçün keşlənmiş dəyər; yoxdursa ``compute()`` (``None`` keşlənmir). ``enabled=False`` → birbaşa."""
    if not enabled:
        return compute()
    return cached_or_compute(_key(session, part), compute, timeout=SHARED_TTL_SECONDS)


__all__ = ["SHARED_TTL_SECONDS", "shared"]
