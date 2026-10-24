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


def resync_exam_journal(exam, *, notify=True, by_user=None) -> Counter:
    """Rəsmi midterm cəhdlərini bağlı jurnala yaz + köhnə bağlantının avtomatik xanalarını sil → saylar."""
    from apps.exams.services import midterm_journal_sync

    counts: Counter = Counter(midterm_journal_sync.resync_exam(exam, notify=notify))
    counts.update(clear_stale(exam, by_user=by_user))
    return counts


def _has_finished_attempts(exam) -> bool:
    from apps.exams.constants import ATTEMPT_FINISHED_STATUSES

    return exam.attempts.filter(status__in=ATTEMPT_FINISHED_STATUSES, is_trial=False).exists()


def after_exam_saved(exam, *, previous_subject_id=None, previous_link_ids=(), by_user=None) -> bool:
    """Yaratma / redaktədən sonra: bağlantını yenilə; fənn və ya jurnal dəyişibsə on_commit yenidən sinxron.

    → yenidən sinxronizasiya planlaşdırıldımı. Best-effort: imtahanın saxlanmasını heç vaxt sındırmır."""
    try:
        _old, new_ids = refresh_links(exam)
    except Exception:  # noqa: BLE001 — bağlantı xətası imtahanı sındırmır (növbəti saxlamada / komanda ilə)
        logger.exception("exam_journal_link: link refresh failed for exam %s", getattr(exam, "pk", "?"))
        return False
    changed = previous_subject_id != exam.subject_id or set(previous_link_ids or ()) != new_ids
    if not changed or not _has_finished_attempts(exam):
        return False

    from django.db import transaction

    def _run():
        try:
            counts = resync_exam_journal(exam, by_user=by_user)
            logger.info("exam_journal_link: exam %s re-linked, resync %s", exam.pk, dict(counts))
        except Exception:  # noqa: BLE001
            logger.exception("exam_journal_link: resync failed for exam %s", getattr(exam, "pk", "?"))

    transaction.on_commit(_run)
    return True


__all__ = [
    "after_exam_saved",
    "clear_stale",
    "compute_link_ids",
    "exam_group_ids",
    "linked_offering_ids",
    "refresh_links",
    "resync_exam_journal",
]
