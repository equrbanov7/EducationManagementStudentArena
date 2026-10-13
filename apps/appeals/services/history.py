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
from django.utils.translation import pgettext

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
        "kind": "appeal",
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
    # 2026-10-13 (gecə): cavab açarı düzəlişi də cəhdin balını dəyişir — eyni tarixçə sətri formatında
    # (``status_label`` / ``delta_points`` / ``reviewer_name`` / ``reviewed_at``) əlavə olunur ki, mövcud
    # şablonlar (``_exam_attempt_history.html``) dəyişmədən göstərsin. Geri alınmış düzəliş də QALIR.
    for row in key_correction_rows(ids):
        rows.setdefault(row["attempt_id"], []).append(row)
    for attempt_rows in rows.values():
        attempt_rows.sort(key=lambda row: row["created_at"])  # stabil: eyni an → əvvəlki sıra qalır
    return rows


def key_correction_rows(attempt_ids) -> list:
    """Açar düzəlişi kreditlərinin tarixçə sətirləri — 1 sorğu."""
    from apps.appeals.models import KeyCorrectionCredit

    credits = (
        KeyCorrectionCredit.objects.filter(attempt_id__in=list(attempt_ids), delta_points__gt=0)
        .select_related("correction", "correction__created_by", "correction__revoked_by")
        .order_by("created_at", "id")
    )
    rows = []
    for credit in credits:
        correction = credit.correction
        revoked = correction.revoked_at is not None or credit.reverted
        actor = correction.revoked_by if revoked and correction.revoked_by_id else correction.created_by
        rows.append(
            {
                "kind": "key_correction",
                "appeal_id": None,
                "attempt_id": credit.attempt_id,
                "status": "key_revoked" if revoked else "key_corrected",
                "status_label": str(
                    pgettext("appeals.history", "Cavab açarı düzəlişi geri alındı")
                    if revoked
                    else pgettext("appeals.history", "Cavab açarı düzəldildi (hamı üçün)")
                ),
                "item_count": 1,
                "accepted_count": 0 if revoked else 1,
                "rejected_count": 0,
                "delta_points": Decimal("0") if revoked else credit.delta_points,
                "reviewer_name": (actor.get_full_name() or actor.get_username()) if actor is not None else "",
                "reviewed_at": correction.revoked_at if revoked else correction.created_at,
                "created_at": correction.created_at,
            }
        )
    return rows


#: Dekan / koordinator oxu səthində göstərilən kateqoriyalar (apellyasiya olunanlar).
_HISTORY_CATEGORIES = ("final", "midterm")


def _fmt_dt(value):
    from django.utils import timezone

    return timezone.localtime(value).strftime("%d.%m.%Y %H:%M") if value else ""


def _fmt_points(value):
    text = f"{Decimal(str(value or 0)):.2f}".rstrip("0").rstrip(".")
    return text if text.startswith("-") else f"+{text}"


def student_exam_history(*, student, organization, limit=60) -> list:
    """Tələbənin final + midterm cəhdləri və apellyasiya / açar düzəlişi izi — YALNIZ-OXU (2026-10-13, gecə).

    Sahibin 2026-09-07 memo-su: «əsas imtahan → apellyasiya → hər təkrar cəhd» izi koordinator,
    dekanlıq və rəhbərlik üçün görünməlidir. Jurnal «Yekun» tab-ı yalnız finalı və yalnız fənn
    müəllimi/jurnal görünüşündə göstərirdi; «Akademik qeydlər» çekməcəsində (dekan/koordinator
    scope-u) bu iz yox idi. Sətirlər JSON-a hazırdır (tarixlər Bakı vaxtı ilə mətn).

    Sorğu sayı cəhd sayından asılı deyil (toplu faiz + toplu apellyasiya sətirləri)."""
    from django.apps import apps as django_apps

    if student is None or organization is None:
        return []
    attempt_model = django_apps.get_model("exams", "ExamAttempt")
    from apps.exams.public import ATTEMPT_FINISHED_STATUSES

    attempts = list(
        attempt_model.objects.filter(
            user=student,
            is_trial=False,
            status__in=ATTEMPT_FINISHED_STATUSES,
            exam__organization=organization,
            exam__exam_type_extended__in=_HISTORY_CATEGORIES,
        )
        .select_related("exam", "exam__subject")
        .order_by("finished_at", "id")[:limit]
    )
    if not attempts:
        return []
    percents = attempt_percents(attempts)
    appeals = appeal_rows_by_attempt([attempt.id for attempt in attempts])
    groups: dict = {}
    for attempt in attempts:
        exam = attempt.exam
        key = (exam.subject_id or f"exam-{exam.id}", exam.exam_type_extended)
        groups.setdefault(key, []).append(attempt)
    category_labels = {
        "final": str(pgettext("appeals.history", "Yekun (final)")),
        "midterm": str(pgettext("appeals.history", "Aralıq (midterm)")),
    }
    rows = []
    for (_, category), group in groups.items():
        for index, attempt in enumerate(group, start=1):
            exam = attempt.exam
            subject = getattr(exam, "subject", None)
            rows.append(
                {
                    "attempt_id": attempt.id,
                    "subject": getattr(subject, "name", "") or exam.title,
                    "exam_title": exam.title,
                    "category": category,
                    "category_label": category_labels.get(category, category),
                    "number": index,
                    "percent": percents.get(attempt.id),
                    "is_official": index == len(group),
                    "is_expelled": getattr(attempt, "supervision_status", "") == "removed",
                    "finished_at": _fmt_dt(attempt.finished_at or attempt.started_at),
                    "appeals": [
                        {
                            "status_label": row["status_label"],
                            "delta": _fmt_points(row["delta_points"]) if row.get("delta_points") else "",
                            "reviewer": row.get("reviewer_name") or "",
                            "at": _fmt_dt(row.get("reviewed_at") or row.get("created_at")),
                        }
                        for row in appeals.get(attempt.id, [])
                    ],
                }
            )
    rows.sort(key=lambda row: (row["subject"].lower(), row["category"], row["number"]))
    return rows


__all__ = [
    "appeal_rows_by_attempt",
    "attempt_percents",
    "key_correction_rows",
    "student_exam_history",
]
