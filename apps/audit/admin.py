"""
Admin configuration for the audit app.
"""

from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin interface for AuditLog model."""

    list_display = [
        "created_at",
        "user",
        "action",
        "resource_display",
        "organization",
        "ip_address",
    ]
    list_filter = ["action", "created_at", "organization"]
    search_fields = [
        "user__username",
        "user__email",
        "resource_type",
        "resource_id",
        "resource_repr",
        "ip_address",
    ]
    readonly_fields = [
        "id",
        "user",
        "organization",
        "action",
        "content_type",
        "object_id",
        "resource_type",
        "resource_id",
        "resource_repr",
        "old_values",
        "new_values",
        "changes",
        "reason",
        "ip_address",
        "user_agent",
        "request_id",
        "created_at",
    ]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    def resource_display(self, obj):
        """Display resource information."""
        return obj.get_resource_display()

    resource_display.short_description = "Resource"

    def has_add_permission(self, request):
        """Disable manual creation of audit logs."""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable editing of audit logs."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Only superusers can delete audit logs."""
        return request.user.is_superuser
