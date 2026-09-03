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
    list_filter = ["action", "organization", "created_at"]
    search_fields = [
        "user__username",
        "user__email",
        "object_id",
        "reason",
        "request_id",
        "ip_address",
    ]
    readonly_fields = [
        "id",
        "user",
        "organization",
        "action",
        "content_type",
        "object_id",
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
        """Audit jurnalı APPEND-ONLY-dir — HEÇ KİM, superuser də silə bilməz.

        2026-09-02 audit (P1-3): burada ``request.user.is_superuser``
        qaytarılırdı, yəni ələ keçirilmiş və ya bədniyyət superadmin 22 301
        sətirlik izi — o cümlədən ÖZ əməllərinin qeydini — admin UI-dan silə
        bilərdi.  PostgreSQL tərəfdə ``audit_log_no_delete`` triggeri
        (``apps/organizations/migrations/0019_audit_log_append_only.py``)
        onsuz da rədd edir; bu, UI-nin həmin düyməni ÜMUMİYYƏTLƏ göstərməməsini
        təmin edir.  Saxlama müddəti (retention) admin düyməsi ilə deyil,
        tarixli/xarici arxivləmə işi ilə idarə olunmalıdır.
        """
        return False

    def get_actions(self, request):
        """Toplu ``delete_selected`` əməlini siyahıdan tamamilə çıxarır."""
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
