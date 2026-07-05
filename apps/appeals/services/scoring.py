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
from dataclasses import replace as _dataclass_replace
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import pgettext

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


def effective_test_score(attempt, *, answers=None):
    """
    Test attempt-i üçün apellyasiya bonusları nəzərə alınmaqla effektiv bal.

    Qaytarır: dict(base, bonus_points, effective_score, max_score, effective_percentage).
    Faza 4 nəticə səhifəsi bunu istifadə edəcək.

    `answers` verilərsə (prefetch olunmuş attempt.answers.all()), siyahı
    görünüşlərində hər attempt üçün əlavə answer sorğuları yaranmır.
    """
    from apps.exams.public import calculate_test_attempt_result

    base = calculate_test_attempt_result(attempt, answers=answers)
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


def appeal_bonus_map(attempt_ids):
    """
    attempt_id → aktiv (revert olunmamış) apellyasiya bonuslarının cəmi.

    Siyahı görünüşləri (müəllim nəticə cədvəli, tələbə nəticələri, export) üçün
    TƏK sorğu — hər attempt üçün ayrıca appeal_score_state çağırmaq əvəzinə.
    """
    ids = [pk for pk in attempt_ids if pk]
    if not ids:
        return {}
    rows = (
        ScoreAdjustment.objects.filter(attempt_id__in=ids, reverted=False)
        .values("attempt_id")
        .annotate(total=Sum("delta_points"))
    )
    return {row["attempt_id"]: row["total"] or Decimal("0") for row in rows}


def apply_bonus_to_test_result(result, bonus):
    """
    Apellyasiya bonusu tətbiq edilmiş YENİ TestAttemptResult qaytarır:
    bal maks. balla clamp olunur, faiz yenidən hesablanır. Bonus yoxdursa
    (None/0/mənfi) nəticə dəyişmir.

    Düzgün/səhv sayları dəyişmir — apellyasiya additiv bal düzəlişidir,
    cavab açarı yox (bax: modul docstring).
    """
    if result is None:
        return result
    try:
        bonus = Decimal(str(bonus if bonus is not None else 0))
    except (InvalidOperation, TypeError, ValueError):
        return result
    if bonus <= 0:
        return result

    effective_score = result.score + bonus
    if result.max_score and effective_score > result.max_score:
        effective_score = result.max_score
    if result.max_score and result.max_score > 0:
        percentage = (effective_score * Decimal("100") / result.max_score).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
    else:
        percentage = Decimal("0")
    return _dataclass_replace(result, score=effective_score, percentage=percentage)


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


def _coerce_awarded_points(value, max_points):
    """
    Reviewer-in əl ilə daxil etdiyi balı [0, max_points] aralığına gətirir.

    None / boş / yanlış → None qaytarır (default davranış: tam bal). Bu sayədə
    mövcud çağırışlar (awarded_points verilmədikdə) heç dəyişmir.
    """
    if value is None or value == "":
        return None
    try:
        points = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if points < 0:
        points = Decimal("0")
    if max_points is not None and points > max_points:
        points = max_points
    return points


def _mark_item_resolved(item, status, reviewer, response_text):
    item.status = status
    if response_text:
        item.reviewer_response = response_text
    item.resolved_by = reviewer
    item.resolved_at = timezone.now()
    item.save(update_fields=["status", "reviewer_response", "resolved_by", "resolved_at", "updated_at"])


