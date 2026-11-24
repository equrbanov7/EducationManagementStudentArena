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

Sahib 2026-11-17 — fərdi əlavə vaxt: nəzarətçi texniki problemə görə BİR tələbəyə əlavə dəqiqə verə bilir
(``ExamAttempt.extra_time_seconds``, bax ``services/attempt_time_extension.py``). Əlavə vaxt hesablanmış
deadline-ın ÜSTÜNƏ gəlir (``end_datetime`` kəsimindən SONRA da) — yalnız həmin cəhdin vaxtı uzanır.
Bütün yollar (taymer, lazy bağlanma, sweep, POST kilidi) bu funksiyanı oxuyur.

Sahib 2026-11-20 («dayandırdığım tələbəni bərpa edəndə olmur»): müəllimin «Dayandır»ı (əl ilə pauza,
``supervision_manual_lock``) tələbənin günahı deyil — pauza vaxtı tələbədən getmir. Pauza davam edərkən
cəhd vaxta görə BAĞLANMIR (əvvəl 60 s-lik sweep pauzadakı cəhdi deadline-da «expired» edirdi və
«Bərpa et» artıq «İmtahan bitib» deyirdi); bərpada pauza müddəti əlavə vaxt kimi qaytarılır
(``services/supervision/actions.py``). Unudulmuş pauza sonsuz açıq qalmasın deyə tavan var:
deadline + ``MANUAL_PAUSE_MAX_SECONDS``.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

#: Əl ilə pauzanın vaxt saatını «dondura» biləcəyi maksimum (və bərpada qaytarılan pauza vaxtının tavanı).
MANUAL_PAUSE_MAX_SECONDS = 2 * 60 * 60


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
    # 2026-10-20 (sahib): müəllimin «Sınaq keç»i imtahanın tarix pəncərəsindən asılı deyil — yalnız öz müddəti.
    if getattr(attempt, "is_trial", False):
        return False
    return end > started


def extra_time(attempt) -> timedelta:
    """Nəzarətçinin bu cəhdə verdiyi əlavə vaxt (sahib 2026-11-17); yoxdursa sıfır."""
    return timedelta(seconds=max(0, int(getattr(attempt, "extra_time_seconds", 0) or 0)))


def attempt_deadline_at(attempt):
    """Cəhdin deadline-ı: ``min(started_at + müddət, end_datetime) + əlavə vaxt``; müddətsizdə ``None``."""
    if not attempt.started_at:
        return None
    duration_minutes = getattr(attempt.exam, "total_duration_minutes", None)
    if not duration_minutes:
        return None
    deadline = attempt.started_at + timedelta(minutes=duration_minutes)
    if _window_end_applies(attempt):
        deadline = min(deadline, attempt.exam.end_datetime)
    return deadline + extra_time(attempt)


def manual_pause_active(attempt) -> bool:
    """Cəhd hazırda müəllimin əl ilə pauzasındadırmı (nəzarət funksiyası açıq olduqda)."""
    from apps.exams.features import exam_supervision_enabled

    return bool(
        getattr(attempt, "supervision_manual_lock", False)
        and getattr(attempt, "supervision_status", "") == "locked"
        and exam_supervision_enabled()
    )


def _pause_allowance(attempt) -> timedelta:
    return timedelta(seconds=MANUAL_PAUSE_MAX_SECONDS) if manual_pause_active(attempt) else timedelta(0)


def time_limit_reached(attempt, *, at_time) -> bool:
    """``at_time`` anında cəhdin vaxtı bitibmi — əl ilə pauzada deadline tavan qədər «donur»."""
    deadline = attempt.deadline_at
    if deadline is None:
        return False
    return at_time >= deadline + _pause_allowance(attempt)


def write_window_closed(attempt, *, at_time) -> bool:
    """``at_time`` anında cəhdə yazı pəncərəsi bağlıdırmı.

    Müddətli imtahanda deadline-dır; müddətsizdə imtahanın ``end_datetime``-ı
    (EX28-07: əvvəl belə cəhd heç vaxt bağlanmırdı). Çağıran grace-i ``at_time``
    ilə verir (``lazy_expiry_cutoff``)."""
    deadline = attempt.deadline_at
    if deadline is not None:
        return at_time >= deadline + _pause_allowance(attempt)
    end = getattr(attempt.exam, "end_datetime", None)
    return _window_end_applies(attempt) and at_time > end + extra_time(attempt) + _pause_allowance(attempt)


__all__ = [
    "MANUAL_PAUSE_MAX_SECONDS",
    "attempt_deadline_at",
    "extra_time",
    "lazy_expiry_cutoff",
    "manual_pause_active",
    "submit_grace",
    "time_limit_reached",
    "write_window_closed",
]
