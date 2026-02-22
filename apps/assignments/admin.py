from django.contrib import admin
from django.utils.translation import pgettext_lazy

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
            pgettext_lazy("assignment.admin.fieldset", "basic_information"),
            {"fields": ("course", "type", "title", "description", "instructions")},
        ),
        (pgettext_lazy("assignment.admin.fieldset", "grading"), {"fields": ("max_score", "weight")}),
        (
            pgettext_lazy("assignment.admin.fieldset", "timing"),
            {
                "fields": (
                    "start_date",
                    "due_date",
                    "allow_late",
                    "late_penalty_per_day",
                )
            },
        ),
        (pgettext_lazy("assignment.admin.fieldset", "settings"), {"fields": ("max_attempts", "status", "created_by")}),
        (pgettext_lazy("assignment.admin.fieldset", "students"), {"fields": ("assigned_students",), "classes": ("collapse",)}),
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
            pgettext_lazy("assignment.submission.admin.fieldset", "submission_information"),
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
            pgettext_lazy("assignment.submission.admin.fieldset", "late_information"),
            {"fields": ("is_late", "late_days")},
        ),
        (
            pgettext_lazy("assignment.submission.admin.fieldset", "grading"),
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
            pgettext_lazy("assignment.notification.admin.fieldset", "notification_information"),
            {"fields": ("user", "type", "title", "message", "link")},
        ),
        (
            pgettext_lazy("assignment.notification.admin.fieldset", "status"),
            {"fields": ("is_read", "created_at")},
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user")
