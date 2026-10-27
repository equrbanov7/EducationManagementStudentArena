"""İmtahan ↔ elektron jurnal bağlantısı — exams tərəfi (sahib 2026-10-24, «JS Loop» halı).

KÖK SƏBƏB (prod, «JS Loop» midtermi): imtahan əvvəl YANLIŞ fənnə bağlanmışdı; tələbələr imtahanı
bitirəndə körpü (``midterm_journal_sync``) yanlış fənn üzrə qeydiyyat tapmadı (``no_enrollment``) və heç
nə yazmadı. Sonra fənn «Mobil proqramlaşdırma»ya dəyişdirildi, amma imtahanın redaktəsi heç bir yenidən
sinxronizasiya işə salmırdı (yalnız «nəticəni göstər» keçidi və cəhdin bitməsi tətik idi) → jurnalın
«Midterm» sütunu 0 / boş qaldı.

İndi:

1. **Açıq bağlantı** — :func:`refresh_links` imtahanın fənni + reyestr qrupları (+ ``journal_teacher``)
   üzrə HƏR qrupun öz jurnal açılışını ``Exam.journal_offerings``-ə yazır (registrar
   ``exam_journal_link.link_offering_ids``). Körpü tələbənin balını onun BAĞLI jurnalına yazır, bağlı
   jurnalda qeydiyyatı yoxdursa əvvəlki kimi fənn üzrə qeydiyyatına.
2. **Yenidən bağlama** — :func:`after_exam_saved` (yaratma / redaktə view-u): fənn və ya bağlı jurnallar
   dəyişibsə tranzaksiya təsdiqindən SONRA :func:`resync_exam_journal` — bütün rəsmi cəhdlər YENİ
   jurnala yazılır, bu imtahanın KÖHNƏ jurnala yazdığı avtomatik xanalar silinir (yalnız bu imtahanın
   yazdıqları; bağlanmış jurnal və sənədli düzəliş toxunulmur).
3. **Bərpa** — ``manage.py sync_midterm_scores [--exam …] [--apply]`` eyni addımları mövcud imtahanlar
   üçün işlədir (defolt dry-run).
"""

from __future__ import annotations

import logging
from collections import Counter
from contextlib import nullcontext

logger = logging.getLogger(__name__)


def _registrar_link():
    from apps.registrar.public import exam_journal_link

    return exam_journal_link


def exam_group_ids(exam) -> list:
    """İmtahanın reyestr qruplarının id-ləri (``allowed_units``)."""
    if not getattr(exam, "pk", None):
        return []
    return list(exam.allowed_units.values_list("pk", flat=True))


def linked_offering_ids(exam) -> list:
    if not getattr(exam, "pk", None):
        return []
    return list(exam.journal_offerings.values_list("pk", flat=True))


def compute_link_ids(exam) -> list:
    """İmtahanın bağlanmalı olduğu jurnal açılışları (fənn + qruplar + müəllim)."""
    if not getattr(exam, "subject_id", None) or getattr(exam, "organization", None) is None:
        return []
    return _registrar_link().link_offering_ids(
        exam.organization,
        subject_id=exam.subject_id,
        group_ids=exam_group_ids(exam),
        teacher=getattr(exam, "journal_teacher", None),
    )


def refresh_links(exam) -> tuple[set, set]:
    """``Exam.journal_offerings``-i yenidən hesabla → ``(köhnə_id-lər, yeni_id-lər)``."""
    old_ids = set(linked_offering_ids(exam))
    new_ids = set(compute_link_ids(exam))
    if new_ids != old_ids:
        exam.journal_offerings.set(list(new_ids))
    return old_ids, new_ids


def clear_stale(exam, *, by_user=None) -> Counter:
    """Bu imtahanın KÖHNƏ fənn / jurnal xanalarına yazdığı avtomatik balları sil → status sayları.

    Yalnız test midtermi üçün (kateqoriya / format dəyişibsə xanalara toxunulmur — açıq qərar tələb edir)."""
    from apps.exams.services import midterm_journal_sync

    if not getattr(exam, "pk", None) or not midterm_journal_sync.is_auto_midterm_exam(exam):
        return Counter()
    return _registrar_link().clear_stale_midterm_scores(
        organization=exam.organization,
        exam_id=exam.pk,
        subject_id=exam.subject_id,
        offering_ids=linked_offering_ids(exam),
        by_user=by_user,
    )


def resync_exam_journal(exam, *, notify=True, by_user=None, scope=None) -> Counter:
    """Rəsmi midterm cəhdlərini bağlı jurnala yaz + köhnə bağlantının avtomatik xanalarını sil → saylar."""
    from apps.exams.services import midterm_journal_sync

    counts: Counter = Counter(midterm_journal_sync.resync_exam(exam, notify=notify, scope=scope))
    with (scope or nullcontext)():
        counts.update(clear_stale(exam, by_user=by_user))
    return counts


