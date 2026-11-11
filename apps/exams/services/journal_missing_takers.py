"""İmtahan vermiş, nəticəsi olan, amma jurnalda olmayan tələbələr — tap, jurnala əlavə et, nəticəni yaz (sahib 2026-11-11).

Sahib: «İmtahana girən və nəticəsi olan hər kəs həmin fənni jurnalında görsün, balını görsün.» Rəsmi cəhdlər
(midterm: :func:`.midterm_journal_sync.official_attempts`; final: ``sync_final_scores.official_final_attempts``) cari
dövrdə başlamış cəhdlərdir; körpünün hədəfi tapılmayan (``target_identity is None``) hər cəhd «itkin»dir. Əlavə
registrar tərəfindədir (``exam_taker_placement_2026_11_11`` — alt qrup yerləşdirməsinin rəsmi servisi, sənədsiz keçid),
sonra cəhd adi yolla yenidən sinxronlaşır (``journal_sync.sync_attempt_to_journal`` — gizli nəticə, yoxlanmamış
yazılı iş və s. qaydalar olduğu kimi qalır).
"""

from __future__ import annotations

from itertools import chain


def _attempts(organization, period):
    from apps.exams.management.commands.sync_final_scores import official_final_attempts
    from apps.exams.models import ExamAttempt
    from apps.exams.services.midterm_journal_sync import official_attempts

    rows = ExamAttempt.objects.filter(exam__organization=organization, started_at__date__gte=period.start_date)
    return chain(official_attempts(rows), official_final_attempts(rows))


def _offering_ids(exam) -> list:
    from apps.exams.services import exam_journal_link

    ids = exam_journal_link.linked_offering_ids(exam)
    if not ids and exam_journal_link.compute_link_ids(exam):
        exam_journal_link.refresh_links(exam)
        ids = exam_journal_link.linked_offering_ids(exam)
    return ids


def run(*, organization, actor, counts, period) -> None:
    from apps.exams.services import journal_sync
    from apps.exams.services.journal_sync_scope import target_identity
    from apps.registrar.public import exam_taker_placement_2026_11_11 as placement

    if period is None:
        return
    exams = set()
    for attempt in _attempts(organization, period):
        counts["takers_checked"] += 1
        if target_identity(attempt) is not None:
            continue
        counts["takers_missing_from_journal"] += 1
        exams.add(attempt.exam_id)
        code, enrollment = placement.place(
            organization=organization, student=attempt.user, offering_ids=_offering_ids(attempt.exam), actor=actor
        )
        counts[code] += 1
        if enrollment is None:
            continue
        journal_sync.sync_attempt_to_journal(attempt)
        written = target_identity(attempt) is not None
        counts["takers_result_synced" if written else "takers_result_still_unresolved"] += 1
    counts["takers_exams_affected"] += len(exams)


__all__ = ["run"]
