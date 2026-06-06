"""
Apellyasiya qərarı + bal düzəlişi (idempotent) + effektiv bal hesablanması.

Kritik dizayn qeydi:
``result_calculation.calculate_test_attempt_result`` test balını sualın DÜZGÜN
variant açarı ilə müqayisədən hesablayır (``answer.is_correct`` flag-indən YOX).
Yəni bir studentin balını yalnız onun üçün artırmaq üçün cavab açarını dəyişmək
OLMAZ (bu, bütün studentlərə təsir edərdi). Buna görə qəbul olunmuş apellyasiya
**additiv ``ScoreAdjustment`` deltası** kimi saxlanılır və effektiv bal =
baza (option-əsaslı) bal + delta cəmi.

İdempotentlik: ``ScoreAdjustment`` ``appeal_item`` ilə OneToOne olduğundan eyni
item üçün bal İKİ DƏFƏ artırıla bilmir.
"""

import logging
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.appeals.constants import (
    APPEAL_ITEM_STATUS_ACCEPTED,
    APPEAL_ITEM_STATUS_PENDING,
    APPEAL_ITEM_STATUS_REJECTED,
    APPEAL_STATUS_ACCEPTED,
    APPEAL_STATUS_PARTIALLY_ACCEPTED,
    APPEAL_STATUS_PENDING,
    APPEAL_STATUS_REJECTED,
    APPEAL_STATUS_UNDER_REVIEW,
)
from apps.appeals.models import AppealItem, ScoreAdjustment

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Effektiv bal (baza + apellyasiya bonusları)
# ---------------------------------------------------------------------------
def appeal_score_state(attempt):
    """Attempt üzrə aktiv (revert olunmamış) düzəlişlərin xülasəsi."""
    adjustments = list(ScoreAdjustment.objects.filter(attempt=attempt, reverted=False))
    bonus = sum((adj.delta_points or Decimal("0") for adj in adjustments), Decimal("0"))
    return {
        "bonus_points": bonus,
        "adjustment_count": len(adjustments),
        "credited_question_ids": {adj.question_id for adj in adjustments if adj.delta_points and adj.delta_points > 0},
    }


def effective_test_score(attempt):
    """
    Test attempt-i üçün apellyasiya bonusları nəzərə alınmaqla effektiv bal.

    Qaytarır: dict(base, bonus_points, effective_score, max_score, effective_percentage).
    Faza 4 nəticə səhifəsi bunu istifadə edəcək.
    """
    from apps.exams.services.result_calculation import calculate_test_attempt_result

    base = calculate_test_attempt_result(attempt)
    bonus = appeal_score_state(attempt)["bonus_points"]

    effective_score = base.score + bonus
    if base.max_score and effective_score > base.max_score:
        effective_score = base.max_score

    if base.max_score and base.max_score > 0:
        effective_percentage = (effective_score * Decimal("100") / base.max_score).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
    else:
        effective_percentage = Decimal("0")

    return {
        "base": base,
        "bonus_points": bonus,
        "effective_score": effective_score,
        "max_score": base.max_score,
        "effective_percentage": effective_percentage,
    }


# ---------------------------------------------------------------------------
# Köməkçilər
# ---------------------------------------------------------------------------
def _question_already_correct(answer, question):
    """Test sualı student üçün artıq düzgün sayılırmı (option-əsaslı)."""
    if answer is None:
        return False
    selected = {option.id for option in answer.selected_options.all()}
    if not selected:
        return False
    correct = {option.id for option in question.options.all() if option.is_correct}
    return bool(correct and selected == correct)


def _mark_item_resolved(item, status, reviewer, response_text):
    item.status = status
    if response_text:
        item.reviewer_response = response_text
    item.resolved_by = reviewer
    item.resolved_at = timezone.now()
    item.save(update_fields=["status", "reviewer_response", "resolved_by", "resolved_at", "updated_at"])


