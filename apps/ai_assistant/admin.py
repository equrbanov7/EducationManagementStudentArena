from django.contrib import admin

from .models import AIAssistantLog


@admin.register(AIAssistantLog)
class AIAssistantLogAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role_name", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("user__username", "user__email", "prompt")
    readonly_fields = (
        "id",
        "user",
        "organization",
        "role_name",
        "prompt",
        "response_summary",
        "status",
        "block_reason",
        "prompt_tokens",
        "response_tokens",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
