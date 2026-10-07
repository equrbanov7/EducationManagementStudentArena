"""Periodik cəhd sweep-ləri üçün ortaq qoruyucular (2026-09-13 infra auditi).

İki 60 saniyəlik Celery sweep-i (``exams.expire_overdue_attempts`` →
``sweep_overdue_attempts``, ``exams.expire_stale_resumed_attempts`` →
``sweep_expired_resume_windows``) əvvəl iki zəiflik daşıyırdı:

* **P2-6 — kilidsiz kor yazı.** Sweep ``.iterator()`` ilə namizədləri gəzib
  ``mark_finished()`` çağırırdı; ``mark_finished`` ``save(update_fields=[status,
  ...])`` ilə yazır. Tələbənin təhvil yolu isə sətri ``select_for_update(of=("self",))``
  ilə kilidləyib ``submitted`` yazır. Sweep kilid götürmədiyi üçün «tələbə təhvil
  verdi → sweep köhnə obyektlə ``expired`` yazdı» ardıcıllığı mümkün idi
  (last-writer-wins) + ``schedule_journal_sync`` iki dəfə. Həll: hər cəhd öz
  ``transaction.atomic()``-ində ``select_for_update(of=("self",), skip_locked=True)``
  ilə YENİDƏN oxunur və status filtri təkrar tətbiq olunur — tələbə sətri
  tutubsa sweep onu ötür (növbəti dəqiqə yenidən baxar), sweep tutubsa tələbə
  gözləyib ``is_finished`` görür.
* **P3-14 — overlap.** Worker ``-c 4`` ilə işləyir; böyük gündə sweep 60 s-dən
  uzun çəksə beat növbəti icranı da növbəyə qoyur və iki sweep paralel gəzir.
  ``cache.add`` (Redis ``SET NX``) ilə 55 s-lik qlobal kilid: kilid tutulubsa
  ikinci icra heç nə etmədən çıxır.

Fon işi tutumu 2026-10-07: kilid TTL-i 55 s-dir, amma bir icranın müddəti
namizəd sayına bağlı idi. Final imtahanında cəhd başına ~54 sorğu (jurnal yazısı
+ bildiriş) ≈ 48 ms → 5 000 vaxtı bitmiş cəhd ≈ 240 s. 55 s-dən sonra kilid
düşür, beat hər dəqiqə yeni sweep başladır və ``celery`` növbəsinin 4 slotunun
hamısı üst-üstə düşən sweep-lərlə dolur (OTP məktubları, bildirişlər gözləyir;
300 s hard limit isə icranı ortada öldürür). İndi qlobal icra
``SWEEP_TIME_BUDGET_SECONDS`` (defolt 45 s < TTL) büdcəsi ilə işləyir: büdcə
bitəndə dayanır, qalan namizədləri növbəti dəqiqənin icrası götürür (köhnədən
yeniyə, ``pk`` sırası ilə).
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager, contextmanager, nullcontext

from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from apps.exams.models import ExamAttempt

logger = logging.getLogger(__name__)

#: Beat intervalı 60 s-dir; kilid ondan qısa olmalıdır ki, sweep crash etsə
#: (kilid silinməsə) növbəti icra maksimum bir dövr gecikin.
SWEEP_LOCK_TTL_SECONDS = 55
SWEEP_LOCK_KEY_PREFIX = "lock:sweep:"
#: Qlobal icranın vaxt büdcəsi — overlap kilidinin TTL-indən qısa olmalıdır.
SWEEP_TIME_BUDGET_SECONDS = 45


def sweep_time_budget() -> float:
    """Qlobal sweep büdcəsi (s); ``EXAM_SWEEP_TIME_BUDGET_SECONDS`` ilə dəyişdirilə bilər."""
    try:
        value = float(getattr(settings, "EXAM_SWEEP_TIME_BUDGET_SECONDS", SWEEP_TIME_BUDGET_SECONDS))
    except (TypeError, ValueError):
        value = SWEEP_TIME_BUDGET_SECONDS
    return max(0.0, min(value, SWEEP_LOCK_TTL_SECONDS - 5))


@contextmanager
def sweep_overlap_lock(name: str, ttl: int = SWEEP_LOCK_TTL_SECONDS):
    """Qlobal sweep üçün overlap kilidi — ``acquired`` boolean-ı verir (P3-14).

    Kilid alınmayıbsa çağıran dərhal 0 qaytarmalıdır. Sahiblik tokeni ilə
    silinir ki, TTL bitəndən sonra başqa icranın kilidini yanlışlıqla
    açmayaq. DummyCache (test defoltu) ``add``-ı həmişə True qaytarır —
    yəni kilid orada şəffafdır.
    """
    key = f"{SWEEP_LOCK_KEY_PREFIX}{name}"
    token = uuid.uuid4().hex
    try:
        acquired = bool(cache.add(key, token, timeout=ttl))
    except Exception as exc:  # pragma: no cover - cache əlçatmazdır
        # Kilid ala bilməmək sweep-i dayandırmamalıdır (fail-open): cəhdlərin
        # bitirilməsi kilidin özündən vacibdir; sətir kilidi onsuz da qoruyur.
        logger.warning("sweep overlap kilidi alınmadı (%s): %s", key, exc)
        acquired = True
    if not acquired:
        logger.info("sweep %s: əvvəlki icra hələ işləyir — ötürülür", name)
    try:
        yield acquired
    finally:
        if acquired:
            try:
                if cache.get(key) == token:
                    cache.delete(key)
            except Exception:  # pragma: no cover
                pass


def finish_attempts_under_row_lock(
    queryset,
    *,
    narrow: Callable[[object], object],
    select_related: tuple[str, ...],
    action: Callable[[ExamAttempt], bool],
    scope: Callable[[], AbstractContextManager] | None = None,
    time_budget: float | None = None,
) -> int:
    """Namizədləri bir-bir sətir kilidi altında yenidən oxuyub ``action`` tətbiq et (P2-6).

    ``narrow`` — namizəd filtri (status və s.); həm ilkin ID siyahısına, həm də
    kilid altındakı təkrar oxumaya tətbiq olunur ki, bu arada dəyişən sətir
    (tələbə təhvil verib) yenidən yazılmasın. ``skip_locked`` — başqa
    tranzaksiyanın (tələbənin təhvili) tutduğu sətir ötürülür.
    ``action`` cəhdi bitiribsə True qaytarır. Bitirilən say qaytarılır.

    Audit 2026-09-28 EX28-05: ``scope`` — hər DB addımını (namizəd sorğusu və HƏR
    cəhd ayrıca) saran kontekst fabriki (Celery sweep-i üçün
    ``rls_worker_atomic() + bypass_rls()``). Əvvəl bütün sweep bir xarici
    ``rls_worker_atomic``-də idi: ``RLS_TRANSACTION_SCOPED`` açıq olanda daxili
    ``atomic`` savepoint-ə çevrilir və emal olunmuş bütün cəhdlərin sətir
    kilidləri sweep bitənə qədər qalırdı. İndi hər cəhd öz real tranzaksiyasında
    commit olunur (kilid dərhal buraxılır, jurnal ``on_commit``-i dərhal işləyir),
    bir cəhdin xətası loglanır və digərlərini dayandırmır.

    ``time_budget`` (s) — verilibsə hər cəhddən SONRA yoxlanır: büdcə bitibsə
    qalan namizədlər növbəti icraya qalır (ən azı bir cəhd həmişə işlənir ki,
    irəliləyiş olsun). Namizədlər ``pk`` sırası ilə — köhnə cəhdlər əvvəl.
    """
    scope = scope or nullcontext
    deadline = time.monotonic() + time_budget if time_budget is not None else None
    # ID-lər əvvəlcədən materiallaşdırılır: hər cəhd öz tranzaksiyasında
    # işlənir, açıq server-side kursor + daxili atomic bloklar qarışmasın.
    with scope():
        candidate_ids = list(narrow(queryset).order_by("pk").values_list("pk", flat=True))
    finished = 0
    for index, attempt_id in enumerate(candidate_ids):
        if index and deadline is not None and time.monotonic() >= deadline:
            logger.warning(
                "sweep: time budget %.0fs exhausted after %d/%d candidate(s); the rest go to the next run",
                time_budget,
                index,
                len(candidate_ids),
            )
            break
        try:
            with scope(), transaction.atomic():
                attempt = (
                    narrow(queryset.select_for_update(of=("self",), skip_locked=True))
                    .select_related(*select_related)
                    .filter(pk=attempt_id)
                    .first()
                )
                # None: ya artıq bitirilib (status filtri kəsdi), ya da sətir başqa
                # tranzaksiyada kilidlidir — hər iki halda toxunmuruq.
                if attempt is not None and action(attempt):
                    finished += 1
        except Exception:  # noqa: BLE001 — bir cəhdin xətası bütün sweep-i dayandırmasın (EX28-05)
            logger.exception("sweep: attempt %s could not be processed", attempt_id)
    return finished