def _audit_score_change(request, reviewer, attempt, *, appeal, adjustment):
    try:
        from apps.audit.utils import log_action
        from core.constants import AuditAction

        log_action(
            action=AuditAction.UPDATE,
            user=reviewer,
            organization=getattr(appeal, "organization", None),
            obj=adjustment,
            reason="Appeal accepted — score adjustment applied",
            request=request,
            new_values={
                "attempt_id": attempt.id,
                "appeal_id": appeal.id,
                "appeal_item_id": adjustment.appeal_item_id,
                "delta_points": str(adjustment.delta_points),
                "previous_score": str(adjustment.previous_score),
                "new_score": str(adjustment.new_score),
            },
        )
    except Exception:
        logger.warning("Appeal score-change audit log failed.", exc_info=True)


# ---------------------------------------------------------------------------
# Qərar əməliyyatları
# ---------------------------------------------------------------------------
@transaction.atomic
def accept_appeal_item(item, *, reviewer, response_text="", request=None):
    """
    Bir AppealItem-i qəbul edir və (test üçün) idempotent bal düzəlişi tətbiq edir.

    Eyni item üçün artıq aktiv düzəliş varsa, bal təkrar ARTIRILMIR — yalnız
    status/cavab yenilənir.
    """
    item = (
        AppealItem.objects.select_for_update()
        .select_related("appeal", "appeal__attempt", "appeal__attempt__exam", "question", "answer")
        .get(pk=item.pk)
    )
    appeal = item.appeal
    attempt = appeal.attempt
    exam = attempt.exam
    question = item.question
    answer = item.answer or attempt.answers.filter(question=question).first()

    existing = ScoreAdjustment.objects.filter(appeal_item=item).first()
    if existing and not existing.reverted:
        # Artıq tətbiq olunub — ikiqat artımın qarşısını alırıq.
        _mark_item_resolved(item, APPEAL_ITEM_STATUS_ACCEPTED, reviewer, response_text)
        recompute_appeal_status(appeal, reviewer=reviewer)
        return existing

    delta = Decimal("0")
    prev_is_correct = None
    new_is_correct = None
    previous_score = None
    new_score = None
    previous_answer_score = None
    question_points = Decimal(str(question.points or 1))

    if getattr(exam, "exam_type", None) == "test":
        # Test: bal cavab açarından hesablandığı üçün additiv bonus (delta).
        prev_is_correct = _question_already_correct(answer, question)
        previous_score = effective_test_score(attempt)["effective_score"]
        if not prev_is_correct:
            delta = question_points
        new_is_correct = True
        new_score = previous_score + delta
    else:
        # Yazılı/praktiki: sual üçün TAM bal verilir (answer.teacher_score = points),
        # sonra attempt.teacher_score cavablardan yenidən hesablanır. Beləliklə
        # nəticə dərhal əks olunur (test-dən fərqli olaraq, ayrıca bonus qatı yox).
        from apps.exams.services.grading import calculate_attempt_score

        previous_answer_score = (
            Decimal(str(answer.teacher_score)) if (answer is not None and answer.teacher_score is not None) else None
        )
        previous_score = calculate_attempt_score(attempt)
        if answer is not None and (previous_answer_score is None or previous_answer_score < question_points):
            answer.teacher_score = int(question_points)
            answer.save(update_fields=["teacher_score", "updated_at"])
        new_score = calculate_attempt_score(attempt)
        delta = new_score - previous_score
        attempt.teacher_score = int(new_score) if new_score and new_score > 0 else attempt.teacher_score
        attempt.save(update_fields=["teacher_score"])

    if existing:
        # Əvvəl revert olunmuş düzəlişi yenidən aktivləşdir.
        existing.reverted = False
        existing.delta_points = delta
        existing.previous_is_correct = prev_is_correct
        existing.new_is_correct = new_is_correct
        existing.previous_score = previous_score
        existing.new_score = new_score
        existing.previous_answer_score = previous_answer_score
        existing.applied_by = reviewer
        existing.save(
            update_fields=[
                "reverted",
                "delta_points",
                "previous_is_correct",
                "new_is_correct",
                "previous_score",
                "new_score",
                "previous_answer_score",
                "applied_by",
            ]
        )
        adjustment = existing
    else:
        adjustment = ScoreAdjustment.objects.create(
            appeal_item=item,
            attempt=attempt,
            question=question,
            delta_points=delta,
            previous_is_correct=prev_is_correct,
            new_is_correct=new_is_correct,
            previous_score=previous_score,
            new_score=new_score,
            previous_answer_score=previous_answer_score,
            applied_by=reviewer,
        )

    _mark_item_resolved(item, APPEAL_ITEM_STATUS_ACCEPTED, reviewer, response_text)
    _audit_score_change(request, reviewer, attempt, appeal=appeal, adjustment=adjustment)
    recompute_appeal_status(appeal, reviewer=reviewer)
    return adjustment


