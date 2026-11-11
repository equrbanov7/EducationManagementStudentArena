"""İmtahan vermiş, nəticəsi olan, amma jurnalda olmayan tələbələr — tap, jurnala əlavə et, nəticəni yaz (sahib 2026-11-11).

Sahib: «İmtahana girən və nəticəsi olan hər kəs həmin fənni jurnalında görsün, balını görsün.» Rəsmi cəhdlər
(midterm: :func:`.midterm_journal_sync.official_attempts`; final: ``sync_final_scores.official_final_attempts``) cari
dövrdə başlamış cəhdlərdir; körpünün hədəfi tapılmayan (``target_identity is None``) cəhd «itkin»dir — 25% müraciətinə
bağlı cəhd İSTİSNADIR (onun hədəfi jurnal qeydiyyatı deyil; bağlanmış müraciət də ``None`` qaytarır).

TƏHLÜKƏSİZLİK HƏDDİ (imtahan başına): itkinlər :data:`MAX_MISSING_STUDENTS`-dən çoxdursa və ya yoxlanan iştirakçıların
:data:`MAX_MISSING_SHARE`-indən çoxdursa bu, «bir-iki alt qrup tələbəsi» deyil — çox güman imtahan yanlış fənnə /
jurnala bağlanıb (bütöv qrup yad jurnala yazılardı). Belə imtahan ATLANIR və sayılır; yalnız planda açıq sadalanan
imtahan (``takers_exams``) həddən keçir. Hər imtahan üçün ayrıca sətir çap olunur (``exam=<id> …``).

Əlavə registrar tərəfindədir (``exam_taker_placement_2026_11_11`` — alt qrup yerləşdirməsinin rəsmi servisi, sənədsiz
keçid), sonra cəhd adi yolla yenidən sinxronlaşır (``journal_sync.sync_attempt_to_journal`` — gizli nəticə,
yoxlanmamış yazılı iş və s. qaydalar olduğu kimi qalır). Yerləşdirmələr paket id-si ilə audit-dədir — geri qaytarma
:func:`undo` (yalnız toxunulmamış sətirlər).
"""

from __future__ import annotations

from collections import defaultdict
from itertools import chain

from django.db import IntegrityError, transaction

#: Bir imtahanda bundan ÇOX itkin tələbə varsa imtahan atlanır (planda açıq sadalanmayıbsa).
MAX_MISSING_STUDENTS = 5
#: … və ya itkinlər yoxlanan rəsmi iştirakçıların bu payından çoxdursa.
MAX_MISSING_SHARE = 0.20


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


def mass_missing(missing: int, checked: int) -> bool:
    return missing > MAX_MISSING_STUDENTS or missing > MAX_MISSING_SHARE * checked


def _scan(organization, period, counts, placement) -> dict:
    """``{imtahan id: {"checked": n, "missing": [cəhd]}}`` — yazı yoxdur."""
    from apps.exams.services.journal_sync_scope import target_identity

    exams = defaultdict(lambda: {"checked": 0, "missing": []})
    for attempt in _attempts(organization, period):
        counts["takers_checked"] += 1
        info = exams[attempt.exam_id]
        info["checked"] += 1
        if target_identity(attempt) is not None:
            continue
        if placement.is_retake_attempt(
            student=attempt.user, subject_id=attempt.exam.subject_id, organization=organization, attempt=attempt
        ):
            counts["takers_retake_attempt_skipped"] += 1
            continue
        info["missing"].append(attempt)
    return exams


def run(*, organization, actor, counts, period, batch, lines=None, allowed_exams=()) -> None:
    from apps.exams.services import journal_sync
    from apps.exams.services.journal_sync_scope import target_identity
    from apps.registrar.public import exam_taker_placement_2026_11_11 as placement

    if period is None:
        return
    lines = [] if lines is None else lines
    allowed = {str(value) for value in allowed_exams or ()}
    placements = []
    for exam_id, info in sorted(_scan(organization, period, counts, placement).items()):
        missing, checked = info["missing"], info["checked"]
        if not missing:
            continue
        counts["takers_missing_from_journal"] += len(missing)
        counts["takers_exams_affected"] += 1
        if mass_missing(len(missing), checked) and str(exam_id) not in allowed:
            counts["takers_exams_skipped_mass_missing"] += 1
            counts["takers_skipped_mass_missing"] += len(missing)
            lines.append(f"exam={exam_id} checked={checked} missing={len(missing)} skipped=mass_missing")
            continue
        placed = refused = 0
        offering_ids = _offering_ids(missing[0].exam)
        for attempt in missing:
            # 2026-11-11 prod dry-run: aktiv üzvlüyü olmayan tələbədə DB qoruyucusu (registrar_guard_active_member)
            # IntegrityError verir — bütün qaçış dayanırdı. Hər tələbə öz savepoint-indədir: yerləşdirmə + nəticə
            # sinxronu birlikdə ya yazılır, ya da geri qayıdır və sayılır.
            try:
                with transaction.atomic():
                    code, enrollment, receipt_row = placement.place(
                        organization=organization, student=attempt.user, offering_ids=offering_ids, actor=actor
                    )
                    resolved = None
                    if enrollment is not None:
                        journal_sync.sync_attempt_to_journal(attempt)
                        resolved = target_identity(attempt) is not None
            except IntegrityError:
                counts["taker_write_blocked_integrity"] += 1
                refused += 1
                continue
            counts[code] += 1
            if receipt_row is not None:
                placements.append({**receipt_row, "exam": str(exam_id), "student": attempt.user_id})
            if enrollment is None:
                refused += 1
                continue
            placed += 1
            counts["takers_result_synced" if resolved else "takers_result_still_unresolved"] += 1
        lines.append(f"exam={exam_id} checked={checked} missing={len(missing)} placed={placed} refused={refused}")
    placement.receipt(organization=organization, actor=actor, batch=batch, placements=placements)


def undo(*, organization, actor, counts, batch) -> bool:
    from apps.registrar.public import exam_taker_placement_2026_11_11 as placement

    return placement.undo(organization=organization, actor=actor, counts=counts, batch=batch)


__all__ = ["MAX_MISSING_SHARE", "MAX_MISSING_STUDENTS", "mass_missing", "run", "undo"]
