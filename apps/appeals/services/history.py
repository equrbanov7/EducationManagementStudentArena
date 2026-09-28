"""Cəhd tarixçəsi provayderi — registrar ``exam_attempt_history`` üçün (Audit 2026-09-28 EXA-03).

Sahibin 2026-09-07 memo-su: «əsas imtahan → apellyasiya → hər 25% təkrar cəhd» izi
tam və DÜZGÜN görünməlidir (koordinator, dekanlıq, rəhbərlik). Registrar bu izi
qurur, amma iki hissəni özü hesablaya bilmir:

* cəhdin faizi — elektron jurnala yazılan RƏSMİ faizlə eyni olmalıdır
  (``exams.services.journal_sync._attempt_percent``: test → apellyasiya bonusu
  DAXİL effektiv faiz; yazılı/praktiki → ``teacher_score`` ÷ ÇATDIRILAN sualların
  snapshot tavanı; yoxlanmamış yazılı → gözləmədə; proctor qovması → 0);
* apellyasiya sətirləri (qərar, bal fərqi, baxan şəxs, tarix).

MODUL SƏRHƏDİ: ``exams → registrar`` istiqaməti mövcuddur, ona görə registrar
nə exams-ı, nə də appeals-i STATİK import edə bilməz (dövri cüt). Registrar bu
modulu app registry üzərindən (``AppealsConfig.attempt_history_provider``) alır —
``ExamAttempt`` modelini ``get_model`` ilə oxuduğu kimi.

Hər iki funksiya TOPLUDUR (roster 500+ tələbə): sorğu sayı cəhd sayından asılı deyil.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import prefetch_related_objects

from apps.appeals.constants import APPEAL_ITEM_STATUS_ACCEPTED, APPEAL_ITEM_STATUS_REJECTED, APPEAL_STATUS_CHOICES
from apps.appeals.models import Appeal
from apps.exams.public import calculate_test_attempt_result

from .scoring import appeal_bonus_map, apply_bonus_to_test_result, delivered_question_points

logger = logging.getLogger(__name__)

_STATUS_LABELS = dict(APPEAL_STATUS_CHOICES)


def _is_test(attempt):
    return getattr(attempt.exam, "exam_type", None) == "test"


def _written_percent(attempt):
    """Yazılı/praktiki: ``teacher_score`` ÷ çatdırılan cavabların snapshot tavanı (journal_sync ilə eyni)."""
    if attempt.teacher_score is None:
        return None  # hələ yoxlanmayıb — jurnal da gözləyir
    answers = list(attempt.answers.all())
    if answers:
        max_score = sum(delivered_question_points(answer, answer.question) for answer in answers)
    else:
        max_score = sum(question.points for question in attempt.exam.questions.all()) or 0
    if not max_score:
        return None
    return round(float(attempt.teacher_score) * 100.0 / float(max_score), 1)


def _test_percent(attempt, bonus):
    """Test: snapshot açarı ilə baza nəticə + apellyasiya bonusu (``effective_test_score`` ilə eyni)."""
    result = calculate_test_attempt_result(attempt, answers=list(attempt.answers.all()))
    return float(apply_bonus_to_test_result(result, bonus).percentage)


def attempt_percents(attempts) -> dict:
    """``attempt_id`` → rəsmi faiz (0–100, 1 onluq) və ya ``None`` (yoxlanmayıb / hesablanmır).

    ``journal_sync._attempt_percent`` qaydasının TOPLU güzgüsüdür — tarixçə
    jurnala yazılan rəqəmdən fərqli faiz göstərməməlidir (əvvəl yazılı final
    ``correct/(correct+wrong)`` = 0 % kimi görünürdü, bonus nəzərə alınmırdı)."""
    attempts = [attempt for attempt in attempts if attempt is not None]
    tests = [attempt for attempt in attempts if _is_test(attempt)]
    written = [attempt for attempt in attempts if not _is_test(attempt)]
    if tests:
        prefetch_related_objects(tests, "answers__question__options", "answers__selected_options")
    if written:
        prefetch_related_objects(written, "answers__question")
    bonus_by_attempt = appeal_bonus_map([attempt.id for attempt in tests]) if tests else {}

    percents = {}
    for attempt in attempts:
        try:
            if getattr(attempt, "supervision_status", "") == "removed":
                percents[attempt.id] = 0.0  # proctor qovması → 0 (avtomatik F), jurnal ilə eyni
            elif _is_test(attempt):
                percents[attempt.id] = _test_percent(attempt, bonus_by_attempt.get(attempt.id))
            else:
                percents[attempt.id] = _written_percent(attempt)
        except Exception:  # noqa: BLE001 — tarixçə heç vaxt səhifəni sındırmır
            logger.exception("appeals.history: percent failed for attempt %s", getattr(attempt, "id", "?"))
            percents[attempt.id] = None
    return percents


def _active_delta(item):
    try:
        adjustment = item.score_adjustment
    except ObjectDoesNotExist:
        return Decimal("0")
    if adjustment is None or adjustment.reverted or not adjustment.delta_points:
        return Decimal("0")
    return adjustment.delta_points


def _appeal_row(appeal):
    items = list(appeal.items.all())
    reviewer = appeal.reviewed_by
    return {
        "appeal_id": appeal.id,
        "attempt_id": appeal.attempt_id,
        "status": appeal.status,
        "status_label": str(_STATUS_LABELS.get(appeal.status, appeal.status)),
        "item_count": len(items),
        "accepted_count": sum(1 for item in items if item.status == APPEAL_ITEM_STATUS_ACCEPTED),
        "rejected_count": sum(1 for item in items if item.status == APPEAL_ITEM_STATUS_REJECTED),
        "delta_points": sum((_active_delta(item) for item in items), Decimal("0")),
        "reviewer_name": (reviewer.get_full_name() or reviewer.get_username()) if reviewer is not None else "",
        "reviewed_at": appeal.reviewed_at,
        "created_at": appeal.created_at,
    }


def appeal_rows_by_attempt(attempt_ids) -> dict:
    """``attempt_id`` → apellyasiya sətirləri (köhnədən yeniyə) — 3 sorğu, cəhd sayından asılı deyil."""
    ids = [pk for pk in attempt_ids if pk]
    if not ids:
        return {}
    appeals = (
        Appeal.objects.filter(attempt_id__in=ids)
        .select_related("reviewed_by")
        .prefetch_related("items__score_adjustment")
        .order_by("created_at", "id")
    )
    rows: dict = {}
    for appeal in appeals:
        rows.setdefault(appeal.attempt_id, []).append(_appeal_row(appeal))
    return rows


__all__ = ["appeal_rows_by_attempt", "attempt_percents"]
