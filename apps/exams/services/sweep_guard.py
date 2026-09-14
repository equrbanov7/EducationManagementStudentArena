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
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from contextlib import contextmanager

from django.core.cache import cache
from django.db import transaction

from apps.exams.models import ExamAttempt

logger = logging.getLogger(__name__)

#: Beat intervalı 60 s-dir; kilid ondan qısa olmalıdır ki, sweep crash etsə
#: (kilid silinməsə) növbəti icra maksimum bir dövr gecikin.
SWEEP_LOCK_TTL_SECONDS = 55
SWEEP_LOCK_KEY_PREFIX = "lock:sweep:"


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
) -> int:
    """Namizədləri bir-bir sətir kilidi altında yenidən oxuyub ``action`` tətbiq et (P2-6).

    ``narrow`` — namizəd filtri (status və s.); həm ilkin ID siyahısına, həm də
    kilid altındakı təkrar oxumaya tətbiq olunur ki, bu arada dəyişən sətir
    (tələbə təhvil verib) yenidən yazılmasın. ``skip_locked`` — başqa
    tranzaksiyanın (tələbənin təhvili) tutduğu sətir ötürülür.
    ``action`` cəhdi bitiribsə True qaytarır. Bitirilən say qaytarılır.
    """
    # ID-lər əvvəlcədən materiallaşdırılır: hər cəhd öz tranzaksiyasında
    # işlənir, açıq server-side kursor + daxili atomic bloklar qarışmasın.
    candidate_ids = list(narrow(queryset).values_list("pk", flat=True))
    finished = 0
    for attempt_id in candidate_ids:
        with transaction.atomic():
            attempt = (
                narrow(queryset.select_for_update(of=("self",), skip_locked=True))
                .select_related(*select_related)
                .filter(pk=attempt_id)
                .first()
            )
            if attempt is None:
                # Ya artıq bitirilib (status filtri kəsdi), ya da sətir başqa
                # tranzaksiyada kilidlidir — hər iki halda toxunmuruq.
                continue
            if action(attempt):
                finished += 1
    return finished
