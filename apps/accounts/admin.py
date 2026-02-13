"""
Admin configuration for accounts app.
"""

from django.contrib import admin

from apps.accounts.models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """
    Admin interface for UserProfile model.
    """

    list_display = ["user", "organization_type", "phone", "location", "created_at"]
    list_filter = ["organization_type", "created_at"]
    search_fields = ["user__username", "user__email", "phone", "location", "supervisor_code"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (
            "User Information",
            {
                "fields": ("user", "organization_type", "avatar"),
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