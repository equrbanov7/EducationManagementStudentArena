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
from apps.exams.services.result_answers import prefetch_score_answers
from apps.exams.services.result_calculation import calculate_test_attempt_result

CHUNK_SIZE = 200


def test_score_map(attempts_qs) -> dict[int, Decimal]:
    """``attempt_id`` → cədvəldəki «Bal» (apellyasiya bonusu daxil)."""
    scores: dict[int, Decimal] = {}
    batch: list = []

    def flush():
        prefetch_score_answers(batch)
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


__all__ = ["test_score_map"]
