from django.contrib import admin

from .models import InAppNotification, PushDevice, StudentOrganizationRequest


@admin.register(StudentOrganizationRequest)
class StudentOrganizationRequestAdmin(admin.ModelAdmin):
    list_display = ["user", "organization", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["user__username", "organization__name"]
    date_hierarchy = "created_at"


@admin.register(InAppNotification)
class InAppNotificationAdmin(admin.ModelAdmin):
    list_display = [
        "recipient",
        "title",
        "notification_type",
        "is_read",
        "deleted_at",
        "created_at",
    ]
    list_filter = ["notification_type", "is_read"]
    search_fields = ["recipient__username", "title", "message"]
    date_hierarchy = "created_at"
    readonly_fields = ["created_at", "read_at", "deleted_at"]


@admin.register(PushDevice)
class PushDeviceAdmin(admin.ModelAdmin):
    list_display = ["user", "platform", "app_version", "language", "is_active", "last_seen", "last_success_at"]
    list_filter = ["platform", "is_active", "deactivated_reason"]
    search_fields = ["user__username"]
    raw_id_fields = ["user"]
    # Token sirr deyil, amma admin siyahısında göstərməyə ehtiyac yoxdur — yalnız redaktə formunda.
    readonly_fields = ["created_at", "last_seen", "last_success_at", "deactivated_at"]
