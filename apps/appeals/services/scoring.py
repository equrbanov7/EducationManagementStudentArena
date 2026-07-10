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

from dataclasses import replace as _dataclass_replace
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db.models import Q, Sum
from django.utils import timezone

from apps.appeals.constants import (
    APPEAL_ITEM_STATUS_ACCEPTED,
    APPEAL_ITEM_STATUS_PENDING,
    APPEAL_ITEM_STATUS_REJECTED,
    APPEAL_STATUS_FINAL,
)
from apps.appeals.models import AppealItem, ScoreAdjustment
from core.helpers import REVIEW_EDIT_LOCK_WINDOW


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


# ---------------------------------------------------------------------------
# Qərar əməliyyatları decisions.py-dədir. Geriyə uyğunluq üçün re-export:
# `from apps.appeals.services.scoring import accept_appeal_item` işləməyə davam etsin.
# (Import faylın sonundadır ki, decisions.py yuxarıdakı köməkçiləri import edə bilsin
#  — tək istiqamətli asılılıq, dövri import yaranmır.)
# ---------------------------------------------------------------------------
from .decisions import (  # noqa: E402
    accept_appeal_item,
    recompute_appeal_status,
    reject_appeal_item,
    revert_item_adjustment,
)

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
