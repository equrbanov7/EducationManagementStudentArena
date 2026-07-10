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
from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.translation import pgettext

from apps.appeals.constants import (
    APPEAL_ITEM_STATUS_ACCEPTED,
    APPEAL_ITEM_STATUS_PENDING,
    APPEAL_ITEM_STATUS_REJECTED,
    APPEAL_STATUS_ACCEPTED,
    APPEAL_STATUS_FINAL,
    APPEAL_STATUS_PARTIALLY_ACCEPTED,
    APPEAL_STATUS_PENDING,
    APPEAL_STATUS_REJECTED,
    APPEAL_STATUS_UNDER_REVIEW,
)
from apps.appeals.models import AppealItem, ScoreAdjustment
from core.helpers import REVIEW_EDIT_LOCK_WINDOW

logger = logging.getLogger(__name__)


def _accept_bonus_points():
    """Apellyasiya QƏBUL olunanda verilən sabit bal (default +1).

    Universitet qaydası: qəbul → +1 bal, rədd → 0. Reviewer əl ilə daha çox və
    ya mənfi bal yaza bilməz — dəyər sabitdir (``settings.APPEAL_ACCEPT_BONUS_POINTS``
    ilə tənzimlənə bilər, amma default 1)."""
    from decimal import Decimal as _D

    from django.conf import settings

    try:
        return _D(str(getattr(settings, "APPEAL_ACCEPT_BONUS_POINTS", 1)))
    except (InvalidOperation, TypeError, ValueError):
        return _D("1")


# ---------------------------------------------------------------------------
# Effektiv bal (baza + apellyasiya bonusları)
# ---------------------------------------------------------------------------
def _review_window_cutoff(at_time=None):
    return (at_time or timezone.now()) - REVIEW_EDIT_LOCK_WINDOW


def appeal_item_result_visible_to_student(item, *, at_time=None):
    """Qərar tələbəyə yalnız 5 dəqiqəlik redaktə pəncərəsi bağlanandan sonra görünür."""
    if item.status == APPEAL_ITEM_STATUS_PENDING:
        return True
    if not item.resolved_at:
        return True
    return (at_time or timezone.now()) >= item.resolved_at + REVIEW_EDIT_LOCK_WINDOW


def appeal_result_hidden_from_student(appeal, *, at_time=None):
    """Apellyasiyada tələbədən gizlədilməli yeni qərar varmı."""
    if appeal.status not in APPEAL_STATUS_FINAL:
        return False
    return any(not appeal_item_result_visible_to_student(item, at_time=at_time) for item in appeal.items.all())


def _student_visible_adjustments(at_time=None):
    cutoff = _review_window_cutoff(at_time)
    return ScoreAdjustment.objects.filter(reverted=False).filter(
        Q(appeal_item__resolved_at__isnull=True) | Q(appeal_item__resolved_at__lte=cutoff)
    )


def _student_visible_fallback_items(at_time=None):
    cutoff = _review_window_cutoff(at_time)
    return _fallback_accepted_bonus_items().filter(Q(resolved_at__isnull=True) | Q(resolved_at__lte=cutoff))


def _score_state_from_sources(attempt, *, adjustments_qs, fallback_items_qs):
    adjustments = list(adjustments_qs.filter(attempt=attempt))
    bonus = sum((adj.delta_points or Decimal("0") for adj in adjustments), Decimal("0"))
    bonus_by_question_id = {}
    for adj in adjustments:
        if not adj.question_id or not adj.delta_points or adj.delta_points <= 0:
            continue
        bonus_by_question_id[adj.question_id] = (
            bonus_by_question_id.get(adj.question_id, Decimal("0")) + adj.delta_points
        )
    fallback_bonus = Decimal("0")
    fallback_credited_question_ids = set()
    fallback_items = (
        fallback_items_qs.filter(appeal__attempt=attempt)
        .select_related("question", "answer")
        .prefetch_related("question__options", "answer__selected_options")
    )
    for item in fallback_items:
        # Eyni sual bir attempt üzrə yalnız BİR dəfə kreditlənir: aktiv audit
        # qeydi (adjustment) və ya əvvəlki fallback item artıq kredit veribsə,
        # bu item ikiqat sayılmır (legacy dublikat qoruması).
        if item.question_id in bonus_by_question_id or item.question_id in fallback_credited_question_ids:
            continue
        item_bonus = _accepted_item_bonus(item, attempt=attempt)
        if item_bonus <= 0:
            continue
        fallback_bonus += item_bonus
        fallback_credited_question_ids.add(item.question_id)
        bonus_by_question_id[item.question_id] = bonus_by_question_id.get(item.question_id, Decimal("0")) + item_bonus
    return {
        "bonus_points": bonus + fallback_bonus,
        "adjustment_count": len(adjustments) + len(fallback_credited_question_ids),
        "credited_question_ids": {adj.question_id for adj in adjustments if adj.delta_points and adj.delta_points > 0}
        | fallback_credited_question_ids,
        "bonus_by_question_id": bonus_by_question_id,
    }


