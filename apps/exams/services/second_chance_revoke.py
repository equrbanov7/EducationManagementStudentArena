"""İmtahan mərkəzi — «yenidən imtahan cəhdi»nin GERİ ALINMASI (``grant_second_chance``-ın tərsi), 2026-10-19.

25% müraciəti imtahan cəhdi açıldıqdan SONRA qərarla bağlananda («İmtahana gəlmədi», rədd, geri götürmə)
tələbənin əlavə cəhdi və fərdi PIN-i açıq qalmamalıdır — əks halda bağlanmış müraciətin cəhdi yenə verilə bilər
və balı yanlış yerə düşər (review 2026-10-19, HIGH-1). Bu servis:

1. Tələbənin həmin imtahanda DAVAM EDƏN (``draft`` / ``in_progress``) və ya təqdim olunmuş, amma hələ
   YOXLANMAMIŞ (yazılı / praktiki, ``teacher_score`` boş) cəhdi varsa geri almır — ``RevokeBlocked``.
2. ``StudentExamAttemptGrant.extra_attempts``-dan verilmiş, amma hələ İSTİFADƏ OLUNMAMIŞ cəhdləri çıxır
   (artıq istifadə olunmuş cəhd tarixçədən silinmir).
3. Qalan cəhd sayı 0-a düşürsə (və ya limit yoxdursa) fərdi PIN-i ləğv edir — ``revoke_student_pin``.
4. Audit jurnalına yazır.

Registrar bunu app registry üzərindən (``ExamsConfig.second_chance_provider``) çağırır — registrar → exams
STATİK importu yoxdur (``scripts/module_deps.py``).
"""

from __future__ import annotations

from django.db import transaction
from django.utils.translation import pgettext

from apps.exams.models import Exam, ExamAttempt, StudentExamAttemptGrant
from apps.exams.services.student_pins import exam_requires_student_pins, revoke_student_pin
from core.audit import log_action
from core.constants import AuditAction

_OPEN_STATUSES = ("draft", "in_progress")
_GRADED_EXAM_TYPES = ("test",)


class RevokeBlocked(ValueError):
    """Cəhd geri alına bilməz — tələbənin davam edən və ya yoxlanmamış cəhdi var (lokalizə olunmuş mətn)."""


def blocking_attempt(*, exam_id, student):
    """Geri almağı bloklayan cəhd (davam edən və ya yoxlanmamış) və ya ``None``."""
    attempts = ExamAttempt.objects.filter(exam_id=exam_id, user=student, is_trial=False).select_related("exam")
    open_attempt = attempts.filter(status__in=_OPEN_STATUSES).order_by("-started_at").first()
    if open_attempt is not None:
        return open_attempt
    return (
        attempts.filter(status="submitted", teacher_score__isnull=True)
        .exclude(exam__exam_type__in=_GRADED_EXAM_TYPES)
        .order_by("-started_at")
        .first()
    )


@transaction.atomic
def revoke_second_chance(*, exam_id, student, extra=1, revoked_by=None, request=None, reason="") -> dict:
    """Verilmiş əlavə cəhd(lər)i və fərdi PIN-i geri al. Xülasə: ``{"revoked", "pin_revoked", "exam_found"}``."""
    exam = Exam.objects.filter(pk=exam_id).first()
    if exam is None:
        return {"revoked": 0, "pin_revoked": False, "exam_found": False}
    grant = StudentExamAttemptGrant.objects.select_for_update().filter(exam=exam, student=student).first()
    blocker = blocking_attempt(exam_id=exam.pk, student=student)
    if blocker is not None:
        if blocker.status in _OPEN_STATUSES:
            message = pgettext(
                "exams.second_chance.error",
                "Tələbə «{exam}» imtahanında hazırda cəhd edir — cəhd bitməmiş müraciət bağlanmır.",
            )
        else:
            message = pgettext(
                "exams.second_chance.error",
                "Tələbənin «{exam}» imtahanındakı cəhdi hələ yoxlanmayıb — əvvəlcə yoxlanmalıdır.",
            )
        raise RevokeBlocked(message.format(exam=exam.title))
    try:
        wanted = max(0, int(extra))
    except (TypeError, ValueError):
        wanted = 1
    left = exam.attempts_left_for(student)
    available = grant.extra_attempts if grant is not None else 0
    removable = min(wanted, available, left) if left is not None else min(wanted, available)
    if removable > 0:
        grant.extra_attempts = available - removable
        grant.granted_by = revoked_by if revoked_by is not None else grant.granted_by
        grant.save(update_fields=["extra_attempts", "granted_by", "updated_at"])
    left_after = exam.attempts_left_for(student, stale_attempts_expired=True)
    pin_revoked = False
    if exam_requires_student_pins(exam) and (left_after is None or left_after <= 0):
        pin_revoked = revoke_student_pin(exam, student)
    log_action(
        AuditAction.UPDATE,
        user=revoked_by,
        organization=exam.organization,
        obj=exam,
        reason="exam_second_chance_revoked",
        request=request,
        resource_type="exam",
        resource_id=str(exam.pk),
        new_values={
            "student_id": getattr(student, "pk", None),
            "requested": wanted,
            "revoked": removable,
            "attempts_left": left_after,
            "pin_revoked": pin_revoked,
            "reason": str(reason or "")[:200],
        },
    )
    return {"revoked": removable, "pin_revoked": pin_revoked, "exam_found": True}


__all__ = ["RevokeBlocked", "blocking_attempt", "revoke_second_chance"]
