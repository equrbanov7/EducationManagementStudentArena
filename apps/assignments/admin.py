from django.contrib import admin

from .models import Assignment, Notification, Submission


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "course",
        "due_date",
        "max_attempts",
        "status",
        "created_at",
    ]
    list_filter = ["status", "course", "created_at"]
    search_fields = ["title", "description", "course__title"]
    date_hierarchy = "created_at"

    fieldsets = (
        (
            "Əsas Məlumat",
            {"fields": ("course", "type", "title", "description", "instructions")},
        ),
        ("Qiymətləndirmə", {"fields": ("max_score", "weight")}),
        (
            "Vaxt",
            {
                "fields": (
                    "start_date",
                    "due_date",
                    "allow_late",
                    "late_penalty_per_day",
                )
            },
        ),
        ("Parametrlər", {"fields": ("max_attempts", "status", "created_by")}),
        ("Tələbələr", {"fields": ("assigned_students",), "classes": ("collapse",)}),
    )

    filter_horizontal = ["assigned_students"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("course")


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = [
        "assignment",
        "user",
        "attempt_number",
        "submitted_at",
        "is_late",
        "status",
        "grade",
        "graded_by",
    ]
    list_filter = ["status", "is_late", "submitted_at", "graded_at"]
    search_fields = [
        "assignment__title",
        "user__username",
        "user__first_name",
        "user__last_name",
    ]
    date_hierarchy = "submitted_at"
    readonly_fields = ["submitted_at", "graded_at", "is_late", "late_days"]

    fieldsets = (
        (
            "Cavab Məlumatı",
            {
                "fields": (
                    "assignment",
                    "user",
                    "attempt_number",
                    "content",
                    "files",
                    "submitted_at",
                )
            },
        ),
        (
            "Gecikmiş Məlumat",
            {"fields": ("is_late", "late_days")},
        ),
        (
            "Qiymətləndirmə",
            {"fields": ("status", "grade", "feedback", "graded_by", "graded_at")},
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("assignment", "user", "graded_by")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["title", "user", "type", "is_read", "created_at"]
    list_filter = ["type", "is_read", "created_at"]
    search_fields = ["title", "message", "user__username"]
    date_hierarchy = "created_at"
    readonly_fields = ["created_at"]

    fieldsets = (
        (
            "Bildiriş Məlumatı",
            {"fields": ("user", "type", "title", "message", "link")},
        ),
        (
            "Status",
            {"fields": ("is_read", "created_at")},
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user")