@transaction.atomic
def reject_appeal_item(item, *, reviewer, response_text="", request=None):
    """
    Bir AppealItem-i rədd edir. Əvvəl qəbul olunub bal verilibsə, həmin düzəliş
    revert olunur (bal geri alınır). Bal dəyişmir (rədd halında).
    """
    item = AppealItem.objects.select_for_update().select_related("appeal").get(pk=item.pk)
    revert_item_adjustment(item)
    _mark_item_resolved(item, APPEAL_ITEM_STATUS_REJECTED, reviewer, response_text)
    recompute_appeal_status(item.appeal, reviewer=reviewer)
    return item


def revert_item_adjustment(item):
    """
    Item üzrə aktiv bal düzəlişini revert edir.

    - Test: düzəliş `reverted=True` olur → effektiv bonusdan çıxır.
    - Yazılı/praktiki: cavabın əvvəlki balı (`previous_answer_score`) bərpa edilir
      və `attempt.teacher_score` cavablardan yenidən hesablanır.
    """
    adjustment = ScoreAdjustment.objects.filter(appeal_item=item, reverted=False).first()
    if adjustment is None:
        return None

    attempt = adjustment.attempt
    exam = attempt.exam

    if getattr(exam, "exam_type", None) != "test" and adjustment.question_id:
        from apps.exams.services.grading import calculate_attempt_score

        answer = item.answer or attempt.answers.filter(question_id=adjustment.question_id).first()
        if answer is not None:
            restore = adjustment.previous_answer_score
            answer.teacher_score = int(restore) if restore is not None else None
            answer.save(update_fields=["teacher_score", "updated_at"])
            new_total = calculate_attempt_score(attempt)
            any_score = attempt.answers.filter(teacher_score__isnull=False).exists()
            attempt.teacher_score = int(new_total) if any_score else None
            attempt.save(update_fields=["teacher_score"])

    adjustment.reverted = True
    adjustment.save(update_fields=["reverted"])
    return adjustment


def recompute_appeal_status(appeal, *, reviewer=None):
    """
    Başlıq statusunu item statuslarından törədir:
    - hamısı accepted → accepted
    - hamısı rejected → rejected
    - qarışıq (accepted + rejected, pending yox) → partially_accepted
    - hələ pending varsa → under_review (qərar başlayıbsa) / pending
    Hamısı həll olunduqda reviewed_at/reviewed_by qeyd olunur.
    """
    statuses = list(appeal.items.values_list("status", flat=True))
    if not statuses:
        return appeal

    has_pending = any(s == APPEAL_ITEM_STATUS_PENDING for s in statuses)
    has_accepted = any(s == APPEAL_ITEM_STATUS_ACCEPTED for s in statuses)
    has_rejected = any(s == APPEAL_ITEM_STATUS_REJECTED for s in statuses)

    update_fields = ["status", "updated_at"]
    fully_resolved = False

    if has_pending:
        new_status = APPEAL_STATUS_UNDER_REVIEW if (has_accepted or has_rejected) else APPEAL_STATUS_PENDING
    elif has_accepted and has_rejected:
        new_status = APPEAL_STATUS_PARTIALLY_ACCEPTED
        fully_resolved = True
    elif has_accepted:
        new_status = APPEAL_STATUS_ACCEPTED
        fully_resolved = True
    else:
        new_status = APPEAL_STATUS_REJECTED
        fully_resolved = True

    appeal.status = new_status
    if fully_resolved:
        appeal.reviewed_at = timezone.now()
        update_fields.append("reviewed_at")
        if reviewer is not None:
            appeal.reviewed_by = reviewer
            update_fields.append("reviewed_by")
    appeal.save(update_fields=update_fields)
    return appeal


__all__ = [
    "accept_appeal_item",
    "appeal_score_state",
    "effective_test_score",
    "recompute_appeal_status",
    "reject_appeal_item",
    "revert_item_adjustment",
]
