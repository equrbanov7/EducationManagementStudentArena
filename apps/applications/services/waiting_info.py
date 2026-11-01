"""Cavabsız əlavə məlumat sorğusu: üç iş günü, ayrıca bağlanma və təhlükəsiz yenidən baxış."""

from datetime import datetime

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from ..constants import WAITING_INFO_WORKING_DAYS, ApplicationStatus, EventKind
from ..models import Application
from ..sla import add_working_days, calendar_for
from ..state_machine import Action
from . import notify


def resume_sla(application):
    application.sla_due_on = add_working_days(
        timezone.localdate(), application.kind.sla_days, calendar_for(application.organization_id)
    )


def resume_sender_comment(application, user, *, is_internal=False):
    """Sahibin adi cavabı da gözləməyi bitirir; əməkdaşın daxili qeydi müddəti uzatmır."""
    if is_internal or application.status != ApplicationStatus.WAITING_INFO or user.pk != application.created_by_id:
        return False
    application.status = ApplicationStatus.IN_REVIEW
    resume_sla(application)
    return True


def waiting_deadline(application, calendar=None):
    requested_at = application.events.filter(kind=EventKind.INFO_REQUESTED).aggregate(at=Max("created_at"))["at"]
    # Tarixçəsi olmayan köhnə/manual status üçün ən son fəaliyyətdən əvvəl bağlama.
    requested_at = requested_at or application.last_activity_at
    local = timezone.localtime(requested_at)
    day = add_working_days(
        local.date(),
        WAITING_INFO_WORKING_DAYS,
        calendar if calendar is not None else calendar_for(application.organization_id),
    )
    return requested_at, timezone.make_aware(datetime.combine(day, local.time()), timezone.get_current_timezone())


@transaction.atomic
def close(*, application, user, text="", request=None):
    """Əvvəlki sahib təsdiqi: workflow.close import səthi saxlanılır."""
    from . import workflow

    rule = workflow._guard(user, application, Action.CLOSE)
    old = application.status
    application.status = rule.target
    application.closed_at = timezone.now()
    workflow._touch(application, ["status", "closed_at"])
    workflow._write_event(application, kind=EventKind.CLOSED, actor=user, text=text, old=old)
    notify.audit(application, action=notify.AUDIT_UPDATE, actor=user, event_kind=EventKind.CLOSED, request=request)
    return application


def _close_waiting(application, user, *, text, request=None):
    from . import workflow

    old = application.status
    application.status = ApplicationStatus.CLOSED
    application.closed_at = timezone.now()
    application.resolved_at = None
    workflow._touch(application, ["status", "closed_at", "resolved_at"])
    workflow._write_event(application, kind=EventKind.CLOSED, actor=user, text=text, old=old)
    notify.audit(
        application,
        action=notify.AUDIT_UPDATE,
        actor=user,
        event_kind=EventKind.CLOSED,
        reason="waiting_info_no_reply" if user else "auto_close_waiting_info_no_reply",
        changes={"status": [old, application.status]},
        request=request,
    )
    notify.notify_sender(application, title=f"{application.number} bağlandı", message=text)
    return application


@transaction.atomic
def close_waiting(*, application, user, request=None):
    """Yalnız səlahiyyətli emalçı gözləyən müraciəti əlavə cavab yazmadan bağlayır."""
    from . import workflow

    workflow._guard(user, application, Action.CLOSE_WAITING)
    return _close_waiting(application, user, text="Əlavə məlumat alınmadığı üçün müraciət bağlandı.", request=request)


def close_stale_waiting_info(*, organization=None, now=None):
    """Hər namizədi təzə kilidlə yoxla; istifadəçi cavabı, yeni sorğu və silinmə yarışda qorunur."""
    now = now or timezone.now()
    candidates = Application.objects.filter(status=ApplicationStatus.WAITING_INFO, deleted_at__isnull=True)
    if organization is not None:
        candidates = candidates.filter(organization=organization)
    calendars, closed = {}, 0
    for ident, org_id in candidates.values_list("pk", "organization_id").iterator(chunk_size=200):
        with transaction.atomic():
            application = Application.objects.select_for_update().get(pk=ident, organization_id=org_id)
            if application.status != ApplicationStatus.WAITING_INFO or application.deleted_at is not None:
                continue
            if org_id not in calendars:
                calendars[org_id] = calendar_for(org_id)
            requested_at, deadline = waiting_deadline(application, calendars[org_id])
            if (
                deadline > now
                or application.events.filter(
                    actor_id=application.created_by_id,
                    is_internal=False,
                    created_at__gte=requested_at,
                    kind__in=[EventKind.COMMENT, EventKind.INFO_PROVIDED],
                ).exists()
            ):
                continue
            _close_waiting(
                application,
                None,
                text=f"Əlavə məlumat sorğusuna {WAITING_INFO_WORKING_DAYS} iş günü ərzində cavab gəlmədi — avtomatik bağlandı.",
            )
            closed += 1
    return closed
