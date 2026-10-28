"""Əvvəlki məzmunu yalnız müraciətin ACL/RLS sahəsində saxlayan dəyişməz tarixçə."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import TimeStampedModel, UUIDModel


class ApplicationContentRevision(UUIDModel, TimeStampedModel):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="application_content_revisions"
    )
    application = models.ForeignKey(
        "applications.Application", on_delete=models.CASCADE, related_name="content_revisions"
    )
    event = models.ForeignKey(
        "applications.ApplicationEvent",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="content_revisions",
    )
    old_subject = models.CharField(max_length=255, blank=True, default="")
    new_subject = models.CharField(max_length=255, blank=True, default="")
    old_text = models.TextField()
    new_text = models.TextField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="application_content_revisions"
    )

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(
                fields=["organization", "application", "event", "created_at"], name="app_content_revision_event_idx"
            )
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Application content revisions are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Application content revisions cannot be deleted.")
