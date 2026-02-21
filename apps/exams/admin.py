from django.contrib import admin

from .models import (
    Exam,
    ExamAnswer,
    ExamAttempt,
    ExamQuestion,
    ExamQuestionOption,
    ProctoringLog,
    QuestionBank,
    StudentGroup,
)

# Register your models here.

# --- Exam related admin registrations ---


class ExamQuestionOptionInline(admin.TabularInline):
    model = ExamQuestionOption
    extra = 4
    can_delete = True


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "exam_type",
        "author",
        "is_active",
        "is_public",
        "created_at",
    )
    list_filter = ("exam_type", "is_active", "is_public", "author")
    search_fields = ("title", "description", "author__username")


@admin.register(ExamQuestion)
class ExamQuestionAdmin(admin.ModelAdmin):
    list_display = ("exam", "order", "answer_mode", "short_text")
    list_filter = ("exam", "answer_mode")
    search_fields = ("text",)
    inlines = [ExamQuestionOptionInline]

    def short_text(self, obj):
        return obj.text[:60]

    short_text.short_description = "Sual"


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "exam",
        "attempt_number",
        "status",
        "correct_count",
        "wrong_count",
        "duration_seconds",
    )
    list_filter = ("exam", "status")
    search_fields = ("user__username", "exam__title")


@admin.register(ExamAnswer)
class ExamAnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "is_correct", "updated_at")
    list_filter = ("question__exam", "is_correct")
    search_fields = ("attempt__user__username", "question__text")


@admin.register(StudentGroup)
class StudentGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "teacher", "created_at")
    list_filter = ("organization", "teacher")
    search_fields = ("name", "organization__name", "teacher__username", "students__username", "teachers__username")
    filter_horizontal = ("students", "teachers")


@admin.register(QuestionBank)
class QuestionBankAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "subject",
        "organization_type",
        "created_by",
        "is_shared",
        "is_active",
        "question_count",
        "created_at",
    )
    list_filter = ("organization_type", "is_shared", "is_active", "created_at")
    search_fields = ("name", "subject", "description", "created_by__username")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "Əsas Məlumat",
            {"fields": ("name", "subject", "description", "organization_type")},
        ),
        (
            "Parametrlər",
            {"fields": ("is_shared", "is_active", "created_by")},
        ),
        (
            "Vaxt Məlumatı",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def question_count(self, obj):
        return obj.question_count

    question_count.short_description = "Sual Sayı"


@admin.register(ProctoringLog)
class ProctoringLogAdmin(admin.ModelAdmin):
    list_display = ("exam_attempt", "event_type", "timestamp", "user_display")
    list_filter = ("event_type", "timestamp")
    search_fields = ("exam_attempt__user__username", "exam_attempt__exam__title")
    readonly_fields = ("timestamp",)
    date_hierarchy = "timestamp"

    fieldsets = (
        (
            "Hadisə Məlumatı",
            {"fields": ("exam_attempt", "event_type", "timestamp")},
        ),
        (
            "Təfərrüatlar",
            {"fields": ("details",)},
        ),
    )

    def user_display(self, obj):
        return obj.exam_attempt.user.username

    user_display.short_description = "İstifadəçi"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("exam_attempt__user", "exam_attempt__exam")
