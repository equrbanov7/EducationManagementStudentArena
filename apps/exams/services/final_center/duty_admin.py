"""final_center paketi — nəzarətçi növbəsinin YAZILMASI / ləğvi (2026-10-13, gecə).

Oxu/icazə tərəfi ``duties.py``-dadır; burada yalnız rəhbərin əməlləri:

* ``create_duties`` — bir zal + bir günün vaxt aralığı üçün bir neçə nəzarətçi;
* ``revoke_duty`` — növbəni dərhal bağlayır (sətir silinmir — audit izi).

Qaydalar (server tərəfində, UI gizlətməsinə güvənmədən):

* yalnız tələbə OLMAYAN aktiv təşkilat üzvləri (sahib 2026-09-07: tələbə heç vaxt
  müəllim/nəzarətçi deyil) — kənar id-lər səssiz atılmır, xəta qaytarılır;
* pəncərə bir təqvim günü daxilindədir (Asia/Baku), son > başlanğıc;
* keçmiş gün yazılmır; ``DUTY_MAX_DAYS_AHEAD``-dən irəli yazılmır;
* eyni (zal, istifadəçi, başlanğıc, son) aktiv növbə təkrarlanmır (idempotent);
* hər yazı/ləğv ``AuditLog``-a düşür.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from apps.exams.models import InvigilatorDuty
from core.audit import log_actions
from core.constants import AuditAction

from .duties import BAKU_TZ, DUTY_MAX_DAYS_AHEAD

_CTX = "exams.final_center.duty"
_STUDENT_ROLE_NAMES = ("student", "lead_student")
MAX_INVIGILATORS_PER_DUTY = 20


class DutyError(ValueError):
    """Növbə yazısı rədd olundu — mesaj istifadəçiyə göstərilir."""


def parse_duty_window(day_raw, start_raw, end_raw, *, now=None):
    """(starts_at, ends_at) aware datetime-lar — Bakı vaxtı ilə bir gün daxilində."""
    now = now or timezone.now()
    try:
        day = date.fromisoformat((day_raw or "").strip())
        start_t = datetime.strptime((start_raw or "").strip(), "%H:%M").time()
        end_t = datetime.strptime((end_raw or "").strip(), "%H:%M").time()
    except ValueError as exc:
        raise DutyError(pgettext(_CTX, "Tarix və ya saat formatı yanlışdır.")) from exc
    today = now.astimezone(BAKU_TZ).date()
    if day < today:
        raise DutyError(pgettext(_CTX, "Keçmiş gün üçün növbə yazmaq olmaz."))
    if day > today + timedelta(days=DUTY_MAX_DAYS_AHEAD):
        raise DutyError(
            pgettext(_CTX, "Növbəni ən çox %(days)d gün irəli yazmaq olar.") % {"days": DUTY_MAX_DAYS_AHEAD}
        )
    if end_t <= start_t:
        raise DutyError(pgettext(_CTX, "Bitmə saatı başlama saatından sonra olmalıdır."))
    starts_at = datetime.combine(day, start_t, tzinfo=BAKU_TZ)
    ends_at = datetime.combine(day, end_t, tzinfo=BAKU_TZ)
    if ends_at <= now:
        raise DutyError(pgettext(_CTX, "Bu vaxt aralığı artıq bitib."))
    return starts_at, ends_at


def eligible_invigilators(candidates_qs, user_ids):
    """Namizəd sorğusundan (``center_staff_queryset``) tələbə rollu üzvləri də çıxarır."""
    from django.apps import apps as django_apps
    from django.db.models import Exists, OuterRef

    membership_model = django_apps.get_model("organizations", "Membership")
    # ``Exists`` — eyni üzvlük sətrində həm aktiv, həm tələbə rolu (multi-valued exclude tələsi yox).
    student_membership = membership_model.objects.filter(
        user_id=OuterRef("pk"), is_active=True, role__name__in=_STUDENT_ROLE_NAMES
    )
    return list(candidates_qs.filter(id__in=user_ids).exclude(Exists(student_membership)))


def create_duties(room, users, starts_at, ends_at, *, by, note="", request=None) -> list:
    """Növbələri yaradır; artıq mövcud olan (eyni pəncərə, ləğvsiz) təkrar yazılmır."""
    if not users:
        raise DutyError(pgettext(_CTX, "Ən azı bir nəzarətçi seçin."))
    if len(users) > MAX_INVIGILATORS_PER_DUTY:
        raise DutyError(
            pgettext(_CTX, "Bir növbəyə ən çox %(n)d nəzarətçi təyin etmək olar.") % {"n": MAX_INVIGILATORS_PER_DUTY}
        )
    note = (note or "").strip()[:200]
    created = []
    with transaction.atomic():
        existing = set(
            InvigilatorDuty.objects.filter(
                room=room, starts_at=starts_at, ends_at=ends_at, revoked_at__isnull=True, user__in=users
            ).values_list("user_id", flat=True)
        )
        for user in users:
            if user.pk in existing:
                continue
            created.append(
                InvigilatorDuty.objects.create(
                    organization_id=room.organization_id,
                    room=room,
                    user=user,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    note=note,
                    assigned_by=by,
                )
            )
        log_actions(
            [
                {
                    "action": AuditAction.CREATE,
                    "user": by,
                    "organization": room.organization,
                    "obj": duty,
                    "reason": "final_room_invigilator_duty_created",
                    "request": request,
                    "changes": {
                        "room_id": room.pk,
                        "invigilator_id": duty.user_id,
                        "starts_at": starts_at.isoformat(),
                        "ends_at": ends_at.isoformat(),
                    },
                    "resource_type": "invigilator_duty",
                    "resource_id": str(duty.pk),
                }
                for duty in created
            ]
        )
    return created


def revoke_duty(duty, *, by, request=None) -> bool:
    """Növbəni dərhal bağlayır. Artıq ləğv olunubsa False (idempotent)."""
    now = timezone.now()
    updated = InvigilatorDuty.objects.filter(pk=duty.pk, revoked_at__isnull=True).update(revoked_at=now, revoked_by=by)
    if not updated:
        return False
    duty.revoked_at = now
    duty.revoked_by = by
    log_actions(
        [
            {
                "action": AuditAction.UPDATE,
                "user": by,
                "organization": duty.room.organization,
                "obj": duty,
                "reason": "final_room_invigilator_duty_revoked",
                "request": request,
                "changes": {"room_id": duty.room_id, "invigilator_id": duty.user_id},
                "resource_type": "invigilator_duty",
                "resource_id": str(duty.pk),
            }
        ]
    )
    return True


def default_duty_form(now=None) -> dict:
    """Forma defoltları: bu gün, cari saat (15 dəq. aşağı yuvarlaq) → +3 saat (gün daxilində)."""
    now = (now or timezone.now()).astimezone(BAKU_TZ)
    start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    end = min(start + timedelta(hours=3), start.replace(hour=23, minute=45))
    if end <= start:
        end = start.replace(hour=23, minute=59)
    return {"date": start.date().isoformat(), "start": start.strftime("%H:%M"), "end": end.strftime("%H:%M")}


__all__ = [
    "DutyError",
    "MAX_INVIGILATORS_PER_DUTY",
    "create_duties",
    "default_duty_form",
    "eligible_invigilators",
    "parse_duty_window",
    "revoke_duty",
]
