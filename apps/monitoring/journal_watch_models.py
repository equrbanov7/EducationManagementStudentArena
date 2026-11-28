"""Tenant-owned journal subscriptions, immutable changes and persistent email batches."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import pgettext_lazy


class WatchKind(models.TextChoices):
    ABSENT = "absent", pgettext_lazy("journal.watch", "Qayıb yazılması")
    SCORE = "score", pgettext_lazy("journal.watch", "Bal yazılması")
    PRESENT = "present", pgettext_lazy("journal.watch", "İştirak yazılması")
    CHANGE = "change", pgettext_lazy("journal.watch", "Mövcud qeydin düzəldilməsi")
    CLEAR = "clear", pgettext_lazy("journal.watch", "Qeydin silinməsi")


class PersonKind(models.TextChoices):
    ACTOR = "actor", pgettext_lazy("journal.watch", "Qeydi yazan şəxs")
    STUDENT = "student", pgettext_lazy("journal.watch", "Qeydi izlənilən tələbə")


class TenantWatchRow(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        abstract = True


class JournalWatchRecipient(TenantWatchRow):
    email = models.EmailField()
    verified_at = models.DateTimeField(null=True, editable=False)
    requested_at = models.DateTimeField(default=timezone.now)
    confirmation_next_at = models.DateTimeField(null=True, db_index=True)
    confirmation_attempts = models.PositiveIntegerField(default=0)
    cooldown_until = models.DateTimeField(null=True)
    nonce = models.UUIDField(default=uuid.uuid4, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint("organization", models.functions.Lower("email"), name="jw_recipient_email")
        ]


class JournalWatch(TenantWatchRow):
    person = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    person_kind = models.CharField(max_length=10, choices=PersonKind.choices)
    event_types = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=("organization", "person_kind", "person"), name="jw_watch_target")]


class JournalWatchRoute(TenantWatchRow):
    watch = models.ForeignKey(JournalWatch, on_delete=models.CASCADE, related_name="routes")
    recipient = models.ForeignKey(JournalWatchRecipient, on_delete=models.CASCADE, related_name="routes")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("watch", "recipient"), name="jw_watch_recipient")]


class JournalWatchEvent(TenantWatchRow):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    actor_label = models.CharField(max_length=250)
    student_label = models.CharField(max_length=250)
    real_actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    real_actor_label = models.CharField(max_length=250, blank=True)
    lesson_id = models.UUIDField()
    lesson_date = models.DateField()
    enrollment_id = models.UUIDField()
    offering_id = models.UUIDField()
    offering_label = models.CharField(max_length=300)
    old_value = models.CharField(max_length=40)
    new_value = models.CharField(max_length=40)
    kind = models.CharField(max_length=10, choices=WatchKind.choices)
    is_correction = models.BooleanField(default=False)

    @staticmethod
    def display_value(value):
        code, _, score = value.partition(" ")
        label = {"qb": "q/b", "iə": "i/e", "üq": "ü/q"}.get(code, code)
        return (
            pgettext_lazy("journal.watch", "%(status)s · %(score)s bal") % {"status": label, "score": score}
            if score
            else label
        )

    @property
    def old_display(self):
        return self.display_value(self.old_value)

    @property
    def new_display(self):
        return self.display_value(self.new_value)

    class Meta:
        indexes = [models.Index(fields=("organization", "-created_at"), name="jw_event_time")]


class JournalWatchBatch(TenantWatchRow):
    recipient = models.ForeignKey(JournalWatchRecipient, on_delete=models.CASCADE, related_name="batches")
    immediate = models.BooleanField(default=False)
    send_after = models.DateTimeField(db_index=True)
    sent_at = models.DateTimeField(null=True)
    cancelled_at = models.DateTimeField(null=True)
    attempts = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("recipient", "immediate"),
                condition=models.Q(sent_at__isnull=True, cancelled_at__isnull=True),
                name="jw_open_delivery_slot",
            )
        ]


class JournalWatchMailItem(TenantWatchRow):
    batch = models.ForeignKey(JournalWatchBatch, on_delete=models.CASCADE, related_name="items")
    event = models.ForeignKey(JournalWatchEvent, on_delete=models.CASCADE, related_name="mail_items")
    recipient = models.ForeignKey(JournalWatchRecipient, on_delete=models.CASCADE, related_name="items")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("event", "recipient"), name="jw_event_mail_recipient")]
