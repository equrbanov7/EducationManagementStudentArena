"""
Apellyasiya yaratma servisi.

Student bir attempt üzrə bir və ya bir neçə sualı apellyasiya edir. Hər sualın
öz tipi və şərhi olur (min ``APPEAL_MIN_COMMENT_LENGTH`` simvol). Yalnız həmin
attempt-ə təqdim olunmuş (delivered) suallar apellyasiya edilə bilər.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import pgettext

from apps.appeals.constants import (
    APPEAL_MIN_COMMENT_LENGTH,
    APPEAL_STATUS_PENDING,
    APPEAL_TYPE_VALUES,
)
from apps.appeals.models import Appeal, AppealItem


def _clean_items(attempt, items):
    """
    items: [{"question_id": int, "appeal_type": str, "comment": str}, ...]
    Qaytarır: təmizlənmiş item siyahısı (answer obyekti də əlavə edilmiş).
    """
    if not items:
        raise ValidationError(pgettext("appeals.service.create.error", "no_items"))

    # Bu attempt-ə təqdim olunmuş sualların id → answer xəritəsi.
    delivered = {answer.question_id: answer for answer in attempt.answers.select_related("question").all()}

    cleaned = []
    seen_question_ids = set()
    for raw in items:
        try:
            question_id = int(raw.get("question_id"))
        except (TypeError, ValueError):
            raise ValidationError(pgettext("appeals.service.create.error", "invalid_question"))

        if question_id not in delivered:
            # Student yalnız ona təqdim olunmuş sualı apellyasiya edə bilər.
            raise ValidationError(pgettext("appeals.service.create.error", "question_not_in_attempt"))

        if question_id in seen_question_ids:
            raise ValidationError(pgettext("appeals.service.create.error", "duplicate_question"))
        seen_question_ids.add(question_id)

        appeal_type = (raw.get("appeal_type") or "").strip()
        if appeal_type not in APPEAL_TYPE_VALUES:
            raise ValidationError(pgettext("appeals.service.create.error", "invalid_appeal_type"))

        comment = (raw.get("comment") or "").strip()
        if len(comment) < APPEAL_MIN_COMMENT_LENGTH:
            raise ValidationError(
                pgettext("appeals.service.create.error", "comment_too_short").format(
                    min_length=APPEAL_MIN_COMMENT_LENGTH
                )
            )

        cleaned.append(
            {
                "question_id": question_id,
                "answer": delivered[question_id],
                "appeal_type": appeal_type,
                "comment": comment,
            }
        )

    return cleaned


@transaction.atomic
def create_appeal(*, attempt, student, items, org_unit=None):
    """
    Bir attempt üzrə apellyasiya başlığı + item-lər yaradır.

    Qeyd: pəncərə (3 gün) və icazə yoxlaması çağıran view/servis tərəfindən
    (``services.permissions.can_create_appeal``) edilməlidir. Burada məzmun
    validasiyası aparılır.
    """
    cleaned = _clean_items(attempt, items)

    exam = attempt.exam
    appeal = Appeal.objects.create(
        attempt=attempt,
        exam=exam,
        student=student,
        organization=exam.organization,
        org_unit=org_unit,
        status=APPEAL_STATUS_PENDING,
    )

    AppealItem.objects.bulk_create(
        [
            AppealItem(
                appeal=appeal,
                question_id=item["question_id"],
                answer=item["answer"],
                appeal_type=item["appeal_type"],
                comment=item["comment"],
            )
            for item in cleaned
        ]
    )
    _notify_teacher_new_appeal(appeal, item_count=len(cleaned))
    return appeal


def _notify_teacher_new_appeal(appeal, *, item_count):
    """İmtahan müəllifinə yeni apellyasiya barədə in-app bildiriş. Xəta flow-u pozmur."""
    try:
        from django.urls import reverse

        from apps.notifications.public import create_notification

        teacher = appeal.exam.author
        if teacher is None or teacher.pk == appeal.student_id:
            return
        student_display = appeal.student.get_full_name() or appeal.student.username
        create_notification(
            recipient=teacher,
            title=pgettext("appeals.notification", "Yeni apellyasiya"),
            message=pgettext(
                "appeals.notification",
                '{student} "{exam}" imtahanı üzrə {count} sual üçün apellyasiya göndərdi.',
            ).format(student=student_display, exam=appeal.exam.title, count=item_count),
            link=reverse("appeals:review_appeal", kwargs={"appeal_id": appeal.id}),
            notification_type="exam",
            metadata={"appeal_id": appeal.id, "attempt_id": appeal.attempt_id, "exam_id": appeal.exam_id},
            organization=appeal.organization,
        )
    except Exception:
        import logging

        logging.getLogger(__name__).warning("New appeal notification failed.", exc_info=True)


__all__ = ["create_appeal"]
