"""Aktiv açar düzəlişini sonradan bitən cəhdlərə də tətbiq et.

Çatdırılmış sual və seçim snapshot-ları dəyişmir. Sual kilidi ilkin kütləvi
düzəlişlə yarışda cəhdi itirmir; correction kilidi geri alma ilə ardıcıllaşır.
Hook cəhdin bitirmə tranzaksiyasında, jurnal hesablanmazdan əvvəl işləyir.
"""

from decimal import Decimal

from django.apps import apps as django_apps
from django.db import transaction

from apps.audit.public import log_action
from apps.exams.public import ATTEMPT_FINISHED_STATUSES
from core.constants import AuditAction

from ..models import AnswerKeyCorrection, KeyCorrectionCredit
from . import key_corrections as keys
from .scoring import delivered_question_points


@transaction.atomic
def apply_active_key_corrections(attempt):
    """Rəsmi bitmiş test cəhdi üçün yeni kredit sayı; təkrar çağırış təhlükəsizdir."""
    exam = attempt.exam
    if attempt.is_trial or attempt.status not in ATTEMPT_FINISHED_STATUSES or exam.exam_type != "test":
        return 0
    Question = django_apps.get_model("exams", "ExamQuestion")
    # Düzəliş hələ yaranmayıbsa da kilid lazımdır: apply sualı kilidləyib
    # bitmiş cəhdləri seçir. Hər iki sıra eyni cəhdə kredit verilməsini təmin edir.
    question_ids = list(
        # NO KEY UPDATE eyni sualı dəyişən apply ilə ziddir, amma revoke-un
        # ledger FK yoxlamasına KEY SHARE icazə verir (kilid dövrəsi yaranmır).
        Question.objects.select_for_update(of=("self",), no_key=True)
        .filter(exam_id=exam.pk, answers__attempt_id=attempt.pk)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    corrections = list(
        AnswerKeyCorrection.objects.select_for_update(of=("self",))
        .filter(
            exam_id=exam.pk,
            organization_id=exam.organization_id,
            question_id__in=question_ids,
            revoked_at__isnull=True,
        )
        .select_related("question", "source_item", "created_by", "organization")
        .order_by("question_id")
    )
    if not corrections:
        return 0
    answers = {
        answer.question_id: answer
        for answer in attempt.answers.filter(question_id__in=[c.question_id for c in corrections])
        .select_related("question")
        .prefetch_related("selected_options", "question__options")
    }
    created = 0
    for correction in corrections:
        answer = answers.get(correction.question_id)
        if answer is not None:
            created += _apply_one(correction, attempt, answer)
    return created


def _apply_one(correction, attempt, answer):
    selected = keys._selected_ids(answer)
    eligible = (
        selected
        and selected == set(correction.corrected_option_ids)
        and selected != keys._delivered_correct_ids(answer)
    )
    credit = None
    if eligible and not correction.credits.filter(attempt_id=attempt.pk).exists():
        before = keys._effective_scores([attempt])[attempt.pk]
        points = Decimal(delivered_question_points(answer, correction.question))
        credit = KeyCorrectionCredit.objects.create(
            correction=correction,
            attempt=attempt,
            question=correction.question,
            delta_points=points,
            previous_score=before,
        )
        keys._ledger(
            attempt, correction.question, grader=correction.created_by, old=0, new=int(points), max_points=int(points)
        )
        credit.new_score = keys._effective_scores([attempt])[attempt.pk]
        credit.save(update_fields=["new_score"])
        # Kredit + qiymət ledgeri + audit + cəhdin bitməsi birlikdə commit olur.
        log_action(
            action=AuditAction.UPDATE,
            user=correction.created_by,
            organization=correction.organization,
            obj=correction,
            reason="Active answer key correction applied on attempt completion",
            resource_type="appeals.answer_key_correction",
            resource_id=str(correction.pk),
            new_values={
                "attempt_id": attempt.pk,
                "credit_id": credit.pk,
                "previous_score": str(before),
                "new_score": str(credit.new_score),
            },
        )
    # Sayğaclar cari bitmiş cəhdləri əhatə edir; təkrar hook onları artırmır.
    correction.affected_count = answer.__class__.objects.filter(
        question_id=correction.question_id,
        attempt__exam_id=correction.exam_id,
        attempt__is_trial=False,
        attempt__status__in=ATTEMPT_FINISHED_STATUSES,
    ).count()
    correction.credited_count = correction.credits.count()
    correction.save(update_fields=["affected_count", "credited_count"])
    if credit is None:
        return 0
    keys._after_commit(
        correction,
        [attempt],
        reviewer=correction.created_by,
        appeal_id=correction.source_item.appeal_id if correction.source_item_id else None,
        question_no=correction.question.order or correction.question_id,
        revoked=False,
    )
    return 1
