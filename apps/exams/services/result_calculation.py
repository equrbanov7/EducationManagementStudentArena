from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


def _as_decimal(value, default="0"):
    try:
        return Decimal(str(value if value is not None else default))
    except Exception:
        return Decimal(default)


def _format_decimal(value):
    value = _as_decimal(value)
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.quantize(Decimal("0.01")).normalize(), "f")


def _percentage(score, max_score):
    max_score = _as_decimal(max_score)
    if max_score <= 0:
        return Decimal("0")
    return (score * Decimal("100") / max_score).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _option_ids(option_manager):
    return {option.id for option in option_manager.all()}


@dataclass(frozen=True)
class TestAttemptResult:
    correct_count: int
    wrong_count: int
    unanswered_count: int
    delivered_count: int
    score: Decimal
    max_score: Decimal
    percentage: Decimal
    used_legacy_fallback: bool = False

    @property
    def score_display(self):
        return _format_decimal(self.score)

    @property
    def max_score_display(self):
        return _format_decimal(self.max_score)

    @property
    def percentage_display(self):
        return _format_decimal(self.percentage)


def _legacy_test_attempt_result(attempt):
    correct_count = int(getattr(attempt, "correct_count", 0) or 0)
    wrong_count = int(getattr(attempt, "wrong_count", 0) or 0)
    delivered_count = correct_count + wrong_count
    score = Decimal(correct_count)
    max_score = Decimal(delivered_count)
    return TestAttemptResult(
        correct_count=correct_count,
        wrong_count=wrong_count,
        unanswered_count=0,
        delivered_count=delivered_count,
        score=score,
        max_score=max_score,
        percentage=_percentage(score, max_score),
        used_legacy_fallback=True,
    )


def calculate_test_attempt_result(attempt, *, answers=None):
    """
    Calculate a test attempt only from the questions delivered to that attempt.

    Random exams persist the delivered set as ExamAnswer rows, so this function
    deliberately uses attempt.answers instead of the full question bank.
    """
    if getattr(getattr(attempt, "exam", None), "exam_type", None) != "test":
        return TestAttemptResult(0, 0, 0, 0, Decimal("0"), Decimal("0"), Decimal("0"))

    if answers is None:
        answers = (
            attempt.answers.select_related("question")
            .prefetch_related("question__options", "selected_options")
            .order_by("id")
        )
    answers = list(answers)

    if not answers:
        return _legacy_test_attempt_result(attempt)

    correct_count = 0
    wrong_count = 0
    unanswered_count = 0
    score = Decimal("0")
    max_score = Decimal("0")

    for answer in answers:
        question = answer.question
        points = _as_decimal(getattr(question, "points", 1), default="1")
        max_score += points

        selected_option_ids = _option_ids(answer.selected_options)
        if not selected_option_ids:
            unanswered_count += 1
            continue

        correct_option_ids = {option.id for option in question.options.all() if option.is_correct}
        if correct_option_ids and selected_option_ids == correct_option_ids:
            correct_count += 1
            score += points
        else:
            wrong_count += 1

    return TestAttemptResult(
        correct_count=correct_count,
        wrong_count=wrong_count,
        unanswered_count=unanswered_count,
        delivered_count=len(answers),
        score=score,
        max_score=max_score,
        percentage=_percentage(score, max_score),
    )


def sync_test_attempt_counts(attempt, *, answers=None):
    result = calculate_test_attempt_result(attempt, answers=answers)
    attempt.correct_count = result.correct_count
    attempt.wrong_count = result.wrong_count
    attempt.save(update_fields=["correct_count", "wrong_count"])
    return result


def attach_test_result_summaries(attempts):
    """
    Hər test attempt-inə `.test_result` əlavə edir — qəbul olunmuş apellyasiya
    bonusları DAXİL (effektiv bal). Bonuslar bütün attempt-lər üçün tək
    sorğu ilə yığılır (per-attempt sorğu yox).
    """
    test_attempts = [
        attempt for attempt in attempts if getattr(getattr(attempt, "exam", None), "exam_type", None) == "test"
    ]
    if not test_attempts:
        return attempts

    # M2 (2026-07-02): appeals-ə birbaşa import ƏVƏZİNƏ exams-ın öz
    # genişlənmə nöqtəsi (score_adjustments) — appeals ready()-də qoşulur.
    from apps.exams import score_adjustments

    bonus_by_attempt_id = score_adjustments.bonus_map([attempt.id for attempt in test_attempts])
    apply_bonus = score_adjustments.apply_bonus

    # Faza 4 (audit 2026-07-02): N+1 aradan qaldırıldı — bütün attempt-lərin
    # cavabları TƏK sorğu dəsti ilə (base + 2 prefetch) yığılır və
    # calculate_test_attempt_result-a hazır ötürülür. Boş siyahı halında
    # funksiya əvvəlki kimi legacy fallback-a düşür (davranış eynidir).
    from apps.exams.models import ExamAnswer

    answers_by_attempt_id: dict[int, list] = {attempt.id: [] for attempt in test_attempts}
    answers_qs = (
        ExamAnswer.objects.filter(attempt_id__in=list(answers_by_attempt_id))
        .select_related("question")
        .prefetch_related("question__options", "selected_options")
        .order_by("id")
    )
    for answer in answers_qs:
        answers_by_attempt_id[answer.attempt_id].append(answer)

    for attempt in test_attempts:
        result = calculate_test_attempt_result(attempt, answers=answers_by_attempt_id.get(attempt.id, []))
        bonus = bonus_by_attempt_id.get(attempt.id)
        if bonus:
            result = apply_bonus(result, bonus)
        attempt.test_result = result
    return attempts


__all__ = [
    "TestAttemptResult",
    "attach_test_result_summaries",
    "calculate_test_attempt_result",
    "sync_test_attempt_counts",
]
