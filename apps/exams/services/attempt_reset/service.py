"""attempt_reset — «Nəticəni sil (cəhdi sıfırla)» veb əməliyyatı (sahib 2026-11-04).

Sahib: «Mənə imtahan nəticəsini silmək lazımdır; midterm/final fərq etməsin. Məsələn tələbə səhvən daxil
olub — səbəb yazaraq … silə bilsin və izləmədə (audit) düşsün. Sonra o cəhd sıfırlanmış sayılsın və midterm
yenidən vermək olsun. Qrupda da elə bir şey etmək olsun».

Silinmənin özü ``exam_attempt_purge.apply_purge``-dur (cavablar, apellyasiyalar, reyestr hadisələri,
proktorinq, bildirişlər; jurnalın midterm xanası / yekun balı bərpa və ya boşaldılır; ``journal_locked`` /
``retake_links`` hallarında RƏDD). Cəhd silindiyi üçün ``max_attempts_per_user`` sayğacından düşür — tələbə
yenidən başlaya bilir. Bu modul üstünə əlavə edir:

* audit sətrində icraçı, IP, səbəb, ``verb=reset_exam_attempt``, tələbə və **əvvəlki ballar**;
* imtahan mərkəzi (zal) imtahanında bilet ``ASSIGNED`` + yeni PIN (``reset_tickets_after_attempt_purge``) —
  hamısı BİR tranzaksiyada;
* toplu / qrup rejimi: hər cəhd AYRI tranzaksiyadadır — bir rədd digərlərini dayandırmır.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from django.db import transaction

from apps.exams.services import exam_attempt_purge as purge
from apps.exams.services.trial_exam_purge import PurgeRefused

from .policy import clean_reason

logger = logging.getLogger(__name__)

RESET_VERB = "reset_exam_attempt"
STATUS_RESET = "reset"
STATUS_REFUSED = "refused"
STATUS_MISSING = "missing"


@dataclass(frozen=True)
class ResetResult:
    attempt_id: int
    student_id: int | None
    status: str
    blockers: tuple = ()
    tickets_reset: tuple = ()

    @property
    def ok(self) -> bool:
        return self.status == STATUS_RESET


@dataclass
class ResetSummary:
    results: list = field(default_factory=list)

    @property
    def reset_count(self) -> int:
        return sum(1 for result in self.results if result.ok)

    @property
    def refused_count(self) -> int:
        return sum(1 for result in self.results if result.status == STATUS_REFUSED)

    @property
    def missing_count(self) -> int:
        return sum(1 for result in self.results if result.status == STATUS_MISSING)

    @property
    def tickets_reset(self) -> int:
        return sum(len(result.tickets_reset) for result in self.results)

    @property
    def blocker_counts(self) -> Counter:
        counts: Counter = Counter()
        for result in self.results:
            counts.update(result.blockers)
        return counts


def _iso(value):
    return value.isoformat() if value else None


def score_snapshot(attempt) -> dict:
    """Silinmədən əvvəlki nəticə (audit üçün) — test: bal / maks / faiz; yazılı: müəllim balı."""
    snapshot = {
        "status": attempt.status or "",
        "attempt_number": attempt.attempt_number,
        "correct_count": attempt.correct_count,
        "wrong_count": attempt.wrong_count,
        "teacher_score": attempt.teacher_score,
        "supervision_status": getattr(attempt, "supervision_status", "") or "",
        "started_at": _iso(attempt.started_at),
        "finished_at": _iso(attempt.finished_at),
    }
    if getattr(attempt.exam, "exam_type", "") == "test":
        from apps.exams.services.result_calculation import calculate_test_attempt_result

        try:
            result = calculate_test_attempt_result(attempt)
        except Exception:  # noqa: BLE001 — audit snapshotı silinməni dayandırmamalıdır
            logger.exception("attempt_reset: score snapshot failed for attempt %s", attempt.pk)
        else:
            snapshot["score"] = str(result.score_display)
            snapshot["max_score"] = str(result.max_score_display)
            snapshot["percent"] = str(result.percentage_display)
    return snapshot


def _locked_attempt(attempt_id):
    from apps.exams.models import ExamAttempt

    return (
        ExamAttempt.objects.select_for_update(of=("self",))
        .select_related("exam", "exam__organization", "user")
        .filter(pk=attempt_id)
        .first()
    )


def reset_attempt(attempt, *, actor, reason, request=None) -> ResetResult:
    """Bir cəhdi sil + (zal imtahanında) bileti yenidən aç — BİR tranzaksiyada. Səbəb yoxlanılır."""
    from apps.exams.models import FinalExamTicket
    from apps.exams.services.final_center import reset_tickets_after_attempt_purge

    reason = clean_reason(reason)
    attempt_id, student_id = attempt.pk, attempt.user_id
    with transaction.atomic():
        locked = _locked_attempt(attempt_id)
        if locked is None:
            return ResetResult(attempt_id=attempt_id, student_id=student_id, status=STATUS_MISSING)
        ticket_ids = list(FinalExamTicket.objects.filter(attempt_id=locked.pk).values_list("pk", flat=True))
        extra = {
            "verb": RESET_VERB,
            "student_username": locked.user.username,
            "exam_category": str(getattr(locked.exam, "exam_type_extended", "") or ""),
            "scores_before": score_snapshot(locked),
            "ticket_ids": ticket_ids,
        }
        try:
            plan = purge.apply_purge(locked, reason=reason, actor=actor, request=request, audit_extra=extra)
        except PurgeRefused as refused:
            return ResetResult(
                attempt_id=attempt_id,
                student_id=student_id,
                status=STATUS_REFUSED,
                blockers=tuple(refused.plan.blockers),
            )
        if plan is None:
            return ResetResult(attempt_id=attempt_id, student_id=student_id, status=STATUS_MISSING)
        reopened = (
            reset_tickets_after_attempt_purge(ticket_ids, actor, attempt_id=attempt_id, request=request)
            if ticket_ids
            else []
        )
    return ResetResult(
        attempt_id=attempt_id,
        student_id=student_id,
        status=STATUS_RESET,
        tickets_reset=tuple(reopened),
    )


def reset_attempts(attempts, *, actor, reason, request=None) -> ResetSummary:
    """Toplu sıfırlama — hər cəhd ayrıca tranzaksiyada (bir rədd digərlərini dayandırmır)."""
    reason = clean_reason(reason)
    summary = ResetSummary()
    for attempt in attempts:
        summary.results.append(reset_attempt(attempt, actor=actor, reason=reason, request=request))
    return summary


def preview_attempts(attempts) -> dict:
    """Yazısız ön baxış: neçə cəhd, neçə tələbə, neçəsi sıfırlana bilər, neçəsi niyə bloklanıb."""
    blocked: Counter = Counter()
    resettable = 0
    students = set()
    total = 0
    for attempt in attempts:
        total += 1
        students.add(attempt.user_id)
        plan = purge.build_plan(attempt)
        if plan.blockers:
            blocked.update(plan.blockers)
        else:
            resettable += 1
    return {
        "attempts": total,
        "students": len(students),
        "resettable": resettable,
        "blocked": total - resettable,
        "blockers": dict(blocked),
    }


__all__ = [
    "RESET_VERB",
    "STATUS_MISSING",
    "STATUS_REFUSED",
    "STATUS_RESET",
    "ResetResult",
    "ResetSummary",
    "preview_attempts",
    "reset_attempt",
    "reset_attempts",
    "score_snapshot",
]
