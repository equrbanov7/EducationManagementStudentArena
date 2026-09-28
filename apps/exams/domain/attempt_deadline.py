"""İmtahan cəhdinin vaxt sərhədləri — deadline, təhvil grace-i, yazı pəncərəsi.

Audit 2026-09-28:

* **EX28-04** — ``EXAM_SUBMIT_GRACE_SECONDS`` (EX-05 düzəlişi) yalnız POST yolunda
  tətbiq olunurdu; 60 s-lik sweep və istənilən GET (nəticə, ikinci tab, reload)
  cəhdi deadline-ın ELƏ ANINDA bağlayırdı → client-in deadline-dan 1,5 s sonra
  göndərdiyi son təhvil/autosave «already_finished» alıb itirdi. İndi bütün
  «tənbəl» (lazy) bağlanmalar və sweep ``now − grace`` anına görə qərar verir;
  grace pəncərəsi daxilində cəhdi yalnız kilid altındakı POST yolu bağlaya bilər.
* **EX28-07** — ``deadline_at`` imtahanın ``end_datetime``-ını nəzərə almırdı:
  bitməyə bir dəqiqə qalmış başlayan tələbə pəncərə bağlanandan sonra da tam
  müddət yazırdı. İndi ``deadline = min(started_at + müddət, end_datetime)``.
  İstisna: zal (final-mərkəz) cəhdi (``room`` dolu) — biletli finalda vaxt
  pəncərəsini zal oturumu təyin edir (bax ``final_center.tickets``); həmçinin
  ``end_datetime``-dan SONRA başlamış cəhd (zal gecikməsi) kəsilmir.
  Müddətsiz imtahanda deadline yoxdur (``None``), amma ``end_datetime`` + grace
  keçəndən sonra yazı (POST) qəbul olunmur — ``write_window_closed``.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone


def submit_grace() -> timedelta:
    """Deadline-dan sonra kilidli POST yazısının hələ qəbul olunduğu pəncərə."""
    return timedelta(seconds=max(0, int(getattr(settings, "EXAM_SUBMIT_GRACE_SECONDS", 0) or 0)))


def lazy_expiry_cutoff(now=None):
    """Lazy bağlanma / sweep üçün müqayisə anı: ``now − grace`` (EX28-04)."""
    return (now or timezone.now()) - submit_grace()


def _window_end_applies(attempt) -> bool:
    """``end_datetime`` bu cəhdin yazı pəncərəsini kəsirmi (EX28-07)."""
    end = getattr(attempt.exam, "end_datetime", None)
    started = attempt.started_at
    if not end or not started or getattr(attempt, "room_id", None):
        return False
    return end > started


def attempt_deadline_at(attempt):
    """Cəhdin deadline-ı: ``min(started_at + müddət, end_datetime)``; müddətsizdə ``None``."""
    if not attempt.started_at:
        return None
    duration_minutes = getattr(attempt.exam, "total_duration_minutes", None)
    if not duration_minutes:
        return None
    deadline = attempt.started_at + timedelta(minutes=duration_minutes)
    if _window_end_applies(attempt):
        deadline = min(deadline, attempt.exam.end_datetime)
    return deadline


def write_window_closed(attempt, *, at_time) -> bool:
    """``at_time`` anında cəhdə yazı pəncərəsi bağlıdırmı.

    Müddətli imtahanda deadline-dır; müddətsizdə imtahanın ``end_datetime``-ı
    (EX28-07: əvvəl belə cəhd heç vaxt bağlanmırdı). Çağıran grace-i ``at_time``
    ilə verir (``lazy_expiry_cutoff``)."""
    deadline = attempt.deadline_at
    if deadline is not None:
        return at_time >= deadline
    return _window_end_applies(attempt) and at_time > attempt.exam.end_datetime


__all__ = [
    "attempt_deadline_at",
    "lazy_expiry_cutoff",
    "submit_grace",
    "write_window_closed",
]
