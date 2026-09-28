"""
Apellyasiya qərar əməliyyatları (accept / reject / revert / recompute).

Bu modul apellyasiya item-lərinə edilən **mutasiyaları** saxlayır: qəbul/rədd,
idempotent bal düzəlişi (``ScoreAdjustment``), başlıq statusunun yenidən
hesablanması, audit qeydi və tələbə bildirişi. Bal **oxuma/hesablama** məntiqi
(effektiv bal, bonus xəritələri) ayrıca ``scoring`` modulundadır — bu modul
oradan yalnız köməkçi hesablama funksiyalarını istifadə edir (tək istiqamətli
asılılıq: decisions → scoring).

İdempotentlik və additiv-delta dizaynı üçün bax: ``scoring`` modul docstring-i.
"""

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
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
from apps.appeals.models import Appeal, AppealItem, ScoreAdjustment

from .scoring import _accept_bonus_points, _question_already_correct, delivered_question_points, effective_test_score
from .state_machine import assert_transition, can_transition

logger = logging.getLogger(__name__)


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

        # SAVEPOINT: audit yazısı düşərsə yalnız ÖZÜ geri qayıtsın. Savepoint
        # olmadan udulmuş DB xətası PostgreSQL-də bütün qərar tranzaksiyasını
        # səssizcə zəhərləyir (bax: JSONField lazy-proxy tx zəhəri dərsi).
        with transaction.atomic():
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


def _audit_score_revert(request, reviewer, adjustment):
    """Bal düzəlişinin GERİ ALINMASI audit izi (2026-08 auditi, G10).

    Əvvəl ``revert_item_adjustment`` tamamilə auditsiz idi: tələbənin balı
    geri götürülürdü, amma «kim, nə vaxt, nədən nəyə» izi qalmırdı."""
    try:
        from apps.audit.public import log_action
        from core.constants import AuditAction

        with transaction.atomic():  # savepoint — bax _audit_score_change
            log_action(
                action=AuditAction.UPDATE,
                user=reviewer,
                organization=getattr(adjustment.appeal_item.appeal, "organization", None),
                obj=adjustment,
                reason="Appeal score adjustment reverted",
                request=request,
                resource_type="appeals.score_adjustment.revert",
                resource_id=str(adjustment.pk),
                old_values={"delta_points": str(adjustment.delta_points)},
                new_values={
                    "attempt_id": adjustment.attempt_id,
                    "appeal_item_id": adjustment.appeal_item_id,
                    "delta_points": "0",
                    "restored_answer_score": str(adjustment.previous_answer_score),
                },
            )
    except Exception:
        logger.warning("Appeal score-revert audit log failed.", exc_info=True)


def _question_credit(*, is_correct, question_points):
    """Sualın tələbəyə verdiyi kredit (ledger sətri üçün TAM ədəd)."""
    return int(question_points) if is_correct else 0


def _write_grade_event(attempt, *, question, grader, old_score, new_score, max_points):
    """İmtahan ledger-inə (``ExamGradeEvent``) əlavə-yalnız sətir yaz.

    Apellyasiya qərarı da ƏL İLƏ bal dəyişikliyidir — manual grading ilə eyni
    tamper-evidence izinə düşməlidir (2026-08 auditi, G10). Bal dəyişmirsə
    sətir yazılmır (səs-küy azaldılır).

    FAIL-CLOSED (manual grading ilə eyni siyasət): ledger yazıla bilmirsə bal
    dəyişikliyi də qalmır — qərar bütün tranzaksiya ilə geri qayıdır."""
    if old_score == new_score:
        return None
    from apps.exams.models import ExamGradeEvent

    return ExamGradeEvent.objects.create(
        attempt=attempt,
        question=question,
        grader=grader,
        old_score=old_score,
        new_score=new_score,
        max_points=max_points,
    )


def _lock_appeal(appeal_id):
    """Apellyasiya başlığını ``FOR UPDATE`` ilə kilidlə (Audit 2026-09-28 EXA-06).

    Kilid sırası HƏMİŞƏ ``Appeal`` → ``AppealItem``-dir: eyni apellyasiyaya
    paralel baxan iki reviewer ardıcıllaşır və başlıq statusu son (commit
    olunmuş) item statuslarından hesablanır — əks halda başlıq ``under_review``-da
    ilişib qalır, tələbə bildirişi də getmirdi."""
    return Appeal.objects.select_for_update(of=("self",)).get(pk=appeal_id)


def _ensure_attempt_graded(attempt, exam):
    """Yazılı/praktiki cəhd yoxlanmayıbsa qərar verilmir (Audit 2026-09-28 EXA-02).

    Yoxlanmamış cəhddə ``answer.teacher_score`` boşdur — qəbul +1-i «0 + 1» kimi
    yazır, ``attempt.teacher_score`` 1 olur və jurnala yarımçıq (F) nəticə
    düşürdü. Yaratma qapısı (``window.appeal_window_start``) yeni belə müraciəti
    bağlayır; bu yoxlama köhnə (qapıdan əvvəl yaranmış) müraciətlər üçündür."""
    if getattr(exam, "exam_type", None) == "test":
        return
    if not getattr(attempt, "checked_by_teacher", False):
        raise ValidationError(
            pgettext(
                "appeals.service.decision.error",
                "İmtahan hələ yoxlanılmayıb — apellyasiyaya yoxlamadan sonra qərar verilə bilər.",
            )
        )


