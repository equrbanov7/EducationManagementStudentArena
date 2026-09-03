"""
Admin configuration for accounts app.
"""

from django.contrib import admin

from apps.accounts.models import EmailOTP, UserProfile


class SuperadminBypassAdminMixin:
    """Allow platform superadmins to manage objects from Django admin."""

    @staticmethod
    def _is_platform_superadmin(user):
        return bool(user and user.is_authenticated and (user.is_superuser or getattr(user, "is_superadmin", False)))

    def has_module_permission(self, request):
        if self._is_platform_superadmin(request.user):
            return True
        return super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        if self._is_platform_superadmin(request.user):
            return True
        return super().has_view_permission(request, obj=obj)

    def has_add_permission(self, request):
        if self._is_platform_superadmin(request.user):
            return True
        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        if self._is_platform_superadmin(request.user):
            return True
        return super().has_change_permission(request, obj=obj)

    def has_delete_permission(self, request, obj=None):
        if self._is_platform_superadmin(request.user):
            return True
        return super().has_delete_permission(request, obj=obj)


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    """Admin interface for EmailOTP model."""

    list_display = ["email", "purpose", "user", "created_at", "expires_at", "is_verified", "attempts_count", "is_used"]
    list_filter = ["purpose", "is_verified", "is_used", "created_at"]
    search_fields = ["email", "user__username", "user__email"]
    readonly_fields = ["created_at", "expires_at", "code", "otp_hash"]


@admin.register(UserProfile)
class UserProfileAdmin(SuperadminBypassAdminMixin, admin.ModelAdmin):
    """
    Admin interface for UserProfile model.
    """

    list_display = [
        "user",
        "role",
        "organization",
        "organization_type",
        "student_university_name",
        "student_school_identifier",
        "phone",
        "location",
        "created_at",
        "fin",
    ]
    list_filter = ["role", "organization_type", "organization", "created_at"]
    list_editable = [
        "role",
        "organization",
        "organization_type",
        "student_university_name",
        "student_school_identifier",
    ]
    list_select_related = ["user", "organization"]
    search_fields = [
        "user__username",
        "user__email",
        "phone",
        "location",
        "supervisor_code",
        "fin",
    ]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (
            "User Information",
            {
                "fields": (
                    "user",
                    "role",
                    "organization",
                    "organization_type",
                    "country",
                    "student_university_name",
                    "student_school_identifier",
                    "fin",
                    "avatar",
                ),
            },
        ),
        (
            "Contact Information",
            {
                "fields": ("phone", "location"),
            },
        ),
        (
            "Profile Details",
            {
                "fields": ("bio", "supervisor_code"),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
            },
        ),
    )