def _has_finished_attempts(exam) -> bool:
    from apps.exams.constants import ATTEMPT_FINISHED_STATUSES

    return exam.attempts.filter(status__in=ATTEMPT_FINISHED_STATUSES, is_trial=False).exists()


def after_exam_saved(exam, *, previous_subject_id=None, previous_link_ids=(), by_user=None, change_log_id=None) -> bool:
    """Yaratma / redaktədən sonra: bağlantını yenilə; fənn və ya jurnal dəyişibsə on_commit yenidən sinxron.

    ``change_log_id`` — təsdiqlənmiş fənn dəyişikliyinin audit sətri (``exam_subject_change``, 2026-10-25):
    verilibsə köçürmənin faktiki sayları da audit olunur (imtahan tarixçəsində görünür).
    → yenidən sinxronizasiya planlaşdırıldımı. Best-effort: imtahanın saxlanmasını heç vaxt sındırmır."""
    try:
        _old, new_ids = refresh_links(exam)
    except Exception:  # noqa: BLE001 — bağlantı xətası imtahanı sındırmır (növbəti saxlamada / komanda ilə)
        logger.exception("exam_journal_link: link refresh failed for exam %s", getattr(exam, "pk", "?"))
        return False
    changed = previous_subject_id != exam.subject_id or set(previous_link_ids or ()) != new_ids
    if not changed or not _has_finished_attempts(exam):
        return False

    schedule_resync(exam, by_user=by_user, change_log_id=change_log_id)
    return True


def run_resync(exam_id, *, by_user_id=None, change_log_id=None, relink=True, scope=None) -> dict:
    """Planlaşdırılmış yenidən sinxron (Celery task-ı və ya növbə əlçatmazdırsa request-in on_commit-i).

    ``relink`` — imtahanın saxlanması (fənn / jurnal bağlantısı dəyişib): yaz + köhnə xanaları sil + təsdiqli
    dəyişikliyin faktiki saylarını audit et. ``relink=False`` — nəticə açılışı: yalnız yaz. Best-effort."""
    from django.contrib.auth import get_user_model

    from apps.exams.models import Exam
    from apps.exams.services import midterm_journal_sync

    scope = scope or nullcontext
    try:
        with scope():
            exam = Exam.objects.select_related("organization").filter(pk=exam_id).first()
            by_user = get_user_model().objects.filter(pk=by_user_id).first() if by_user_id else None
        if exam is None:
            return {}
        if not relink:
            return dict(midterm_journal_sync.resync_exam(exam, scope=scope))
        counts = resync_exam_journal(exam, by_user=by_user, scope=scope)
        logger.info("exam_journal_link: exam %s re-linked, resync %s", exam.pk, dict(counts))
        if change_log_id is not None:
            from apps.exams.services import exam_subject_change

            with scope():
                exam_subject_change.record_resync(exam, counts, decision_log_id=change_log_id, user=by_user)
        return {str(key): int(value) for key, value in counts.items()}
    except Exception:  # noqa: BLE001 — imtahanın saxlanmasını / nəticə açılışını sındırmır
        logger.exception("exam_journal_link: resync failed for exam %s", exam_id)
        return {}


def schedule_resync(exam, *, by_user=None, change_log_id=None, relink=True) -> None:
    """Tranzaksiya təsdiqindən SONRA :func:`run_resync`-i Celery-yə ver (sahib 2026-10-27).

    Cəhd başına ~30 sorğu (bal, kilid, audit, bildiriş) — 10 qrupluq midtermdə «Saxlanılır…» saniyələrlə
    ilişirdi (``ATOMIC_REQUESTS``-də on_commit request-in içindədir). Növbə əlçatmazdırsa əvvəlki kimi yerində."""
    from django.db import transaction

    exam_id, by_user_id = exam.pk, getattr(by_user, "pk", None)
    # Celery JSON: AuditLog pk UUID-dir — sətir kimi (``record_resync`` onsuz da ``str(...)`` yazır).
    log_id = None if change_log_id is None else str(change_log_id)
    options = {"by_user_id": by_user_id, "change_log_id": log_id, "relink": relink}

    def _enqueue():
        from apps.exams.tasks import resync_exam_journal as resync_task

        try:
            resync_task.delay(exam_id, **options)
        except Exception:  # noqa: BLE001 — broker düşübsə bal köçürməsi itməsin
            logger.warning("exam_journal_link: resync task not queued (exam=%s) — inline", exam_id, exc_info=True)
            run_resync(exam_id, **options)

    transaction.on_commit(_enqueue)


__all__ = [
    "after_exam_saved",
    "clear_stale",
    "compute_link_ids",
    "exam_group_ids",
    "linked_offering_ids",
    "refresh_links",
    "resync_exam_journal",
    "run_resync",
    "schedule_resync",
]
