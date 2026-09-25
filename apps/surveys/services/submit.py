"""Cavabın göndərilməsi — qəbz + anonim cavab EYNİ tranzaksiyada, ortaq açarsız.

Təkrar göndərişə qarşı qoruma DB səviyyəsindədir: qəbzin şərtli unikal
məhdudiyyəti (``surveys_receipt_teacher_once`` / ``surveys_receipt_general_once``).
Qəbz cavabdan ƏVVƏL, ayrıca savepoint-də yazılır: paralel ikinci POST unikal
indeksdə gözləyib ``IntegrityError`` alır və bütün blok geri çəkilir — ikinci
anonim cavab heç vaxt yaranmır. Kampaniya sətri kilidlənmir (bütün tələbələrin
göndərişini seriyalaşdırardı).

Heç bir audit/log yazılmır: «kim, nə vaxt, hansı müəllimə nə yazdı» izi
anonimliyi pozardı. Qəbzin özü («kim doldurdu») kifayətdir.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import pgettext

from .. import registrar_bridge as bridge
from ..models import SurveyAnswer, SurveyReceipt, SurveyResponse

_CTX = "surveys.submit"


class AlreadySubmitted(ValidationError):
    """Bu hədəf artıq doldurulub (təkrar göndəriş)."""


class SubmissionClosed(ValidationError):
    """Kampaniya aktiv deyil və ya hədəf artıq uyğun deyil."""


def submit_target(*, campaign, student, target, cleaned_answers) -> None:
    """Hədəfin cavabını yazır. ``cleaned_answers`` — ``forms.validate_answers`` çıxışı."""
    today = timezone.localdate()
    if not campaign.is_active_on(today):
        raise SubmissionClosed(pgettext(_CTX, "Sorğu artıq qəbul edilmir."))
    organization = campaign.organization_id
    if target.is_general:
        snapshot = bridge.student_snapshot(organization, student)
        department_id = None
    else:
        snapshot = bridge.offering_snapshot(organization, target.offering_id, target.teacher_id)
        department_id = snapshot.get("teacher_department_id")
    with transaction.atomic():
        try:
            with transaction.atomic():
                SurveyReceipt.objects.create(
                    organization_id=organization,
                    campaign=campaign,
                    student=student,
                    scope=target.scope,
                    offering_id=None if target.is_general else target.offering_id,
                    teacher_id=None if target.is_general else target.teacher_id,
                    teacher_department_id=department_id,
                    completed_on=today,
                )
        except IntegrityError as exc:
            raise AlreadySubmitted(pgettext(_CTX, "Bu sorğunu artıq doldurmusunuz.")) from exc
        response = SurveyResponse.objects.create(
            organization_id=organization,
            campaign=campaign,
            scope=target.scope,
            offering_id=None if target.is_general else target.offering_id,
            teacher_id=None if target.is_general else target.teacher_id,
            subject_id=snapshot.get("subject_id"),
            group_id=snapshot.get("group_id"),
            teacher_department_id=department_id,
            faculty_id=snapshot.get("faculty_id"),
            program_id=snapshot.get("program_id"),
            course_year=snapshot.get("course_year"),
        )
        SurveyAnswer.objects.bulk_create(
            [
                SurveyAnswer(
                    organization_id=organization,
                    response=response,
                    question=question,
                    score=score,
                    text=text,
                )
                for question, score, text in cleaned_answers
            ]
        )


__all__ = ["AlreadySubmitted", "SubmissionClosed", "submit_target"]
