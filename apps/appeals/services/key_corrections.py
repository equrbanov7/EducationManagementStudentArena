"""Cavab AÇARININ düzəlişi — sualı cavablayan BÜTÜN tələbələr üçün (2026-10-13, gecə).

Sahib: «apellyasiyaya verilmə, cavabın düzəldilməsi…». İmtahan mərkəzi apellyasiyaya baxanda
iki variant var:

1. **Yalnız bu tələbə** — mövcud qərar (``decisions.accept_appeal_item``): sabit +1 bal;
2. **Açar səhvdir → hamı üçün** — bu modul: düzgün variant(lar) seçilir, səbəb yazılır və
   həmin imtahanın bu sualını cavablayan hər bitmiş (sınaq olmayan) cəhd yoxlanılır. Yeni
   açara UYĞUN cavab verib köhnə açarla səhv sayılan tələbəyə eyni qayda ilə kredit verilir
   (``APPEAL_ACCEPT_BONUS_POINTS``, sualın çatdırılan balı ilə məhdud).

Dizayn qərarları (tövsiyə olunan variant):

* **Heç kimin balı AZALMIR.** Köhnə açarla düz sayılan tələbə krediti saxlayır (açar səhvi
  tələbənin günahı deyil) — düzəliş yalnız ARTIRIR.
* **Tarixçə yenidən yazılmır.** ``ExamAnswer.question_snapshot`` və seçimlər toxunulmaz qalır;
  kredit ayrıca ``KeyCorrectionCredit`` sətridir, effektiv bal = baza + kreditlər
  (``scoring`` modulundakı additiv dizayn). Rəsmi jurnal balı ``journal_sync`` ilə
  yenilənir və registrar ledger-ində ``ExamScoreEntry(kind=appeal)`` sətri qalır (append-only).
* **İdempotent.** Bir sual üçün eyni anda bir aktiv düzəliş (DB unique constraint); eyni
  (düzəliş, cəhd) üçün bir kredit sətri; fərdi apellyasiya krediti ilə eyni sual ikiqat
  sayılmır (oxuma anında dedup).
* **Geri alına bilir** (səhv düzəliş üçün): sətir silinmir — ``revoked_at`` + kreditlər
  ``reverted``; ledger, audit, jurnal və bildirişlər eyni yolla yazılır.
* **Fail-closed ledger**: ``ExamGradeEvent`` yazıla bilmirsə bütün əməliyyat geri qayıdır.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from apps.appeals.constants import APPEAL_MAX_COMMENT_LENGTH
from apps.appeals.models import AnswerKeyCorrection, AppealItem, KeyCorrectionCredit
from apps.exams.public import ATTEMPT_FINISHED_STATUSES, calculate_test_attempt_result

from .scoring import _accept_bonus_points, appeal_bonus_map, delivered_question_points

logger = logging.getLogger(__name__)

#: Səbəb mətninin minimum uzunluğu — kütləvi bal dəyişikliyi izahsız qalmasın.
KEY_CORRECTION_MIN_REASON = 10


def _error(message):
    return ValidationError(pgettext("appeals.service.key_correction.error", message))


def _selected_ids(answer):
    frozen = getattr(answer, "selected_option_ids_snapshot", None)
    if frozen is not None:
        return {int(option_id) for option_id in frozen}
    return {option.id for option in answer.selected_options.all()}


def _snapshot_options(answer):
    snapshot = getattr(answer, "question_snapshot", None)
    options = snapshot.get("options") if isinstance(snapshot, dict) else None
    return options or []


def _delivered_correct_ids(answer):
    """Bu cavabın ÇATDIRILDIĞI andakı açar (snapshot yoxdursa canlı açar)."""
    options = _snapshot_options(answer)
    if options:
        return {int(option["id"]) for option in options if option.get("is_correct")}
    return {option.id for option in answer.question.options.all() if option.is_correct}


def key_option_choices(answer, question):
    """Açar düzəlişi formu üçün variantlar — çatdırılan snapshot-dan (yoxdursa canlı sual)."""
    options = _snapshot_options(answer) if answer is not None else []
    if options:
        return [
            {
                "id": int(option["id"]),
                "label": option.get("label", ""),
                "text": option.get("text", ""),
                "is_correct": bool(option.get("is_correct")),
            }
            for option in options
        ]
    return [
        {"id": option.id, "label": option.label, "text": option.text, "is_correct": bool(option.is_correct)}
        for option in question.options.all()
    ]


def active_correction_for(question_id):
    return (
        AnswerKeyCorrection.objects.filter(question_id=question_id, revoked_at__isnull=True)
        .select_related("created_by")
        .first()
    )


def _clean_corrected_ids(raw_ids, allowed_ids):
    try:
        corrected = {int(value) for value in raw_ids or [] if str(value).strip()}
    except (TypeError, ValueError):
        raise _error("Düzgün variant seçimi yanlışdır.")
    if not corrected:
        raise _error("Ən azı bir düzgün variant seçin.")
    if not corrected <= set(allowed_ids):
        raise _error("Seçilən variant bu suala aid deyil.")
    return corrected


def _clean_reason(reason):
    reason = (reason or "").strip()
    if len(reason) < KEY_CORRECTION_MIN_REASON:
        raise ValidationError(
            pgettext(
                "appeals.service.key_correction.error", "Açar düzəlişinin səbəbini yazın (ən azı {n} simvol)."
            ).format(n=KEY_CORRECTION_MIN_REASON)
        )
    if len(reason) > APPEAL_MAX_COMMENT_LENGTH:
        raise ValidationError(
            pgettext("appeals.service.key_correction.error", "Səbəb {n} simvoldan uzun ola bilməz.").format(
                n=APPEAL_MAX_COMMENT_LENGTH
            )
        )
    return reason


def _question_answers(question):
    """Sualı alan bütün BİTMİŞ, sınaq olmayan cəhdlərin cavabları (tək sorğu + prefetch)."""
    from apps.exams.models import ExamAnswer

    return list(
        ExamAnswer.objects.filter(
            question=question,
            attempt__exam_id=question.exam_id,
            attempt__is_trial=False,
            attempt__status__in=ATTEMPT_FINISHED_STATUSES,
        )
        .select_related("attempt", "attempt__exam", "attempt__user", "question")
        .prefetch_related("selected_options", "question__options")
        .order_by("attempt_id")
    )


def _effective_scores(attempts):
    """``attempt_id`` → effektiv test balı (baza + bütün aktiv kreditlər) — TOPLU (N+1 yox)."""
    from apps.exams.models import ExamAnswer

    if not attempts:
        return {}
    by_attempt = {attempt.id: [] for attempt in attempts}
    answers = (
        ExamAnswer.objects.filter(attempt_id__in=list(by_attempt))
        .select_related("question")
        .prefetch_related("question__options", "selected_options")
        .order_by("id")
    )
    for answer in answers:
        by_attempt[answer.attempt_id].append(answer)
    bonus = appeal_bonus_map(list(by_attempt))
    scores = {}
    for attempt in attempts:
        base = calculate_test_attempt_result(attempt, answers=by_attempt[attempt.id])
        value = base.score + (bonus.get(attempt.id) or Decimal("0"))
        scores[attempt.id] = min(value, base.max_score) if base.max_score else value
    return scores


def _audit(request, reviewer, correction, *, reason, values):
    try:
        from apps.audit.public import log_action
        from core.constants import AuditAction

        with transaction.atomic():  # savepoint — bax decisions._audit_score_change
            log_action(
                action=AuditAction.UPDATE,
                user=reviewer,
                organization=correction.organization,
                obj=correction,
                reason=reason,
                request=request,
                resource_type="appeals.answer_key_correction",
                resource_id=str(correction.pk),
                new_values=values,
            )
    except Exception:
        logger.warning("Answer-key correction audit log failed.", exc_info=True)


def _ledger(attempt, question, *, grader, old, new, max_points):
    from apps.exams.models import ExamGradeEvent

    if old == new:
        return
    ExamGradeEvent.objects.create(
        attempt=attempt, question=question, grader=grader, old_score=old, new_score=new, max_points=max_points
    )


def _after_commit(correction, attempts, *, reviewer, appeal_id, question_no, revoked):
    """Rəsmi qiymət (jurnal) + bildirişlər — YALNIZ tranzaksiya təsdiqindən sonra."""

    def _run():
        from apps.exams.public import sync_attempt_to_journal

        from .notify import notify_key_correction

        for attempt in attempts:
            try:
                sync_attempt_to_journal(attempt, actor=reviewer, appeal_id=appeal_id)
            except Exception:
                logger.warning("Key correction journal sync failed for attempt %s", attempt.pk, exc_info=True)
        notify_key_correction(correction, credited_attempts=attempts, question_no=question_no, revoked=revoked)

    transaction.on_commit(_run)


def _question_number(item):
    return getattr(item.question, "order", None) or item.question_id


@transaction.atomic
def apply_key_correction(item, *, reviewer, corrected_option_ids, reason, request=None):
    """Apellyasiya item-indən açar düzəlişi yarat və bütün uyğun cəhdlərə kredit ver.

    Qaytarır: ``AnswerKeyCorrection`` (``affected_count`` / ``credited_count`` ilə)."""
    from .decisions import _lock_appeal

    _lock_appeal(item.appeal_id)
    item = (
        AppealItem.objects.select_for_update(of=("self",))
        .select_related("appeal", "appeal__attempt", "appeal__exam", "appeal__organization", "question", "answer")
        .get(pk=item.pk)
    )
    exam = item.appeal.exam
    if getattr(exam, "exam_type", None) != "test":
        raise _error("Açar düzəlişi yalnız test (variantlı) suallar üçündür.")
    question = item.question
    # Eyni sual üçün paralel iki düzəlişi ardıcıllaşdır (sual sətri kilidi).
    type(question).objects.select_for_update().filter(pk=question.pk).first()
    if active_correction_for(question.pk) is not None:
        raise _error("Bu sual üçün aktiv açar düzəlişi artıq var — əvvəlcə onu geri alın.")

    reference = item.answer or item.appeal.attempt.answers.filter(question=question).first()
    allowed = [option["id"] for option in key_option_choices(reference, question)]
    corrected = _clean_corrected_ids(corrected_option_ids, allowed)
    reason = _clean_reason(reason)
    previous = sorted(_delivered_correct_ids(reference)) if reference is not None else []
    if set(previous) == corrected:
        raise _error("Yeni açar köhnə açarla eynidir — düzəliş lazım deyil.")

    answers = _question_answers(question)
    eligible = []
    for answer in answers:
        selected = _selected_ids(answer)
        if selected and selected == corrected and selected != _delivered_correct_ids(answer):
            eligible.append(answer)
    attempts = [answer.attempt for answer in eligible]
    before = _effective_scores(attempts)

    correction = AnswerKeyCorrection.objects.create(
        organization=item.appeal.organization,
        exam=exam,
        question=question,
        source_item=item,
        previous_option_ids=previous,
        corrected_option_ids=sorted(corrected),
        reason=reason,
        created_by=reviewer,
        affected_count=len(answers),
        credited_count=len(eligible),
    )
    bonus = _accept_bonus_points()
    credits = []
    for answer in eligible:
        points = Decimal(delivered_question_points(answer, question))
        delta = min(bonus, points)
        credits.append(
            KeyCorrectionCredit(
                correction=correction,
                attempt=answer.attempt,
                question=question,
                delta_points=delta,
                previous_score=before.get(answer.attempt_id),
            )
        )
        _ledger(answer.attempt, question, grader=reviewer, old=0, new=int(delta), max_points=int(points))
    KeyCorrectionCredit.objects.bulk_create(credits)
    after = _effective_scores(attempts)
    for credit in credits:
        credit.new_score = after.get(credit.attempt_id)
    if credits:
        KeyCorrectionCredit.objects.bulk_update(credits, ["new_score"])

    _audit(
        request,
        reviewer,
        correction,
        reason="Answer key corrected for all students",
        values={
            "exam_id": exam.id,
            "question_id": question.id,
            "appeal_item_id": item.id,
            "previous_option_ids": previous,
            "corrected_option_ids": sorted(corrected),
            "affected_count": len(answers),
            "credited_count": len(eligible),
            "reason": reason,
        },
    )
    _after_commit(
        correction,
        attempts,
        reviewer=reviewer,
        appeal_id=item.appeal_id,
        question_no=_question_number(item),
        revoked=False,
    )
    return correction


@transaction.atomic
def revoke_key_correction(correction, *, reviewer, reason, request=None):
    """Səhv açar düzəlişini geri al — kreditlər ``reverted``, sətirlər QALIR (audit)."""
    correction = (
        AnswerKeyCorrection.objects.select_for_update(of=("self",))
        .select_related("exam", "organization", "question", "source_item")
        .get(pk=correction.pk)
    )
    if correction.revoked_at is not None:
        raise _error("Bu açar düzəlişi artıq geri alınıb.")
    reason = _clean_reason(reason)
    credits = list(correction.credits.filter(reverted=False).select_related("attempt", "attempt__user"))
    for credit in credits:
        if credit.delta_points and credit.delta_points > 0:
            answer = credit.attempt.answers.filter(question_id=credit.question_id).first()
            points = delivered_question_points(answer, correction.question)
            _ledger(
                credit.attempt,
                correction.question,
                grader=reviewer,
                old=int(credit.delta_points),
                new=0,
                max_points=int(points),
            )
    KeyCorrectionCredit.objects.filter(pk__in=[credit.pk for credit in credits]).update(reverted=True)
    correction.revoked_at = timezone.now()
    correction.revoked_by = reviewer
    correction.revoke_reason = reason
    correction.save(update_fields=["revoked_at", "revoked_by", "revoke_reason"])
    _audit(
        request,
        reviewer,
        correction,
        reason="Answer key correction revoked",
        values={"reverted_credits": len(credits), "reason": reason},
    )
    attempts = [credit.attempt for credit in credits if credit.delta_points and credit.delta_points > 0]
    question_no = getattr(correction.question, "order", None) or correction.question_id
    appeal_id = correction.source_item.appeal_id if correction.source_item_id else None
    _after_commit(correction, attempts, reviewer=reviewer, appeal_id=appeal_id, question_no=question_no, revoked=True)
    return correction


def ensure_can_correct_key(request, appeal):
    """Açar düzəlişi = qərar səlahiyyəti (``appeal.respond`` + ``appeal.decide``, tenant)."""
    from .permissions import can_decide_appeal, can_respond_appeal

    if not (can_respond_appeal(request, appeal) and can_decide_appeal(request, appeal)):
        raise PermissionDenied(pgettext("appeals.view.message", "Apellyasiya qərarı vermək icazəniz yoxdur."))


__all__ = [
    "KEY_CORRECTION_MIN_REASON",
    "active_correction_for",
    "apply_key_correction",
    "ensure_can_correct_key",
    "key_option_choices",
    "revoke_key_correction",
]