def _schedule_journal_sync(attempt, *, actor):
    """Qərardan sonra rəsmi qiyməti (elektron jurnal) yenilə.

    ``apps.exams.public`` fasadı üzərindən — appeals→exams istiqaməti legitim,
    əks istiqamət (exams→appeals) ``score_adjustments`` hook-larıyla qalır."""
    try:
        from apps.exams.public import schedule_journal_sync

        schedule_journal_sync(attempt, actor=actor)
    except Exception:
        logger.warning("Appeal journal sync scheduling failed.", exc_info=True)


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
    _lock_appeal(item.appeal_id)
    item = (
        AppealItem.objects.select_for_update(of=("self",))
        .select_related("appeal", "appeal__attempt", "appeal__attempt__exam", "question")
        .get(pk=item.pk)
    )
    appeal = item.appeal
    attempt = appeal.attempt
    exam = attempt.exam
    _ensure_attempt_graded(attempt, exam)
    question = item.question
    answer = item.answer or attempt.answers.filter(question=question).first()

    existing = ScoreAdjustment.objects.filter(appeal_item=item).first()
    if existing and not existing.reverted:
        # Artıq tətbiq olunub — ikiqat artımın qarşısını alırıq (bal dəyişmir,
        # ona görə nə yeni ledger sətri, nə də yeni jurnal yazısı lazımdır).
        _mark_item_resolved(item, APPEAL_ITEM_STATUS_ACCEPTED, reviewer, response_text)
        recompute_appeal_status(appeal, reviewer=reviewer)
        return existing

    delta = Decimal("0")
    prev_is_correct = None
    new_is_correct = None
    previous_score = None
    new_score = None
    previous_answer_score = None
    # Audit 2026-09-28 EXA-08: tavan ÇATDIRILAN snapshot-dan (canlı sual balı yox).
    question_points = Decimal(delivered_question_points(answer, question))
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
        # Ledger: sualın tələbəyə verdiyi kredit 0 → +delta (bax _write_grade_event).
        event_old = _question_credit(is_correct=prev_is_correct, question_points=question_points)
        _write_grade_event(
            attempt,
            question=question,
            grader=reviewer,
            old_score=event_old,
            new_score=event_old + int(delta),
            max_points=int(question_points),
        )
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
            _write_grade_event(
                attempt,
                question=question,
                grader=reviewer,
                old_score=None if previous_answer_score is None else int(previous_answer_score),
                new_score=answer.teacher_score,
                max_points=int(question_points),
            )
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
    # 2026-08 auditi (G10): qərar RƏSMİ qiymətə (elektron jurnal) də çatmalıdır —
    # əvvəl bal yalnız ScoreAdjustment-da qalırdı. Aktor = reviewer.
    _schedule_journal_sync(attempt, actor=reviewer)
    recompute_appeal_status(appeal, reviewer=reviewer)
    return adjustment


@transaction.atomic
def reject_appeal_item(item, *, reviewer, response_text="", request=None):
    """
    Bir AppealItem-i rədd edir. Əvvəl qəbul olunub bal verilibsə, həmin düzəliş
    revert olunur (bal geri alınır). Bal dəyişmir (rədd halında).
    """
    _lock_appeal(item.appeal_id)
    item = AppealItem.objects.select_for_update(of=("self",)).select_related("appeal").get(pk=item.pk)
    revert_item_adjustment(item, reviewer=reviewer, request=request)
    _mark_item_resolved(item, APPEAL_ITEM_STATUS_REJECTED, reviewer, response_text)
    recompute_appeal_status(item.appeal, reviewer=reviewer)
    return item


