from collections import defaultdict
from datetime import timedelta
from functools import partial

from django.db import transaction
from django.db.models import Prefetch, Q
from django.dispatch import receiver
from django.utils import timezone

from core.journal_events import journal_cells_changed
from core.rls_pooling import rls_worker_atomic

from .journal_watch_models import (
    JournalWatch,
    JournalWatchBatch,
    JournalWatchEvent,
    JournalWatchMailItem,
    JournalWatchRecipient,
    JournalWatchRoute,
    PersonKind,
    WatchKind,
)
from .journal_watch_scope import watch_tenant

COOLDOWN = timedelta(minutes=5)


def _kind(value):
    if value == "—":
        return WatchKind.CLEAR
    if value.split()[0] == "qb":
        return WatchKind.ABSENT
    if value.startswith("iə "):
        return WatchKind.SCORE
    if value == "iə":
        return WatchKind.PRESENT
    # An excused absence can only be entered by the formal correction workflow.
    return WatchKind.CHANGE


def _label(user):
    return (user.get_full_name() or user.get_username())[:250] if user else ""


def _dispatch(organization_id, batch_id, send_after):
    from .journal_watch_mail import deliver_journal_watch

    deliver_journal_watch.apply_async(args=(str(organization_id), str(batch_id)), eta=send_after)


@receiver(journal_cells_changed, dispatch_uid="monitoring.journal.watch.cells")
def record_changes(sender, *, offering, actor, changes, request=None, **kwargs):
    """Called only for accepted UI writes. An empty active-cell placeholder has no event."""
    if not actor or not actor.pk:
        return
    active = [
        (lesson, enrollment, old, new)
        for lesson, enrollment, old, new in changes
        if not lesson.is_passive
        and old != new
        and enrollment.organization_id == offering.organization_id
        and lesson.organization_id == offering.organization_id
        and lesson.offering_id == offering.pk
        and enrollment.offering_id == offering.pk
    ]
    if not active:
        return
    if request and getattr(request, "organization", None) and request.organization.pk != offering.organization_id:
        return
    # The publishing service already owns the grade-write transaction and its RLS scope.
    # A single indexed lookup avoids setting up the optional delivery machinery for a tenant with no active rules.
    if (
        transaction.get_connection().in_atomic_block
        and not JournalWatch.objects.filter(organization_id=offering.organization_id, is_active=True).exists()
    ):
        return
    with rls_worker_atomic(), transaction.atomic(), watch_tenant(offering.organization_id):
        _record_active(offering, actor, active, request)


def _record_active(offering, actor, active, request):
    org_id = offering.organization_id
    routes = JournalWatchRoute.objects.filter(
        organization_id=org_id, recipient__organization_id=org_id, recipient__verified_at__isnull=False
    )
    real = getattr(request, "real_user", None) if getattr(request, "is_view_as", False) else None
    actor_ids = {actor.pk, real.pk} if getattr(real, "pk", None) else {actor.pk}
    subs = (
        JournalWatch.objects.filter(organization_id=org_id, is_active=True)
        .filter(
            Q(person_kind=PersonKind.ACTOR, person_id__in=actor_ids)
            | Q(person_kind=PersonKind.STUDENT, person_id__in={e.student_id for _, e, _, _ in active})
        )
        .prefetch_related(Prefetch("routes", queryset=routes, to_attr="verified_routes"))
    )
    watches = defaultdict(list)
    for sub in subs:
        watches[sub.person_kind, sub.person_id].append(sub)
    if not watches:
        return
    now = timezone.now()
    events = []
    deliveries = {}
    for lesson, enrollment, old, new in active:
        kind = _kind(new)
        correction = old != "—"
        wanted = {kind, WatchKind.CHANGE} if correction else {kind}
        targets = [(PersonKind.ACTOR, person_id) for person_id in actor_ids]
        targets.append((PersonKind.STUDENT, enrollment.student_id))
        matching = [rule for target in targets for rule in watches[target] if wanted.intersection(rule.event_types)]
        if not matching:
            continue
        event = JournalWatchEvent(
            organization_id=org_id,
            actor_id=actor.pk,
            actor_label=_label(actor),
            student_id=enrollment.student_id,
            student_label=_label(enrollment.student),
            real_actor_id=getattr(real, "pk", None),
            real_actor_label=_label(real),
            offering_id=offering.pk,
            offering_label=str(offering.subject.name)[:300],
            lesson_id=lesson.pk,
            enrollment_id=enrollment.pk,
            lesson_date=lesson.date,
            kind=kind,
            is_correction=correction,
            old_value=old,
            new_value=new,
            created_at=now,
        )
        events.append(event)
        recipient_ids = {r.recipient_id for s in matching for r in s.verified_routes}
        for recipient_id in recipient_ids:
            deliveries.setdefault(recipient_id, []).append(event)
    if not events:
        return
    JournalWatchEvent.objects.bulk_create(events)
    for recipient in (
        JournalWatchRecipient.objects.select_for_update()
        .filter(organization_id=org_id, pk__in=deliveries, verified_at__isnull=False)
        .order_by("pk")
    ):
        # A first event goes out at commit. A second slot collects following events even
        # if the first job is still in the broker. Recipient row locks serialize this decision.
        opened = JournalWatchBatch.objects.filter(
            organization_id=org_id, recipient=recipient, sent_at=None, cancelled_at=None
        )
        batch = opened.filter(immediate=False).first()
        created = False
        if batch is None:
            immediate = recipient.cooldown_until is None or recipient.cooldown_until <= now
            batch, created = opened.get_or_create(
                immediate=immediate,
                defaults={
                    "organization_id": org_id,
                    "recipient": recipient,
                    "send_after": now if immediate else recipient.cooldown_until,
                },
            )
            if immediate and created:
                recipient.cooldown_until = now + COOLDOWN
                recipient.save(update_fields=["cooldown_until"])
        JournalWatchMailItem.objects.bulk_create(
            [
                JournalWatchMailItem(organization_id=org_id, batch=batch, recipient=recipient, event=e)
                for e in deliveries[recipient.pk]
            ]
        )
        if created:
            transaction.on_commit(partial(_dispatch, org_id, batch.pk, batch.send_after), robust=True)
