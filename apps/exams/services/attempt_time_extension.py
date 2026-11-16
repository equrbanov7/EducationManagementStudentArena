"""Canlı imtahanda BİR tələbəyə əlavə vaxt (sahib 2026-11-17).

Sahib: «imtahan gedərkən monitorda tələbənin üzərinə klik edib ona əlavə N dəqiqə vermək olsun (məs. texniki
problemə görə vaxt itirib) — yalnız onun vaxtı uzansın, başqasına toxunulmasın; bunu edərkən heç nə pozulmasın».

Necə işləyir:

* Vaxt ``ExamAttempt.extra_time_seconds``-a əlavə olunur; deadline-ın TƏK mənbəyi
  ``domain.attempt_deadline.attempt_deadline_at`` onu nəzərə alır — taymer, lazy bağlanma, 60 s-lik sweep,
  POST kilidi, monitor və nəticə vaxtı eyni rəqəmi görür. Başqa cəhdlərə toxunulmur.
* Yazı cəhd sətrinin ``SELECT … FOR UPDATE`` kilidi altındadır: sweep (``skip_locked``) və ya tələbənin təhvili
  ilə yarışda bitmiş cəhdə vaxt yazılmır, iki paralel əlavə də itmir (cəm saxlanılır).
* Yalnız DAVAM EDƏN (bitməmiş, vaxtı + grace hələ keçməmiş, müddətli) cəhdə. Bir əmrdə 1–60 dəq, cəmi ≤ 120 dəq.
* Tələbənin ekranı yeni vaxtı yenidən yükləmədən alır: WS (``time_extended``), nəzarət status sorğusu və
  autosave cavabı ``extra_time_seconds`` cəmini daşıyır; brauzer fərqi öz deadline-ına əlavə edir (saat
  fərqindən asılı deyil). Yenidən qoşulan / səhifəni yeniləyən tələbə qalan vaxtı serverdən təzə alır.
* Audit: kim, neçə dəqiqə, səbəb, əvvəlki və yeni deadline (``AuditLog``).
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from apps.exams.models import ExamAttempt
from core.audit import log_action
from core.constants import AuditAction

#: Bir əmrdə verilə bilən dəqiqə aralığı və bir cəhd üçün cəmi hədd.
MIN_STEP_MINUTES = 1
MAX_STEP_MINUTES = 60
MAX_TOTAL_MINUTES = 120
REASON_MAX = 500


class TimeExtensionError(ValueError):
    """İstifadəçiyə göstərilən (tərcümə olunmuş) imtina mesajı."""


def extra_minutes(attempt) -> int:
    return int(getattr(attempt, "extra_time_seconds", 0) or 0) // 60


def remaining_extension_minutes(attempt) -> int:
    """Bu cəhdə hələ verilə bilən dəqiqə (cəmi hədddən qalan)."""
    return max(0, MAX_TOTAL_MINUTES - extra_minutes(attempt))


def can_extend(attempt) -> bool:
    """Monitor düyməsinin görünməsi üçün ucuz yoxlama (sorğusuz); server əməldə yenidən yoxlayır."""
    if attempt is None or attempt.is_finished or attempt.deadline_at is None:
        return False
    return remaining_extension_minutes(attempt) >= MIN_STEP_MINUTES


def _parse_minutes(raw) -> int:
    try:
        minutes = int(str(raw).strip())
    except (TypeError, ValueError):
        raise TimeExtensionError(pgettext("exams.time_extension", "Dəqiqə sayını rəqəmlə yazın.")) from None
    if minutes < MIN_STEP_MINUTES or minutes > MAX_STEP_MINUTES:
        raise TimeExtensionError(
            pgettext("exams.time_extension", "Bir dəfəyə %(min)d–%(max)d dəqiqə əlavə etmək olar.")
            % {"min": MIN_STEP_MINUTES, "max": MAX_STEP_MINUTES}
        )
    return minutes


def extend_attempt_time(attempt, by, *, minutes, reason: str, request=None) -> dict:
    """Davam edən cəhdə ``minutes`` dəqiqə əlavə et → yeni vəziyyət (``deadline_at``, ``remaining_seconds``…).

    İmtina hallarında ``TimeExtensionError`` (mətn istifadəçiyə göstərilir).
    """
    minutes = _parse_minutes(minutes)
    reason = (reason or "").strip()[:REASON_MAX]
    if not reason:
        raise TimeExtensionError(pgettext("exams.time_extension", "Əlavə vaxtın səbəbini yazın."))

    with transaction.atomic():
        locked = (
            ExamAttempt.objects.select_for_update(of=("self",))
            .select_related("exam", "exam__organization")
            .filter(pk=attempt.pk)
            .first()
        )
        if locked is None or locked.is_finished:
            raise TimeExtensionError(
                pgettext("exams.time_extension", "Tələbə imtahanı artıq bitirib — əlavə vaxt verilə bilməz.")
            )
        old_deadline = locked.deadline_at
        if old_deadline is None:
            raise TimeExtensionError(
                pgettext("exams.time_extension", "Bu imtahanda vaxt limiti yoxdur — əlavə vaxt lazım deyil.")
            )
        # Deadline keçibsə əlavə vaxt verilmir — brauzer taymeri 00:00-da artıq avtomatik təhvil göndərir; grace
        # yalnız tələbənin son POST-u üçündür (deadline-dan sonra «uğurlu» uzatma yanıltıcı olardı).
        if timezone.now() >= old_deadline:
            raise TimeExtensionError(
                pgettext(
                    "exams.time_extension",
                    "İmtahan vaxtı artıq bitib — əlavə vaxt yalnız davam edən imtahana verilir.",
                )
            )
        if minutes > remaining_extension_minutes(locked):
            raise TimeExtensionError(
                pgettext(
                    "exams.time_extension",
                    "Bir tələbəyə cəmi %(max)d dəqiqədən çox əlavə vaxt verilə bilməz (artıq verilib: %(given)d dəq).",
                )
                % {"max": MAX_TOTAL_MINUTES, "given": extra_minutes(locked)}
            )
        old_extra = int(locked.extra_time_seconds or 0)
        locked.extra_time_seconds = old_extra + minutes * 60
        locked.save(update_fields=["extra_time_seconds"])
        new_deadline = locked.deadline_at
        log_action(
            AuditAction.UPDATE,
            user=by,
            organization=locked.exam.organization,
            obj=locked,
            old_values={"extra_time_seconds": old_extra, "deadline_at": old_deadline.isoformat()},
            new_values={
                "extra_time_seconds": locked.extra_time_seconds,
                "deadline_at": new_deadline.isoformat(),
                "added_minutes": minutes,
            },
            reason=f"exam_attempt_time_extended[+{minutes}m]: {reason}"[:500],
            request=request,
            resource_type="exams.ExamAttempt",
            resource_id=str(locked.pk),
            resource_repr=getattr(locked.exam, "title", ""),
        )
    attempt.extra_time_seconds = locked.extra_time_seconds
    remaining = max(0, int((new_deadline - timezone.now()).total_seconds()))
    state = {
        "attempt_id": locked.pk,
        "added_minutes": minutes,
        "extra_time_seconds": locked.extra_time_seconds,
        "extra_minutes": extra_minutes(locked),
        "deadline_at": new_deadline.isoformat(),
        "remaining_seconds": remaining,
        "can_add_minutes": remaining_extension_minutes(locked),
    }
    transaction.on_commit(lambda: _notify(locked.pk, state))
    return state


def _notify(attempt_id: int, state: dict) -> None:
    """Tələbənin açıq səhifəsinə (WS) xəbər — brauzer deadline-ını yerində uzadır. Xəta imtahanı sındırmır."""
    from apps.exams.services.supervision import notify_attempt_student

    notify_attempt_student(
        attempt_id,
        {
            "action": "time_extended",
            "extra_time_seconds": state["extra_time_seconds"],
            "added_minutes": state["added_minutes"],
            "remaining_seconds": state["remaining_seconds"],
        },
    )


__all__ = [
    "MAX_STEP_MINUTES",
    "MAX_TOTAL_MINUTES",
    "MIN_STEP_MINUTES",
    "TimeExtensionError",
    "can_extend",
    "extend_attempt_time",
    "extra_minutes",
    "remaining_extension_minutes",
]
