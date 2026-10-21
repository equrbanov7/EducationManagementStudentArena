"""Test formatlı midterm cəhdi → elektron jurnalın «Midterm» xanası (exams tərəf, sahib 2026-10-21).

Sahib: «Midterm test olaraq verənlərdə avtomatik olaraq jurnala da düşsün, tələbənin balı əl ilə
doldurulmasın, tələbədə görünsün». Bu, 2026-09-25 qərarının («midterm balını müəllim İmtahan Mərkəzinin
pəncərəsində özü yazır») TEST formatı üçün geri alınmasıdır; yazılı / kodlaşdırma midtermi əvvəlki kimi
əl ilə yazılır (``journal_sync.SKIP_MIDTERM_CATEGORY``).

Qərar zənciri (hamısı ``sync_midterm_attempt``-də, hər addım sayılan status qaytarır):

1. fənnə bağlı, sınaq olmayan (``is_trial`` HEÇ VAXT yazılmır), BİTMİŞ cəhd;
2. ``exam_type == "test"`` və ``exam_type_extended == "midterm"``;
3. nəticə tələbədən GİZLƏDİLMƏYİB (``results_hidden_from_students``) — gizlidirsə jurnala da düşmür;
   müəllim nəticəni açanda (``lifecycle.set_results_hidden``) ``resync_exam`` bütün rəsmi cəhdləri yazır.
   Nəticə sonradan yenidən gizlədilsə jurnaldakı bal QALIR (artıq rəsmi jurnal qeydidir);
4. RƏSMİ cəhd — eyni tələbə + fənn üzrə DAHA SONRA başlamış bitmiş test midterm cəhdi yoxdur
   (yekun körpüsünün ``SKIP_SUPERSEDED_ATTEMPT`` qaydası, ``started_at`` + ``pk``);
5. faiz yekun körpüsü ilə EYNİ mənbədən (``journal_sync._attempt_percent`` — apellyasiya bonusu daxil),
   qovulma → 0; registrar şkalaya çevirir (``midterm_bridge``).

Tətik nöqtələri ``journal_sync.sync_attempt_to_journal``-dan keçir (cəhdin bitməsi, apellyasiya qərarı və
bal düzəlişi — ``appeals.services.decisions``, cavab açarı düzəlişi — ``appeals.services.key_corrections``);
ona görə yenidən qiymətləndirmə öz-özünə yenidən sinxronlaşır. Yazı best-effort-dur (imtahanı sındırmır).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

AUTO_MIDTERM_EXAM_TYPE = "test"

#: Exams tərəfinin statusları (registrar statusları ``midterm_bridge``-dədir).
UNLINKED = "unlinked"
TRIAL = "trial"
NOT_FINISHED = "not_finished"
NOT_AUTO_MIDTERM = "not_auto_midterm"
NO_ORGANIZATION = "no_organization"
RESULTS_HIDDEN = "results_hidden"
SUPERSEDED = "superseded"
PERCENT_UNAVAILABLE = "percent_unavailable"
WRITE_FAILED = "write_failed"

#: Sayğaca (``ems_journal_sync_skips_total``) yazılan midterm atlamaları — etiket ``midterm_<status>``.
_COUNTED = frozenset(
    {
        NOT_FINISHED,
        NO_ORGANIZATION,
        RESULTS_HIDDEN,
        SUPERSEDED,
        PERCENT_UNAVAILABLE,
        WRITE_FAILED,
        "no_enrollment",
        "not_midterm_period",
        "journal_locked",
        "overridden",
    }
)
#: Gözlənilən hallar (xəta deyil) INFO; qalanları WARNING.
_EXPECTED = frozenset({RESULTS_HIDDEN, SUPERSEDED, "overridden", "not_midterm_period"})


def is_auto_midterm_exam(exam) -> bool:
    """İmtahan TEST formatlı midtermdirmi (balı jurnala avtomatik düşür)."""
    from apps.exams.services.journal_sync import MIDTERM_EXAM_CATEGORY

    category = str(getattr(exam, "exam_type_extended", None) or "").strip()
    return category == MIDTERM_EXAM_CATEGORY and getattr(exam, "exam_type", None) == AUTO_MIDTERM_EXAM_TYPE


def _later_attempts_q(attempt):
    from django.db.models import Q

    started_at = attempt.started_at
    return Q(started_at__gt=started_at) | Q(started_at=started_at, pk__gt=attempt.pk)


def _official_filter(subject_id):
    """Rəsmi test midterm cəhdlərinin ortaq süzgəci (fənn üzrə)."""
    from apps.exams.constants import ATTEMPT_FINISHED_STATUSES
    from apps.exams.services.journal_sync import MIDTERM_EXAM_CATEGORY

    return {
        "exam__subject_id": subject_id,
        "exam__exam_type_extended": MIDTERM_EXAM_CATEGORY,
        "exam__exam_type": AUTO_MIDTERM_EXAM_TYPE,
        "exam__is_deleted": False,
        "is_trial": False,
        "status__in": ATTEMPT_FINISHED_STATUSES,
    }


def superseded_by_later_midterm(attempt, subject_id) -> bool:
    """Eyni tələbənin eyni fənn üzrə bu cəhddən SONRA başlamış bitmiş test midterm cəhdi varmı."""
    from apps.exams.models import ExamAttempt

    if getattr(attempt, "started_at", None) is None:
        return False
    return (
        ExamAttempt.objects.filter(_later_attempts_q(attempt), user_id=attempt.user_id, **_official_filter(subject_id))
        .exclude(pk=attempt.pk)
        .exists()
    )


def _status(status, attempt, row=None):
    if status in _COUNTED:
        from apps.exams.services.journal_sync import journal_sync_skips_total

        journal_sync_skips_total.labels(reason=f"midterm_{status}").inc()
        level = logging.INFO if status in _EXPECTED else logging.WARNING
        logger.log(level, "midterm_journal_sync: attempt %s not written (%s)", getattr(attempt, "id", "?"), status)
    return status, row


def sync_midterm_attempt(attempt, *, actor=None, appeal_id=None, notify=True):
    """Test midterm cəhdinin balını jurnala yaz → ``(status, ComponentScore | None)``. Heç vaxt istisna atmır."""
    exam = getattr(attempt, "exam", None)
    subject_id = getattr(exam, "subject_id", None)
    if exam is None or not subject_id:
        return UNLINKED, None
    if getattr(attempt, "is_trial", False):
        return TRIAL, None  # müəllimin «Sınaq keç» cəhdi heç vaxt jurnala düşmür
    if not attempt.is_finished:
        return _status(NOT_FINISHED, attempt)
    if not is_auto_midterm_exam(exam):
        return NOT_AUTO_MIDTERM, None
    organization = getattr(exam, "organization", None)
    if organization is None:
        return _status(NO_ORGANIZATION, attempt)
    if getattr(exam, "results_hidden_from_students", False):
        return _status(RESULTS_HIDDEN, attempt)
    if superseded_by_later_midterm(attempt, subject_id):
        return _status(SUPERSEDED, attempt)

    from apps.exams.services import journal_sync

    is_expelled = getattr(attempt, "supervision_status", "") == "removed"
    percent = 0 if is_expelled else journal_sync._attempt_percent(attempt)
    if percent is None or percent is journal_sync.PERCENT_PENDING:
        return _status(PERCENT_UNAVAILABLE, attempt)
    try:
        from apps.registrar.public import record_midterm_result

        status, row = record_midterm_result(
            student=attempt.user,
            subject_id=subject_id,
            organization=organization,
            score_percent=percent,
            attempt_id=attempt.pk,
            exam_id=exam.pk,
            exam_title=getattr(exam, "title", ""),
            exam_slug=getattr(exam, "slug", ""),
            attempt_finished_at=getattr(attempt, "finished_at", None),
            is_expelled=is_expelled,
            by_user=journal_sync._resolve_actor(attempt, actor),
            appeal_id=appeal_id,
            notify=notify,
        )
    except Exception:  # körpü heç vaxt imtahanı sındırmır
        logger.exception("midterm_journal_sync: failed to write attempt %s", getattr(attempt, "id", "?"))
        return _status(WRITE_FAILED, attempt)
    return _status(status, attempt, row)


def official_attempts(queryset):
    """``queryset``-dəki bitmiş test midterm cəhdlərindən (tələbə, fənn) üzrə RƏSMİ olanları (ən son başlamış)."""
    from django.db.models import F

    from apps.exams.constants import ATTEMPT_FINISHED_STATUSES
    from apps.exams.services.journal_sync import MIDTERM_EXAM_CATEGORY

    rows = (
        queryset.filter(
            exam__subject__isnull=False,
            exam__exam_type_extended=MIDTERM_EXAM_CATEGORY,
            exam__exam_type=AUTO_MIDTERM_EXAM_TYPE,
            exam__is_deleted=False,
            is_trial=False,
            status__in=ATTEMPT_FINISHED_STATUSES,
        )
        .select_related("exam", "exam__organization", "user")
        .order_by("user_id", "exam__subject_id", F("started_at").desc(nulls_last=True), "-pk")
    )
    seen = set()
    for attempt in rows.iterator(chunk_size=500):
        key = (attempt.user_id, attempt.exam.subject_id)
        if key in seen:
            continue
        seen.add(key)
        yield attempt


def resync_exam(exam, *, notify=True) -> dict:
    """İmtahanın bütün rəsmi test midterm cəhdlərini yenidən yaz (nəticə tələbəyə AÇILANDA). → status sayları."""
    from apps.exams.models import ExamAttempt

    counts: dict = {}
    if not is_auto_midterm_exam(exam) or not getattr(exam, "subject_id", None):
        return counts
    for attempt in official_attempts(ExamAttempt.objects.filter(exam=exam)):
        status, _row = sync_midterm_attempt(attempt, notify=notify)
        counts[status] = counts.get(status, 0) + 1
    return counts


def schedule_resync_exam(exam) -> None:
    """``resync_exam``-ı tranzaksiya təsdiqindən SONRA işlət (görünürlük keçidi geri qayıdarsa yazı olmasın)."""
    from django.db import transaction

    def _run():
        try:
            resync_exam(exam)
        except Exception:  # noqa: BLE001 — nəticə açılışını sındırmır
            logger.exception("midterm_journal_sync: resync failed for exam %s", getattr(exam, "id", "?"))

    transaction.on_commit(_run)


__all__ = [
    "is_auto_midterm_exam",
    "official_attempts",
    "resync_exam",
    "schedule_resync_exam",
    "superseded_by_later_midterm",
    "sync_midterm_attempt",
]
