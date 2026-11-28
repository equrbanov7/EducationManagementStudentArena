"""Persistent journal digest delivery. Celery wakes only scheduled batches and recovers missed handoffs."""

import logging
from datetime import timedelta
from functools import partial

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from celery import shared_task

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

from .journal_watch_models import (
    JournalWatchBatch,
    JournalWatchEvent,
    JournalWatchRecipient,
    JournalWatchRoute,
    PersonKind,
    WatchKind,
)
from .journal_watch_scope import watch_tenant

logger = logging.getLogger(__name__)


def _event_count(batch):
    # Re-check current routing at send time. Disabling a rule or removing its recipient suppresses queued mail.
    routes = JournalWatchRoute.objects.filter(
        organization_id=batch.organization_id,
        recipient_id=batch.recipient_id,
        watch__organization_id=batch.organization_id,
        watch__is_active=True,
    ).select_related("watch")
    allowed = Q(pk__in=[])
    for route in routes:
        watch = route.watch
        event_filter = Q(kind__in=watch.event_types)
        if WatchKind.CHANGE in watch.event_types:
            event_filter |= Q(is_correction=True)
        person_filter = Q(student_id=watch.person_id)
        if watch.person_kind == PersonKind.ACTOR:
            person_filter = Q(actor_id=watch.person_id) | Q(real_actor_id=watch.person_id)
        allowed |= person_filter & event_filter
    return (
        JournalWatchEvent.objects.filter(organization_id=batch.organization_id, mail_items__batch=batch)
        .filter(allowed)
        .count()
    )


@shared_task(name="monitoring.deliver_journal_watch", ignore_result=True)
def deliver_journal_watch(org_id, batch_id):
    with rls_worker_atomic(), transaction.atomic(), watch_tenant(org_id):
        candidate = (
            JournalWatchBatch.objects.filter(
                pk=batch_id, organization_id=org_id, sent_at__isnull=True, cancelled_at__isnull=True
            )
            .values_list("recipient_id", flat=True)
            .first()
        )
        if not candidate:
            return
        # Same lock order as cell recording. Concurrent deliveries and writes to a digest serialize.
        recipient = (
            JournalWatchRecipient.objects.select_for_update().filter(pk=candidate, organization_id=org_id).first()
        )
        batch = (
            JournalWatchBatch.objects.select_for_update()
            .filter(
                pk=batch_id,
                organization_id=org_id,
                sent_at__isnull=True,
                cancelled_at__isnull=True,
                send_after__lte=timezone.now(),
            )
            .first()
        )
        if not batch:
            return
        if not batch.immediate and recipient and recipient.cooldown_until and recipient.cooldown_until > timezone.now():
            batch.send_after = recipient.cooldown_until
            batch.save(update_fields=["send_after"])
            transaction.on_commit(
                partial(deliver_journal_watch.apply_async, args=(str(org_id), str(batch_id)), eta=batch.send_after),
                robust=True,
            )
            return
        count = (
            _event_count(batch)
            if recipient
            and recipient.verified_at
            and recipient.organization.is_active
            and recipient.organization.status == "active"
            else 0
        )
        if not count:
            batch.cancelled_at = timezone.now()
            batch.save(update_fields=["cancelled_at"])
            return
        url = settings.SITE_URL.rstrip("/") + reverse("accounts:profile") + "?section=journal-watch"
        # A forwarded message reveals neither a student nor a grade. Details require the tenant's RİM head.
        subject = pgettext("journal.watch", "Jurnalda izlənilən dəyişikliklər")
        text = pgettext(
            "journal.watch", "Yeni qeydlərin sayı: %(count)s. Ətraflı məlumatı kabinetdə «Nəzarət» bölməsindən açın."
        ) % {"count": count}
        msg = EmailMessage(
            subject,
            text + "\n\n" + url,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient.email],
            headers={"Message-ID": f"<journal-watch-{batch.pk}@ems-notifications.invalid>"},
        )
        batch.attempts += 1
        try:
            if msg.send(fail_silently=False) != 1:
                raise OSError("Journal notification was not accepted")
        except Exception as exc:
            # Keep one row for the same digest and use capped exponential backoff. No address in worker logs.
            logger.error("Journal watch delivery failed for batch %s (%s)", batch.pk, type(exc).__name__)
            batch.send_after = timezone.now() + timedelta(minutes=min(240, 2 ** min(batch.attempts, 8)))
            batch.save(update_fields=["attempts", "send_after"])
            transaction.on_commit(
                partial(deliver_journal_watch.apply_async, args=(str(org_id), str(batch_id)), eta=batch.send_after),
                robust=True,
            )
        else:
            from .journal_watch_events import COOLDOWN

            batch.sent_at = timezone.now()
            recipient.cooldown_until = batch.sent_at + COOLDOWN
            recipient.save(update_fields=["cooldown_until"])
            batch.save(update_fields=["attempts", "sent_at"])


