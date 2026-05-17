"""
AI Assistant chat log model.

Every AI assistant request is logged for audit, abuse detection, and analytics.
Sensitive user data is NOT stored — only the prompt text and a response summary.
"""

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel, UUIDModel


class AIAssistantLog(UUIDModel, TimeStampedModel):
    """Audit log for every AI assistant interaction."""

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        BLOCKED = "blocked", "Blocked"
        RATE_LIMITED = "rate_limited", "Rate Limited"
        ERROR = "error", "Error"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_assistant_logs",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_assistant_logs",
    )
    role_name = models.CharField(max_length=100, blank=True, default="")
    prompt = models.TextField()
    response_summary = models.CharField(max_length=500, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUCCESS)
    block_reason = models.CharField(max_length=255, blank=True, default="")
    prompt_tokens = models.PositiveIntegerField(default=0)
    response_tokens = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["organization", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return f"AI Log {self.user_id} [{self.status}] {self.created_at}"