def appeal_score_state(attempt):
    """Attempt üzrə aktiv (revert olunmamış) düzəlişlərin xülasəsi."""
    return _score_state_from_sources(
        attempt,
        adjustments_qs=ScoreAdjustment.objects.filter(reverted=False),
        fallback_items_qs=_fallback_accepted_bonus_items(),
    )


def student_visible_appeal_score_state(attempt, *, at_time=None):
    """Tələbə səthləri üçün yalnız redaktə pəncərəsi bağlanmış bonusların xülasəsi."""
    return _score_state_from_sources(
        attempt,
        adjustments_qs=_student_visible_adjustments(at_time),
        fallback_items_qs=_student_visible_fallback_items(at_time),
    )


def student_visible_appeal_status_by_qid(attempt, *, at_time=None):
    """
    Nəticə səhifəsi üçün: question_id → tələbəyə görünən apellyasiya statusu
    (``"pending"`` | ``"accepted"`` | ``"rejected"``).

    Qərar hələ tələbəyə görünmürsə (5 dəqiqəlik redaktə pəncərəsi) status
    "pending" kimi qaytarılır. Eyni suala bir neçə item düşərsə (legacy
    dublikat) prioritet: accepted > pending > rejected.
    """
    priority = {APPEAL_ITEM_STATUS_ACCEPTED: 2, APPEAL_ITEM_STATUS_PENDING: 1, APPEAL_ITEM_STATUS_REJECTED: 0}
    result = {}
    items = AppealItem.objects.filter(appeal__attempt=attempt).only("status", "resolved_at", "question_id")
    for item in items:
        if item.status == APPEAL_ITEM_STATUS_PENDING or not appeal_item_result_visible_to_student(
            item, at_time=at_time
        ):
            status = APPEAL_ITEM_STATUS_PENDING
        elif item.status in (APPEAL_ITEM_STATUS_ACCEPTED, APPEAL_ITEM_STATUS_REJECTED):
            status = item.status
        else:
            status = APPEAL_ITEM_STATUS_PENDING
        current = result.get(item.question_id)
        if current is None or priority[status] > priority[current]:
            result[item.question_id] = status
    return result


def _effective_test_score_with_bonus(attempt, *, answers=None, bonus):
    from apps.exams.public import calculate_test_attempt_result

    base = calculate_test_attempt_result(attempt, answers=answers)
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


def effective_test_score(attempt, *, answers=None):
    """
    Test attempt-i üçün apellyasiya bonusları nəzərə alınmaqla effektiv bal.

    Qaytarır: dict(base, bonus_points, effective_score, max_score, effective_percentage).
    Faza 4 nəticə səhifəsi bunu istifadə edəcək.

    `answers` verilərsə (prefetch olunmuş attempt.answers.all()), siyahı
    görünüşlərində hər attempt üçün əlavə answer sorğuları yaranmır.
    """
    return _effective_test_score_with_bonus(attempt, answers=answers, bonus=appeal_score_state(attempt)["bonus_points"])


def student_visible_effective_test_score(attempt, *, answers=None, at_time=None):
    """Test attempt-i üçün tələbəyə görünən effektiv bal."""
    bonus = student_visible_appeal_score_state(attempt, at_time=at_time)["bonus_points"]
    return _effective_test_score_with_bonus(attempt, answers=answers, bonus=bonus)


def _bonus_map_from_sources(attempt_ids, *, adjustments_qs, fallback_items_qs):
    """
    attempt_id → aktiv (revert olunmamış) apellyasiya bonuslarının cəmi.

    Siyahı görünüşləri (müəllim nəticə cədvəli, tələbə nəticələri, export) üçün
    TƏK sorğu — hər attempt üçün ayrıca appeal_score_state çağırmaq əvəzinə.
    """
    ids = [pk for pk in attempt_ids if pk]
    if not ids:
        return {}
    rows = (
        adjustments_qs.filter(attempt_id__in=ids)
        .values("attempt_id", "question_id")
        .annotate(total=Sum("delta_points"))
    )
    bonus_by_attempt = {}
    credited_pairs = set()  # (attempt_id, question_id) — artıq kredit alan suallar
    for row in rows:
        attempt_id = row["attempt_id"]
        total = row["total"] or Decimal("0")
        bonus_by_attempt[attempt_id] = bonus_by_attempt.get(attempt_id, Decimal("0")) + total
        if total > 0 and row["question_id"]:
            credited_pairs.add((attempt_id, row["question_id"]))
    fallback_items = (
        fallback_items_qs.filter(appeal__attempt_id__in=ids)
        .select_related("appeal", "question", "answer")
        .prefetch_related("question__options", "answer__selected_options")
    )
    for item in fallback_items:
        attempt_id = item.appeal.attempt_id
        # Eyni sual bir attempt üzrə yalnız BİR dəfə kreditlənir (legacy
        # dublikat qoruması) — bax _score_state_from_sources.
        if (attempt_id, item.question_id) in credited_pairs:
            continue
        item_bonus = _accepted_item_bonus(item)
        if item_bonus <= 0:
            continue
        credited_pairs.add((attempt_id, item.question_id))
        bonus_by_attempt[attempt_id] = bonus_by_attempt.get(attempt_id, Decimal("0")) + item_bonus
    return bonus_by_attempt


