import json

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class StudentOrganizationRequestStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    APPROVED = "approved", _("Approved")
    REJECTED = "rejected", _("Rejected")
    CANCELLED = "cancelled", _("Cancelled")
    AUTO_CLOSED = "auto_closed", _("Auto Closed")


class MembershipRequestRoleType(models.TextChoices):
    """Discriminates student / teacher / staff join requests."""

    STUDENT = "student", _("Student")
    TEACHER = "teacher", _("Teacher")
    STAFF = "staff", _("Staff")


class StudentOrganizationRequest(models.Model):
    """Unified membership-join request for students, teachers, and staff.

    The ``role_type`` field discriminates between the three kinds of join
    requests.  Pre-existing rows (created before the field was added) default
    to ``STUDENT`` so the existing student approval flow is unaffected.
    """

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
    role_type = models.CharField(
        max_length=10,
        choices=MembershipRequestRoleType.choices,
        default=MembershipRequestRoleType.STUDENT,
        db_index=True,
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
            models.Index(fields=["organization", "role_type", "status"]),
        ]

    def __str__(self):
        return f"{self.user} -> {self.organization} [{self.role_type}] ({self.status})"


# ────────────────────────────────────────────────────────────────────────────
# In-App Notification System
# ────────────────────────────────────────────────────────────────────────────


class NotificationType(models.TextChoices):
    ASSIGNMENT = "assignment", _("Assignment")
    EXAM = "exam", _("Exam")
    GRADE = "grade", _("Grade / Feedback")
    SYSTEM = "system", _("System / Admin")
    COURSE = "course", _("Course")
    LIVE_EXAM = "live_exam", _("Live Exam / Session")
    APPROVAL = "approval", _("Membership / Approval Request")
    APPLICATION = "application", _("Application / Request")


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
    # Tenant scope. A real, indexed FK — not a JSON key — so the PostgreSQL
    # RLS policy can enforce tenant isolation reliably (fail-closed).
    # NULL means a deliberately GLOBAL notification (e.g. platform/system or
    # blog notifications that belong to no single organization). Such rows are
    # still protected by the recipient_id check in the RLS policy.
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="in_app_notifications",
        null=True,
        blank=True,
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
            # Backs the RLS policy's tenant predicate.
            models.Index(fields=["organization", "recipient"], name="notif_org_recipient_idx"),
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