def revert_item_adjustment(item, *, reviewer=None, request=None):
    """
    Item üzrə aktiv bal düzəlişini revert edir.

    - Test: düzəliş `reverted=True` olur → effektiv bonusdan çıxır.
    - Yazılı/praktiki: cavabın əvvəlki balı (`previous_answer_score`) bərpa edilir
      və `attempt.teacher_score` cavablardan yenidən hesablanır.

    2026-08 auditi (G10): geri alma da ledger + audit izi qoyur və rəsmi
    qiyməti (elektron jurnal) yenidən hesablatdırır — əvvəl bunların heç biri
    yox idi (bal səssizcə geri götürülürdü).
    """
    adjustment = ScoreAdjustment.objects.filter(appeal_item=item, reverted=False).first()
    if adjustment is None:
        return None

    attempt = adjustment.attempt
    exam = attempt.exam
    answer = None
    if adjustment.question_id:
        answer = item.answer or attempt.answers.filter(question_id=adjustment.question_id).first()
    # Audit 2026-09-28 EXA-08: ledger tavanı ÇATDIRILAN snapshot-dan.
    question_points = delivered_question_points(answer, adjustment.question) if adjustment.question_id else 1
    delta = int(adjustment.delta_points or 0)

    if getattr(exam, "exam_type", None) != "test" and adjustment.question_id:
        from apps.exams.public import calculate_attempt_score

        if answer is not None:
            restore = adjustment.previous_answer_score
            previous_answer_total = answer.teacher_score
            answer.teacher_score = int(restore) if restore is not None else None
            answer.save(update_fields=["teacher_score", "updated_at"])
            _write_grade_event(
                attempt,
                question=adjustment.question,
                grader=reviewer,
                old_score=previous_answer_total,
                new_score=answer.teacher_score,
                max_points=question_points,
            )
            new_total = calculate_attempt_score(attempt)
            any_score = attempt.answers.filter(teacher_score__isnull=False).exists()
            attempt.teacher_score = int(new_total) if any_score else None
            attempt.save(update_fields=["teacher_score"])
    elif getattr(exam, "exam_type", None) == "test" and adjustment.question_id:
        credit = _question_credit(is_correct=bool(adjustment.previous_is_correct), question_points=question_points)
        _write_grade_event(
            attempt,
            question=adjustment.question,
            grader=reviewer,
            old_score=credit + delta,
            new_score=credit,
            max_points=question_points,
        )

    adjustment.reverted = True
    adjustment.save(update_fields=["reverted"])
    _audit_score_revert(request, reviewer, adjustment)
    _schedule_journal_sync(attempt, actor=reviewer)
    return adjustment


def recompute_appeal_status(appeal, *, reviewer=None):
    """
    Başlıq statusunu item statuslarından törədir:
    - hamısı accepted → accepted
    - hamısı rejected → rejected
    - qarışıq (accepted + rejected, pending yox) → partially_accepted
    - hələ pending varsa → under_review (qərar başlayıbsa) / pending
    Hamısı həll olunduqda reviewed_at/reviewed_by qeyd olunur.

    Audit 2026-09-28 EXA-06: başlıq sətri ``FOR UPDATE`` ilə kilidlənir (item
    statusları kilid ALTINDA oxunur) və keçid ``state_machine`` ilə yoxlanır.
    Çağıran ``appeal`` obyekti də yeni vəziyyətlə sinxronlaşdırılır.
    """
    if not transaction.get_connection().in_atomic_block:
        with transaction.atomic():
            return recompute_appeal_status(appeal, reviewer=reviewer)
    locked = _lock_appeal(appeal.pk)
    statuses = list(AppealItem.objects.filter(appeal_id=locked.pk).values_list("status", flat=True))
    if not statuses:
        return appeal

    has_pending = any(s == APPEAL_ITEM_STATUS_PENDING for s in statuses)
    has_accepted = any(s == APPEAL_ITEM_STATUS_ACCEPTED for s in statuses)
    has_rejected = any(s == APPEAL_ITEM_STATUS_REJECTED for s in statuses)

    previous_status = locked.status
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

    _assert_derived_transition(previous_status, new_status)
    locked.status = new_status
    if fully_resolved:
        locked.reviewed_at = timezone.now()
        update_fields.append("reviewed_at")
        if reviewer is not None:
            locked.reviewed_by = reviewer
            update_fields.append("reviewed_by")
    locked.save(update_fields=update_fields)
    for field in ("status", "reviewed_at", "reviewed_by_id", "updated_at"):
        setattr(appeal, field, getattr(locked, field))

    # Tələbəyə bildiriş — yalnız status İLK DƏFƏ final vəziyyətə keçəndə
    # (pending/under_review → accepted/rejected/partially_accepted). Müəllim
    # 5 dəqiqəlik pəncərədə qərarı redaktə edəndə dublikat bildiriş yaranmır.
    final_statuses = {APPEAL_STATUS_ACCEPTED, APPEAL_STATUS_REJECTED, APPEAL_STATUS_PARTIALLY_ACCEPTED}
    if fully_resolved and previous_status not in final_statuses:
        _notify_student_appeal_resolved(locked)
    return appeal


def _assert_derived_transition(previous_status, new_status):
    """Törəmə başlıq statusunu ``APPEAL_STATUS_TRANSITIONS`` ilə yoxla (EXA-06).

    Başlıq item-lərdən törədildiyi üçün bir sorğuda ``pending → accepted`` və ya
    (5 dəqiqəlik redaktədə) ``accepted → partially_accepted`` kimi sıçrayış
    olur — bu, aradakı gizli ``under_review`` addımı ilə icazəlidir. Cədvəldə
    heç bir yolu olmayan keçid (məs. yekun → ``pending``) ``InvalidAppealTransition``
    qaldırır və qərar tranzaksiyası geri qayıdır."""
    if can_transition(previous_status, new_status):
        return
    if can_transition(previous_status, APPEAL_STATUS_UNDER_REVIEW):
        assert_transition(APPEAL_STATUS_UNDER_REVIEW, new_status)
        return
    assert_transition(previous_status, new_status)


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
    "recompute_appeal_status",
    "reject_appeal_item",
    "revert_item_adjustment",
]
