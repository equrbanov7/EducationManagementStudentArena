import json

from django.conf import settings
from django.db import models
from django.utils import timezone


class StudentOrganizationRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"
    AUTO_CLOSED = "auto_closed", "Auto Closed"


class StudentOrganizationRequest(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_organization_requests",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="student_organization_requests",
    )
    message = models.CharField(max_length=280, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=StudentOrganizationRequestStatus.choices,
        default=StudentOrganizationRequestStatus.PENDING,
        db_index=True,
    )
    resolution_note = models.CharField(max_length=280, blank=True, default="")
    responded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="processed_student_organization_requests",
        null=True,
        blank=True,
    )
    responded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["organization", "status"]),
        ]

    def __str__(self):
        return f"{self.user} -> {self.organization} ({self.status})"


# ────────────────────────────────────────────────────────────────────────────
# In-App Notification System
# ────────────────────────────────────────────────────────────────────────────


class NotificationType(models.TextChoices):
    ASSIGNMENT = "assignment", "Assignment"
    EXAM = "exam", "Exam"
    GRADE = "grade", "Grade / Feedback"
    SYSTEM = "system", "System / Admin"
    COURSE = "course", "Course"
    LIVE_EXAM = "live_exam", "Live Exam / Session"


class InAppNotification(models.Model):
    """
    Persistent in-app notification for a single user.

    Notifications are never removed automatically.  The user must explicitly
    delete them.  Read/unread state is tracked separately so that opening a
    notification does not lose it.
    """

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="in_app_notifications",
        db_index=True,
    )
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True, default="")
    link = models.CharField(max_length=500, blank=True, default="")
    notification_type = models.CharField(
        max_length=20,
        choices=NotificationType.choices,
        default=NotificationType.SYSTEM,
        db_index=True,
    )
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    # Soft-delete: deleted_at is set when the user removes the notification.
    # Deleted notifications are excluded from the default queryset.
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    # Flexible JSON payload for future extensibility (e.g. object IDs).
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "deleted_at", "is_read"]),
            models.Index(fields=["recipient", "deleted_at", "created_at"]),
        ]

    def __str__(self):
        return f"[{self.notification_type}] {self.title} → {self.recipient}"

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])

    def mark_unread(self):
        if self.is_read:
            self.is_read = False
            self.read_at = None
            self.save(update_fields=["is_read", "read_at"])

    def soft_delete(self):
        if not self.is_deleted:
            self.deleted_at = timezone.now()
            self.save(update_fields=["deleted_at"])

    def get_metadata_json(self) -> str:
        return json.dumps(self.metadata)
