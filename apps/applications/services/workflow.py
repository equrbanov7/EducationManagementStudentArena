"""Keçidlərin İCRASI — hər biri bir tranzaksiya, bir hadisə, bir audit sətri.

Qayda seçimi ``state_machine.ensure_allowed``-dadır; burada İCAZƏ yoxlanır,
sətir yazılır və yan-təsirlər (bildiriş, audit, badge keşi) tetiklənir.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from ..constants import MIN_NOTE_LENGTH, ApplicationStatus, EventKind
from ..models import ApplicationEvent, ApplicationWatch
from ..state_machine import ACTOR_HANDLER, Action, TransitionDenied, ensure_allowed, rule_for
from . import access, notify
from .submit import attach_files

#: Əməl → zaman xətti hadisə növü.
_EVENT_KIND = {
    Action.MARK_SEEN: EventKind.SEEN,
    Action.ADD_COMMENT: EventKind.COMMENT,
    Action.ASSIGN: EventKind.ASSIGNED,
    Action.FORWARD: EventKind.FORWARDED,
    Action.REQUEST_INFO: EventKind.INFO_REQUESTED,
    Action.PROVIDE_INFO: EventKind.INFO_PROVIDED,
    Action.RETURN_FOR_CORRECTION: EventKind.RETURNED,
    Action.RESUBMIT: EventKind.RESUBMITTED,
    Action.RESOLVE: EventKind.RESOLVED,
    Action.REJECT: EventKind.REJECTED,
    Action.CLOSE: EventKind.CLOSED,
    Action.CANCEL: EventKind.CANCELLED,
}


def _actor_name(user) -> str:
    if user is None:
        return "Sistem"
    return (user.get_full_name() or user.get_username())[:200]


def _authorize(user, application, rule):
    """Aktor tipinə görə icazə — fail-closed."""
    if rule.actor == ACTOR_HANDLER:
        if not access.can_act(user, application):
            raise TransitionDenied("permission.not_handler", "Bu müraciət sizin şöbənizdə deyil.")
        return
    if not access.is_sender(user, application):
        raise TransitionDenied("permission.not_sender", "Bu əməli yalnız müraciət sahibi edə bilər.")


def _guard(user, application, action, text=""):
    """İCAZƏ əvvəl, STATUS sonra — qəsdən bu sıra ilə.

    Əks sıra vəziyyət sızdırardı: səlahiyyətsiz istifadəçi «bu status bu əməli
    qəbul etmir» cavabından müraciətin harada olduğunu öyrənərdi. Ona görə
    aktor yoxlanışı hər zaman birincidir.
    """
    _authorize(user, application, rule_for(action))
    return ensure_allowed(action=action, status=application.status, text=text)


def _write_event(application, *, kind, actor, text="", is_internal=False, from_unit=None, to_unit=None, old=None):
    role_name = ""
    if actor is not None:
        role_name = access.handler_role_for(actor, application.organization, application.current_unit)
    return ApplicationEvent.objects.create(
        organization=application.organization,
        application=application,
        kind=kind,
        actor=actor,
        actor_name=_actor_name(actor),
        actor_role_name=role_name,
        from_unit=from_unit,
        to_unit=to_unit,
        old_status=old or "",
        new_status=application.status,
        text=(text or "").strip(),
        is_internal=bool(is_internal),
    )


def _touch(application, fields):
    application.last_activity_at = timezone.now()
    application.save(update_fields=list(dict.fromkeys([*fields, "last_activity_at", "updated_at"])))


@transaction.atomic
def mark_seen(*, application, user, request=None) -> bool:
    """Emalçı müraciəti İLK dəfə açanda ``Yeni → Baxılır``. İdempotentdir."""
    if application.status != ApplicationStatus.SUBMITTED.value:
        return False
    rule = _guard(user, application, Action.MARK_SEEN)
    old = application.status
    application.status = rule.target
    _touch(application, ["status"])
    _write_event(application, kind=EventKind.SEEN, actor=user, old=old)
    notify.audit(application, action=notify.AUDIT_UPDATE, actor=user, event_kind=EventKind.SEEN, request=request)
    return True


@transaction.atomic
def add_comment(*, application, user, text: str, is_internal: bool = False, files=None, request=None):
    """Statusu dəyişməyən qeyd. Daxili qeydi yalnız emalçı yaza bilər."""
    is_handler = access.can_act(user, application)
    if not is_handler:
        if not access.is_sender(user, application):
            raise TransitionDenied("permission.denied", "Bu müraciətə qeyd yaza bilməzsiniz.")
        # Sahibin qeydi HEÇ VAXT daxili ola bilməz — daxili qeyd emalçı sirridir.
        is_internal = False
    ensure_allowed(action=Action.ADD_COMMENT, status=application.status, text=text)
    event = _write_event(application, kind=EventKind.COMMENT, actor=user, text=text, is_internal=is_internal)
    attach_files(application, files, event=event, uploaded_by=user)
    _touch(application, [])
    notify.audit(application, action=notify.AUDIT_UPDATE, actor=user, event_kind=EventKind.COMMENT, request=request)
    if is_handler and not is_internal:
        notify.notify_sender(
            application,
            title=f"{application.number} — yeni qeyd",
            message=text.strip()[:200],
        )
    elif not is_handler:
        notify.notify_current_unit(
            application,
            title=f"{application.number} — müraciət sahibindən qeyd",
            message=text.strip()[:200],
        )
    return event


@transaction.atomic
def assign(*, application, user, assignee, note: str = "", request=None):
    """Müraciəti CARİ şöbənin konkret əməkdaşına təyin edir."""
    rule = _guard(user, application, Action.ASSIGN, note)
    if assignee is None or not access.handles_unit(
        assignee, application.organization, application.current_unit, application.current_scope_unit
    ):
        raise TransitionDenied("assignee.not_handler", "Seçilən şəxs bu şöbənin emalçısı deyil.")
    old = application.status
    application.status = rule.target
    application.assigned_to = assignee
    _touch(application, ["status", "assigned_to"])
    _write_event(application, kind=EventKind.ASSIGNED, actor=user, text=note or _actor_name(assignee), old=old)
    notify.audit(
        application,
        action=notify.AUDIT_UPDATE,
        actor=user,
        event_kind=EventKind.ASSIGNED,
        changes={"assigned_to": str(assignee.pk)},
        request=request,
    )
    notify.notify_users(
        application,
        [assignee],
        title=f"{application.number} sizə təyin edildi",
        message=application.subject,
    )
    notify.notify_sender(
        application,
        title=f"{application.number} — məsul şəxs təyin edildi",
        message=application.current_unit.name,
    )
    return application


@transaction.atomic
def forward(*, application, user, target_unit, note: str, keep_watching: bool = True, request=None):
    """Müraciəti BAŞQA şöbəyə ötürür; müraciət İTMİR, məsul şöbə dəyişir."""
    rule = _guard(user, application, Action.FORWARD, note)
    if target_unit is None or not target_unit.is_active:
        raise TransitionDenied("unit.unknown", "Hədəf şöbə tapılmadı.")
    if target_unit.pk == application.current_unit_id:
        raise TransitionDenied("unit.same", "Hədəf şöbə cari şöbə ilə eyni ola bilməz.")

    from .routing import resolve_scope_unit

    source_unit = application.current_unit
    source_scope = application.current_scope_unit
    old = application.status
    application.status = rule.target
    application.current_unit = target_unit
    application.current_scope_unit = resolve_scope_unit(target_unit, application.sender_scope_unit)
    application.assigned_to = None
    _touch(application, ["status", "current_unit", "current_scope_unit", "assigned_to"])

    if keep_watching:
        ApplicationWatch.objects.get_or_create(
            application=application,
            unit=source_unit,
            defaults={"organization": application.organization, "scope_unit": source_scope},
        )

    _write_event(
        application,
        kind=EventKind.FORWARDED,
        actor=user,
        text=note,
        from_unit=source_unit,
        to_unit=target_unit,
        old=old,
    )
    notify.audit(
        application,
        action=notify.AUDIT_UPDATE,
        actor=user,
        event_kind=EventKind.FORWARDED,
        reason=note,
        changes={"from_unit": source_unit.code, "to_unit": target_unit.code},
        request=request,
    )
    notify.notify_current_unit(
        application,
        title=f"{application.number} — {source_unit.name} şöbəsindən yönləndirildi",
        message=note.strip()[:200],
    )
    notify.notify_sender(
        application,
        title=f"{application.number} yönləndirildi",
        message=f"Yeni məsul şöbə: {target_unit.name}",
    )
    return application


def _handler_status_change(*, application, user, action, text, event_kind, request, sender_title):
    rule = _guard(user, application, action, text)
    old = application.status
    application.status = rule.target
    fields = ["status"]
    if rule.target == ApplicationStatus.RESOLVED.value:
        application.resolved_at = timezone.now()
        fields.append("resolved_at")
    if rule.target == ApplicationStatus.REJECTED.value:
        application.resolved_at = timezone.now()
        application.closed_at = timezone.now()
        fields += ["resolved_at", "closed_at"]
    _touch(application, fields)
    _write_event(application, kind=event_kind, actor=user, text=text, old=old)
    notify.audit(
        application,
        action=notify.AUDIT_UPDATE,
        actor=user,
        event_kind=event_kind,
        reason=text,
        changes={"status": [old, application.status]},
        request=request,
    )
    notify.notify_sender(application, title=sender_title, message=(text or "").strip()[:400])
    return application


@transaction.atomic
def request_info(*, application, user, text: str, files=None, request=None):
    application = _handler_status_change(
        application=application,
        user=user,
        action=Action.REQUEST_INFO,
        text=text,
        event_kind=EventKind.INFO_REQUESTED,
        request=request,
        sender_title=f"{application.number} — əlavə məlumat istənilir",
    )
    attach_files(application, files, uploaded_by=user)
    return application


@transaction.atomic
def return_for_correction(*, application, user, reason: str, request=None):
    return _handler_status_change(
        application=application,
        user=user,
        action=Action.RETURN_FOR_CORRECTION,
        text=reason,
        event_kind=EventKind.RETURNED,
        request=request,
        sender_title=f"{application.number} düzəliş üçün qaytarıldı",
    )


@transaction.atomic
def resolve(*, application, user, text: str, files=None, request=None):
    application = _handler_status_change(
        application=application,
        user=user,
        action=Action.RESOLVE,
        text=text,
        event_kind=EventKind.RESOLVED,
        request=request,
        sender_title=f"{application.number} həll olundu",
    )
    attach_files(application, files, uploaded_by=user)
    notify.notify_users(
        application,
        notify.watcher_recipients(application),
        title=f"{application.number} həll olundu",
        message=application.subject,
    )
    return application


@transaction.atomic
def reject(*, application, user, reason: str, request=None):
    application = _handler_status_change(
        application=application,
        user=user,
        action=Action.REJECT,
        text=reason,
        event_kind=EventKind.REJECTED,
        request=request,
        sender_title=f"{application.number} rədd edildi",
    )
    notify.notify_users(
        application,
        notify.watcher_recipients(application),
        title=f"{application.number} rədd edildi",
        message=reason.strip()[:200],
    )
    return application


@transaction.atomic
def provide_info(*, application, user, text: str, files=None, request=None):
    """Müraciət sahibi istənilən əlavə məlumatı verir → yenidən baxışa."""
    rule = _guard(user, application, Action.PROVIDE_INFO, text)
    old = application.status
    application.status = rule.target
    _touch(application, ["status"])
    event = _write_event(application, kind=EventKind.INFO_PROVIDED, actor=user, text=text, old=old)
    attach_files(application, files, event=event, uploaded_by=user)
    notify.audit(
        application, action=notify.AUDIT_UPDATE, actor=user, event_kind=EventKind.INFO_PROVIDED, request=request
    )
    notify.notify_current_unit(
        application,
        title=f"{application.number} — əlavə məlumat gəldi",
        message=text.strip()[:200],
    )
    return application


@transaction.atomic
def resubmit(*, application, user, subject: str, body: str, files=None, request=None):
    """Qaytarılmış müraciəti düzəldib yenidən göndərir (mətn MƏCBURİ dəyişir)."""
    from .submit import validate_text

    rule = _guard(user, application, Action.RESUBMIT)
    errors = validate_text(subject, body)
    if errors:
        from django.core.exceptions import ValidationError

        raise ValidationError(errors)

    old = application.status
    application.status = rule.target
    application.subject = subject.strip()[:255]
    application.body = body.strip()
    _touch(application, ["status", "subject", "body"])
    event = _write_event(application, kind=EventKind.RESUBMITTED, actor=user, text=application.subject, old=old)
    attach_files(application, files, event=event, uploaded_by=user)
    notify.audit(application, action=notify.AUDIT_UPDATE, actor=user, event_kind=EventKind.RESUBMITTED, request=request)
    notify.notify_current_unit(
        application,
        title=f"{application.number} düzəlişdən sonra yenidən göndərildi",
        message=application.subject,
    )
    return application


@transaction.atomic
def close(*, application, user, text: str = "", request=None):
    """Müraciət sahibi «Həll olunub» nəticəsini təsdiqləyir."""
    rule = _guard(user, application, Action.CLOSE)
    old = application.status
    application.status = rule.target
    application.closed_at = timezone.now()
    _touch(application, ["status", "closed_at"])
    _write_event(application, kind=EventKind.CLOSED, actor=user, text=text, old=old)
    notify.audit(application, action=notify.AUDIT_UPDATE, actor=user, event_kind=EventKind.CLOSED, request=request)
    return application


@transaction.atomic
def cancel(*, application, user, reason: str = "", request=None):
    """Müraciət sahibi açıq müraciəti geri götürür."""
    rule = _guard(user, application, Action.CANCEL)
    old = application.status
    application.status = rule.target
    application.closed_at = timezone.now()
    _touch(application, ["status", "closed_at"])
    _write_event(application, kind=EventKind.CANCELLED, actor=user, text=reason, old=old)
    notify.audit(
        application,
        action=notify.AUDIT_UPDATE,
        actor=user,
        event_kind=EventKind.CANCELLED,
        reason=reason,
        request=request,
    )
    notify.notify_current_unit(
        application,
        title=f"{application.number} ləğv edildi",
        message=reason.strip()[:200],
    )
    return application


#: Endpoint-in qəbul etdiyi əməl adları → servis funksiyaları.
ACTION_DISPATCH = {
    Action.MARK_SEEN: mark_seen,
    Action.ADD_COMMENT: add_comment,
    Action.ASSIGN: assign,
    Action.FORWARD: forward,
    Action.REQUEST_INFO: request_info,
    Action.PROVIDE_INFO: provide_info,
    Action.RETURN_FOR_CORRECTION: return_for_correction,
    Action.RESUBMIT: resubmit,
    Action.RESOLVE: resolve,
    Action.REJECT: reject,
    Action.CLOSE: close,
    Action.CANCEL: cancel,
}

MIN_NOTE = MIN_NOTE_LENGTH

__all__ = [
    "ACTION_DISPATCH",
    "MIN_NOTE",
    "add_comment",
    "assign",
    "cancel",
    "close",
    "forward",
    "mark_seen",
    "provide_info",
    "reject",
    "request_info",
    "resolve",
    "resubmit",
    "return_for_correction",
]
