"""Tələbə jurnala yazılanda onun bitmiş imtahan nəticəsi o jurnala da düşür (sahib 2026-11-16).

Sahib: «qiymətləndirilmiş nəticəsi olan hər tələbənin nəticəsi öz səhifəsində görünsün, yeni jurnallarında da».
Bal jurnala yalnız cəhd bitəndə / yoxlananda / imtahan yenidən sinxronlaşanda yazılırdı; tələbə imtahandan SONRA
jurnala düşəndə (bərpa olunmuş qiyabi, yeni seçmə jurnalı, alt qrupa yerləşdirmə, qrupa sonradan gəlmə) nəticə
gəlmirdi və tələbə həmin fənnin kartında boş xana görürdü.

İndi registrar ``enrollments_activated`` siqnalı (commit-dən sonra, ``registrar.enrollment_events``) bu modula
``(tələbə, açılış, fənn)`` sətirlərini verir; tələbənin həmin fənn (və ya həmin jurnala bağlı imtahan) üzrə RƏSMİ
cəhdləri canlı körpü ilə EYNİ yoldan yenidən yazılır (``sync_midterm_attempt`` / ``sync_final_attempt`` — gizli nəticə,
sənədli düzəliş, bağlı jurnal və s. qaydalar olduğu kimi). İş request-dən kənarda (Celery
``exams.sync_enrolled_student_results``); növbə əlçatmazdırsa yerində. Bildiriş GETMİR (bal tələbəyə yeni deyil).
Best-effort: qeydiyyat yazısını heç vaxt sındırmır; bərpa: ``audit_exam_results_20261116 --apply``.
"""

from __future__ import annotations

import logging
from collections import Counter
from contextlib import contextmanager

from django.dispatch import receiver

from apps.registrar.public import enrollments_activated
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

logger = logging.getLogger(__name__)

#: Bir Celery mesajında ən çox bu qədər sətir (toplu qeydiyyat — məs. seçmə jurnalının açılışı).
CHUNK = 200


@contextmanager
def _scope():
    """Hər DB addımı öz qısa tranzaksiyasında + RLS bypass (worker / on_commit — request konteksti yoxdur)."""
    with rls_worker_atomic(), bypass_rls():
        yield


def _attempts(organization_id, student_id, offering_id, subject_id):
    from django.db.models import Q

    from apps.exams.models import ExamAttempt

    match = Q(exam__journal_offerings__id=offering_id)
    if subject_id:
        match |= Q(exam__subject_id=subject_id)
    ids = (
        ExamAttempt.objects.filter(match, user_id=student_id, exam__organization_id=organization_id, is_trial=False)
        .values_list("pk", flat=True)
        .distinct()
    )
    return ExamAttempt.objects.filter(pk__in=list(ids))


def sync_rows(organization_id, rows, *, scope=None) -> Counter:
    """``[(tələbə, açılış, fənn)]`` → tələbənin rəsmi midterm / final cəhdlərini yenidən yaz → status sayları."""
    from apps.exams.services import journal_sync, midterm_journal_sync

    scope = scope or _scope
    counts: Counter = Counter()
    for student_id, offering_id, subject_id in rows or ():
        with scope():
            attempts = _attempts(organization_id, student_id, offering_id, subject_id)
            if not attempts.exists():
                continue
            midterms = list(midterm_journal_sync.official_attempts(attempts))
            finals = list(journal_sync.official_final_attempts(attempts))
        for attempt in midterms:
            with scope():
                status, _row = midterm_journal_sync.sync_midterm_attempt(attempt, notify=False)
            counts[f"midterm_{status}"] += 1
        for attempt in finals:
            with scope():
                status, _row = journal_sync.sync_final_attempt(attempt)
            counts[f"final_{status}"] += 1
    if counts:
        logger.info("enrollment_result_sync: org=%s %s", organization_id, dict(counts))
    return counts


@receiver(enrollments_activated, dispatch_uid="exams_enrollment_result_sync")
def on_enrollments_activated(sender, organization_id=None, rows=(), **kwargs):
    rows = [list(row) for row in rows or () if row and row[0] and row[1]]
    if not organization_id or not rows:
        return
    from apps.exams.tasks import sync_enrolled_student_results

    for start in range(0, len(rows), CHUNK):
        chunk = rows[start : start + CHUNK]
        try:
            sync_enrolled_student_results.delay(str(organization_id), chunk)
        except Exception:  # noqa: BLE001 — broker düşübsə nəticə köçürməsi itməsin
            logger.warning("enrollment_result_sync: task not queued (org=%s) — inline", organization_id, exc_info=True)
            try:
                sync_rows(organization_id, chunk)
            except Exception:  # noqa: BLE001 — qeydiyyat axını sınmır
                logger.exception("enrollment_result_sync: inline sync failed (org=%s)", organization_id)


__all__ = ["on_enrollments_activated", "sync_rows"]
