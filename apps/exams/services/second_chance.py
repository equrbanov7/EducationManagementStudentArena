"""İmtahan mərkəzi — «imtahan şansı ver» (ikinci şans) servisi.

Seçilmiş tələbə(lər)ə və ya bütöv qrupa konkret final/midterm (və ya adi)
imtahan üzrə yenidən cəhd hüququ verir. Bir çağırışda ÜÇ iş görülür ki,
tələbə həqiqətən yenidən girə bilsin:

1. ``StudentExamAttemptGrant`` upsert — cəhd limiti artır
   (``Exam.attempts_left_for`` və tələbə siyahıları grant-ı nəzərə alır,
   ona görə imtahan «təyin olunmuş tapşırıqlar»da YENİDƏN görünür).
2. Final/midterm üçün TƏZƏ fərdi PIN (köhnəsi imtahan başlayanda birdəfəlik
   ləğv olunub) — ``reissue_student_pin``.
3. Final üçün köhnə giriş biletinin sıfırlanması: ``completed/removed/absent``
   bilet ``/exams/final/`` girişini bloklayır (``ensure_pin_ticket``) — bilet
   təzə oturuş üçün ilkin vəziyyətə qaytarılır (sətir silinmir ki, unikallıq
   və tarixçə qorunur; cəhd qeydləri ``ExamAttempt``-də onsuz da qalır).

Hər qərar audit jurnalına yazılır (kim, hansı imtahan, neçə tələbə, +neçə cəhd).
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils.translation import pgettext

from apps.exams.domain.final_center import (
    TICKET_STATUS_ASSIGNED,
    FinalExamTicket,
)
from apps.exams.models import StudentExamAttemptGrant
from apps.exams.services.student_pins import exam_requires_student_pins, reissue_student_pin
from core.audit import log_action
from core.constants import AuditAction

logger = logging.getLogger(__name__)

MAX_EXTRA_ATTEMPTS = 10


class SecondChanceError(ValueError):
    """İstifadəçiyə göstərilə bilən (lokalizə olunmuş) ikinci-şans xətası."""


def _reset_final_ticket(exam, student) -> bool:
    """Finalın köhnə biletini təzə oturuş üçün ilkin vəziyyətə qaytarır."""
    ticket = FinalExamTicket.objects.filter(exam=exam, student=student).first()
    if ticket is None:
        return False
    ticket.status = TICKET_STATUS_ASSIGNED
    ticket.session = None
    ticket.attempt = None
    ticket.seat_number = None
    # Bilet PIN sahələri legacy-dir (giriş ExamStudentPin ilədir) — təmizlə.
    ticket.pin_hash = ""
    ticket.pin_cipher = ""
    ticket.pin_issued_at = None
    ticket.pin_expires_at = None
    ticket.pin_revoked_at = None
    ticket.pin_failed_attempts = 0
    ticket.pin_locked_until = None
    # Həyat dövrü + çıxarılma sahələri sıfırlanır (yeni oturuş təmiz başlasın).
    ticket.entry_validated_at = None
    ticket.rules_accepted_at = None
    ticket.waiting_since = None
    ticket.ready_at = None
    ticket.started_at = None
    ticket.completed_at = None
    ticket.removed_at = None
    ticket.removed_by = None
    ticket.removal_action = ""
    ticket.removal_reason = ""
    ticket.reconnect_count = 0
    ticket.save()
    return True


def _upsert_grant(exam, student, extra, granted_by):
    """Tələbə üçün grant yarat/artır (müəllim endpoint-i ilə eyni semantika)."""
    grant, created = StudentExamAttemptGrant.objects.get_or_create(
        exam=exam,
        student=student,
        defaults={"extra_attempts": extra, "granted_by": granted_by},
    )
    if not created:
        grant.extra_attempts = grant.extra_attempts + extra
        grant.granted_by = granted_by
        grant.save(update_fields=["extra_attempts", "granted_by", "updated_at"])
    return grant


def _notify_students(exam, students):
    """Tələbələrə PIN-siz bildiriş — yeni PIN kabinetdə onsuz da görünür."""
    try:
        from apps.notifications.public import create_notification_for_users

        create_notification_for_users(
            recipients=list(students),
            title=pgettext("exams.second_chance.notification", "İmtahan üçün yenidən şans verildi"),
            message=pgettext(
                "exams.second_chance.notification",
                "«{exam}» imtahanı üzrə sizə yenidən cəhd hüququ verildi. "
                "Yeni giriş PIN-iniz kabinetinizdəki tapşırıq kartında görünür.",
            ).format(exam=exam.title),
            link="/accounts/profile/?section=assigned-exams",
            notification_type="exam",
            organization=exam.organization,
        )
    except Exception:  # noqa: BLE001 — bildiriş xətası şans verməni bloklamır
        logger.warning("second_chance: bildiriş göndərilmədi", exc_info=True)


@transaction.atomic
def grant_second_chance(*, exam, students, extra=1, granted_by=None, request=None) -> dict:
    """Tələbələrə imtahan üzrə ikinci şans verir; xülasə sayları qaytarır."""
    students = [s for s in students if getattr(s, "pk", None)]
    if not students:
        raise SecondChanceError(pgettext("exams.second_chance.error", "Ən azı bir tələbə seçilməlidir."))
    try:
        extra = int(extra)
    except (TypeError, ValueError):
        extra = 1
    extra = max(1, min(extra, MAX_EXTRA_ATTEMPTS))

    pins_reissued = 0
    tickets_reset = 0
    for student in students:
        _upsert_grant(exam, student, extra, granted_by)
        if exam_requires_student_pins(exam):
            if reissue_student_pin(exam, student):
                pins_reissued += 1
        if exam.exam_type_extended == "final":
            if _reset_final_ticket(exam, student):
                tickets_reset += 1

    log_action(
        AuditAction.UPDATE,
        user=granted_by,
        organization=exam.organization,
        obj=exam,
        reason="exam_second_chance_granted",
        request=request,
        resource_type="exam",
        resource_id=str(exam.pk),
        new_values={
            "student_ids": [s.pk for s in students],
            "student_count": len(students),
            "extra_attempts": extra,
            "pins_reissued": pins_reissued,
            "tickets_reset": tickets_reset,
            "exam_category": exam.exam_type_extended or "",
        },
    )
    _notify_students(exam, students)

    return {
        "students": len(students),
        "extra": extra,
        "pins_reissued": pins_reissued,
        "tickets_reset": tickets_reset,
    }


__all__ = ["MAX_EXTRA_ATTEMPTS", "SecondChanceError", "grant_second_chance"]