def _audit_score_change(request, reviewer, attempt, *, appeal, adjustment):
    try:
        from apps.audit.public import log_action
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
def accept_appeal_item(item, *, reviewer, response_text="", request=None, awarded_points=None):
    """
    Bir AppealItem-i qəbul edir və (test üçün) idempotent bal düzəlişi tətbiq edir.

    ``awarded_points`` (opsional): reviewer həmin suala neçə bal veriləcəyini əl
    ilə təyin edə bilər (0..sualın maksimum balı). Verilmədikdə (None) davranış
    əvvəlki kimidir — sual üçün TAM bal verilir.

    Eyni item üçün artıq aktiv düzəliş varsa, bal təkrar ARTIRILMIR — yalnız
    status/cavab yenilənir.
    """
    item = (
        AppealItem.objects.select_for_update()
        .select_related("appeal", "appeal__attempt", "appeal__attempt__exam", "question")
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

    awarded = _coerce_awarded_points(awarded_points, question_points)

    if getattr(exam, "exam_type", None) == "test":
        # Test: bal cavab açarından hesablandığı üçün additiv bonus (delta).
        prev_is_correct = _question_already_correct(answer, question)
        previous_score = effective_test_score(attempt)["effective_score"]
        base_contribution = question_points if prev_is_correct else Decimal("0")
        # Default (awarded=None) → tam bal; əks halda reviewer-in təyin etdiyi bal.
        target = question_points if awarded is None else awarded
        delta = target - base_contribution
        if delta < 0:
            delta = Decimal("0")
        new_is_correct = True if target >= question_points else None
        new_score = previous_score + delta
    else:
        # Yazılı/praktiki: sual üçün TAM bal verilir (answer.teacher_score = points),
        # sonra attempt.teacher_score cavablardan yenidən hesablanır. Beləliklə
        # nəticə dərhal əks olunur (test-dən fərqli olaraq, ayrıca bonus qatı yox).
        from apps.exams.public import calculate_attempt_score

        previous_answer_score = (
            Decimal(str(answer.teacher_score)) if (answer is not None and answer.teacher_score is not None) else None
        )
        previous_score = calculate_attempt_score(attempt)
        if answer is not None:
            if awarded is None:
                # Default: tam bal (yalnız əvvəlki bal tamdan azdırsa qaldır).
                if previous_answer_score is None or previous_answer_score < question_points:
                    answer.teacher_score = int(question_points)
                    answer.save(update_fields=["teacher_score", "updated_at"])
            else:
                # Reviewer-in təyin etdiyi bal (qismən bal mümkündür).
                answer.teacher_score = int(awarded)
                answer.save(update_fields=["teacher_score", "updated_at"])
        new_score = calculate_attempt_score(attempt)
        delta = new_score - previous_score
        # Revert yolu ilə eyni qayda: hər hansı cavabda bal varsa yekun bal
        # yenidən hesablanmış dəyərdir (0 daxil olmaqla) — əks halda None.
        # Əvvəlki "if new_score > 0" şərti 0 balda köhnə dəyəri saxlayırdı.
        any_score = attempt.answers.filter(teacher_score__isnull=False).exists()
        attempt.teacher_score = int(new_score) if any_score else None
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
        from apps.exams.public import calculate_attempt_score

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

    previous_status = appeal.status
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

    # Tələbəyə bildiriş — yalnız status İLK DƏFƏ final vəziyyətə keçəndə
    # (pending/under_review → accepted/rejected/partially_accepted). Müəllim
    # 5 dəqiqəlik pəncərədə qərarı redaktə edəndə dublikat bildiriş yaranmır.
    final_statuses = {APPEAL_STATUS_ACCEPTED, APPEAL_STATUS_REJECTED, APPEAL_STATUS_PARTIALLY_ACCEPTED}
    if fully_resolved and previous_status not in final_statuses:
        _notify_student_appeal_resolved(appeal)
    return appeal


def _notify_student_appeal_resolved(appeal):
    """Apellyasiya nəticələnəndə tələbəyə in-app bildiriş. Xəta flow-u pozmur."""
    try:
        from django.urls import reverse

        from apps.notifications.public import create_notification

        create_notification(
            recipient=appeal.student,
            title=pgettext("appeals.notification", "Apellyasiyanıza baxıldı"),
            message=pgettext(
                "appeals.notification",
                '"{exam}" imtahanı üzrə apellyasiyanız nəticələndi. Nəticəyə baxın.',
            ).format(exam=appeal.exam.title),
            link=reverse("appeals:appeal_detail", kwargs={"appeal_id": appeal.id}),
            notification_type="grade",
            metadata={"appeal_id": appeal.id, "attempt_id": appeal.attempt_id, "exam_id": appeal.exam_id},
            organization=appeal.organization,
        )
    except Exception:
        logger.warning("Appeal resolved notification failed.", exc_info=True)


__all__ = [
    "accept_appeal_item",
    "appeal_bonus_map",
    "appeal_score_state",
    "apply_bonus_to_test_result",
    "effective_test_score",
    "recompute_appeal_status",
    "reject_appeal_item",
    "revert_item_adjustment",
]