@shared_task(name="monitoring.deliver_journal_watch_confirmation", ignore_result=True)
def deliver_confirmation(org_id, recipient_id):
    from .journal_watch_config import SALT

    with rls_worker_atomic(), transaction.atomic(), watch_tenant(org_id):
        rec = (
            JournalWatchRecipient.objects.select_for_update()
            .filter(
                organization_id=org_id,
                pk=recipient_id,
                verified_at__isnull=True,
                confirmation_next_at__lte=timezone.now(),
            )
            .first()
        )
        if not rec:
            return
        expiry = rec.requested_at + timedelta(days=1)
        if timezone.now() >= expiry or not rec.organization.is_active or rec.organization.status != "active":
            rec.confirmation_next_at = None
            rec.save(update_fields=["confirmation_next_at"])
            return
        token = signing.dumps([str(rec.organization_id), str(rec.pk), str(rec.nonce)], salt=SALT)
        url = settings.SITE_URL.rstrip("/") + reverse("monitoring:journal_watch_confirm") + "#" + token
        msg = EmailMessage(
            pgettext("journal.watch", "Jurnal bildirişləri üçün ünvanı təsdiqləyin"),
            pgettext(
                "journal.watch",
                "Bu ünvanda jurnal bildirişlərini almaq istəyirsinizsə, keçidi açıb təsdiqləyin. Keçid 24 saat qüvvədədir.",
            )
            + "\n\n"
            + url,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[rec.email],
            headers={"Message-ID": f"<journal-watch-confirm-{rec.nonce}@ems-notifications.invalid>"},
        )
        rec.confirmation_attempts += 1
        try:
            if msg.send(fail_silently=False) != 1:
                raise OSError("Journal address verification was not accepted")
        except Exception as exc:
            logger.error("Journal address verification failed for recipient %s (%s)", rec.pk, type(exc).__name__)
            rec.confirmation_next_at = timezone.now() + timedelta(
                minutes=min(240, 2 ** min(rec.confirmation_attempts, 8))
            )
        else:
            rec.confirmation_next_at = None
        if rec.confirmation_next_at and rec.confirmation_next_at >= expiry:
            rec.confirmation_next_at = None
        rec.save(update_fields=["confirmation_attempts", "confirmation_next_at"])
        if rec.confirmation_next_at:
            transaction.on_commit(
                partial(
                    deliver_confirmation.apply_async,
                    args=(str(org_id), str(recipient_id)),
                    eta=rec.confirmation_next_at,
                ),
                robust=True,
            )


@shared_task(name="monitoring.recover_journal_watch_outbox", ignore_result=True)
def recover_journal_watch_outbox():
    # Recovery reads opaque IDs only. Each worker re-enables strict tenant context before loading data.
    with rls_worker_atomic(), transaction.atomic(), bypass_rls():
        due = list(
            JournalWatchBatch.objects.filter(
                sent_at__isnull=True, cancelled_at__isnull=True, send_after__lte=timezone.now()
            )
            .order_by("send_after")
            .values_list("organization_id", "pk")[:200]
        )
        confirmations = list(
            JournalWatchRecipient.objects.filter(verified_at__isnull=True, confirmation_next_at__lte=timezone.now())
            .order_by("confirmation_next_at")
            .values_list("organization_id", "pk")[:200]
        )
    for org_id, recipient_id in confirmations:
        deliver_confirmation.delay(str(org_id), str(recipient_id))
    for org_id, batch_id in due:
        deliver_journal_watch.delay(str(org_id), str(batch_id))
