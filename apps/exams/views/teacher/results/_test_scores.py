"""results paketi — test imtahanı üçün cəhd → effektiv bal xəritəsi (bal aralığı / bal sıralaması).

Test balı DB-də saxlanmır: çatdırılan sual snapshot-undan + seçim snapshot-undan
(`calculate_test_attempt_result`) və qəbul olunmuş apellyasiya bonusu ilə hesablanır —
cədvəldə görünən «Bal» ilə eyni. Yalnız müəllim bal süzgəci və ya bal sıralaması seçəndə
çağırılır; cəhdlər hissə-hissə (prefetch ilə) oxunur — yaddaş sabit, sorğu sayı hissə
sayına mütənasib (sətir başına sorğu yoxdur).
"""

from __future__ import annotations

from decimal import Decimal

from apps.exams import score_adjustments
from apps.exams.services.result_calculation import calculate_test_attempt_result

CHUNK_SIZE = 200


def attach_legacy_selected_options(attempts) -> None:
    """Cavabların ``selected_options`` keşini doldur — yalnız seçim snapshot-u OLMAYAN köhnə cavablar üçün.

    2026-10-25 (prod kopyası): ``answers__selected_options`` prefetch-i RLS altında sətir başına iç-içə
    siyasət yoxlaması edir — 28 cəhdlik imtahanda ~6.4 s (səhifənin 85 %-i). Halbuki
    ``answer_scoring_keys`` seçimi ``selected_option_ids_snapshot``-dan oxuyur; canlı M2M yalnız
    snapshot-u ``None`` olan köhnə cavablar üçündür (prod-da onların seçim sətri 0). İndi M2M yalnız
    həmin cavablar üçün TƏK sorğu ilə gətirilir; qalanlarına boş keş qoyulur (heç vaxt oxunmur).
    """
    from apps.exams.models import ExamAnswer

    through = ExamAnswer.selected_options.through
    option_model = ExamAnswer.selected_options.field.related_model
    answers = [answer for attempt in attempts for answer in attempt.answers.all()]
    legacy_ids = [answer.pk for answer in answers if answer.selected_option_ids_snapshot is None]
    by_answer: dict = {}
    if legacy_ids:
        rows = through.objects.filter(examanswer_id__in=legacy_ids).select_related("examquestionoption")
        for row in rows:
            by_answer.setdefault(row.examanswer_id, []).append(row.examquestionoption)
    for answer in answers:
        cached = option_model.objects.none()
        cached._result_cache = by_answer.get(answer.pk, [])
        cached._prefetch_done = True
        answer._prefetched_objects_cache = {
            **getattr(answer, "_prefetched_objects_cache", {}),
            "selected_options": cached,
        }


def test_score_map(attempts_qs) -> dict[int, Decimal]:
    """``attempt_id`` → cədvəldəki «Bal» (apellyasiya bonusu daxil)."""
    scores: dict[int, Decimal] = {}
    batch: list = []

    def flush():
        attach_legacy_selected_options(batch)
        bonuses = score_adjustments.bonus_map([att.id for att in batch])
        for att in batch:
            result = calculate_test_attempt_result(att, answers=att.answers.all())
            bonus = bonuses.get(att.id) or 0
            if bonus:
                result = score_adjustments.apply_bonus(result, bonus)
            scores[att.id] = Decimal(str(result.score or 0))
        batch.clear()

    for attempt in attempts_qs.order_by("id").iterator(chunk_size=CHUNK_SIZE):
        batch.append(attempt)
        if len(batch) >= CHUNK_SIZE:
            flush()
    if batch:
        flush()
    return scores


__all__ = ["attach_legacy_selected_options", "test_score_map"]
