from django.conf import settings
from django.db import models


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