def appeal_bonus_map(attempt_ids):
    return _bonus_map_from_sources(
        attempt_ids,
        adjustments_qs=ScoreAdjustment.objects.filter(reverted=False),
        fallback_items_qs=_fallback_accepted_bonus_items(),
    )


def student_visible_appeal_bonus_map(attempt_ids, *, at_time=None):
    return _bonus_map_from_sources(
        attempt_ids,
        adjustments_qs=_student_visible_adjustments(at_time),
        fallback_items_qs=_student_visible_fallback_items(at_time),
    )


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


def _fallback_accepted_bonus_items():
    """
    Köhnə data qoruması: bəzi qəbul edilmiş test apellyasiyalarında
    ScoreAdjustment audit qeydi olmaya bilər. Belə item-lər də effektiv balda
    görünməlidir, amma aktiv audit qeydi olanlar ikiqat sayılmamalıdır.
    """
    return AppealItem.objects.filter(
        appeal__attempt__exam__exam_type="test",
        status=APPEAL_ITEM_STATUS_ACCEPTED,
    ).filter(Q(score_adjustment__isnull=True) | Q(score_adjustment__reverted=True))


def _accepted_item_bonus(item, *, attempt=None):
    answer = item.answer
    if answer is None and attempt is not None:
        answer = (
            attempt.answers.filter(question=item.question).prefetch_related("selected_options").order_by("id").first()
        )
    if _question_already_correct(answer, item.question):
        return Decimal("0")
    return _accept_bonus_points()


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
    Bir AppealItem-i qəbul edir və idempotent bal düzəlişi tətbiq edir.

    Universitet qaydası (2026-07): qəbul → **sabit +1 bal** (``_accept_bonus_points``),
    rədd → 0. ``awarded_points`` artıq NƏZƏRƏ ALINMIR — reviewer daha çox və ya
    mənfi bal yaza bilməz (parametr geriyə-uyğunluq üçün qalır).

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
    bonus = _accept_bonus_points()  # sabit +1 (awarded_points nəzərə alınmır)

    # Eyni sual bir attempt üzrə yalnız BİR dəfə kreditlənir. Yaratma
    # validasiyası dublikatı bloklayır, amma köhnə (legacy) dublikat item-lər
    # üçün də qəbul zamanı ikinci bonus verilmir (delta 0 qalır).
    already_credited = (
        ScoreAdjustment.objects.filter(attempt=attempt, question=question, reverted=False)
        .exclude(appeal_item=item)
        .exists()
    )

    if getattr(exam, "exam_type", None) == "test":
        # Test: bal cavab açarından hesablandığı üçün additiv bonus (delta = +1).
        prev_is_correct = _question_already_correct(answer, question)
        previous_score = effective_test_score(attempt)["effective_score"]
        # Artıq düzgün sayılırsa və ya sual artıq kreditlənibsə ikiqat kredit olmasın.
        delta = Decimal("0") if (prev_is_correct or already_credited) else bonus
        new_is_correct = True if delta > 0 else None
        new_score = previous_score + delta
    else:
        # Yazılı/praktiki: cavabın balına +1 (sualın maksimumu ilə clamp),
        # sonra attempt.teacher_score cavablardan yenidən hesablanır.
        from apps.exams.public import calculate_attempt_score

        previous_answer_score = (
            Decimal(str(answer.teacher_score)) if (answer is not None and answer.teacher_score is not None) else None
        )
        previous_score = calculate_attempt_score(attempt)
        if answer is not None and not already_credited:
            base = previous_answer_score if previous_answer_score is not None else Decimal("0")
            target = base + bonus
            if target > question_points:
                target = question_points
            answer.teacher_score = int(target)
            answer.save(update_fields=["teacher_score", "updated_at"])
        new_score = calculate_attempt_score(attempt)
        delta = new_score - previous_score
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
    "appeal_item_result_visible_to_student",
    "appeal_result_hidden_from_student",
    "appeal_score_state",
    "apply_bonus_to_test_result",
    "effective_test_score",
    "recompute_appeal_status",
    "reject_appeal_item",
    "revert_item_adjustment",
    "student_visible_appeal_bonus_map",
    "student_visible_appeal_score_state",
    "student_visible_effective_test_score",
]
