from django.contrib import admin

from .models import (
    CodingExamQuestion,
    CodingFile,
    CodingSubmission,
    CodingTestCase,
    Exam,
    ExamAnswer,
    ExamAttempt,
    ExamQuestion,
    ExamQuestionOption,
    ExamRoom,
    ExamRoomSession,
    ExamSupervisionConfig,
    FinalExamTicket,
    ProctoringLog,
    QuestionBank,
    StudentGroup,
    SupervisionIncident,
)

# Register your models here.

# --- Exam related admin registrations ---


class ExamQuestionOptionInline(admin.TabularInline):
    model = ExamQuestionOption
    extra = 4
    can_delete = True


class CodingTestCaseInline(admin.TabularInline):
    model = CodingTestCase
    extra = 2
    fields = ("visibility", "input_data", "expected_output", "point_value", "order")


class CodingFileInline(admin.TabularInline):
    model = CodingFile
    extra = 0
    readonly_fields = ("name", "language", "is_main", "updated_at")
    fields = ("name", "language", "is_main", "updated_at")
    can_delete = False


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "exam_type",
        "author",
        "is_active",
        "is_public",
        "fair_question_distribution_enabled",
        "ai_difficulty_balance_enabled",
        "created_at",
    )
    list_filter = (
        "exam_type",
        "is_active",
        "is_public",
        "fair_question_distribution_enabled",
        "ai_difficulty_balance_enabled",
        "author",
    )
    search_fields = ("title", "description", "author__username")


@admin.register(ExamQuestion)
class ExamQuestionAdmin(admin.ModelAdmin):
    list_display = ("exam", "order", "answer_mode", "difficulty", "difficulty_source", "short_text")
    list_filter = ("exam", "answer_mode", "difficulty", "difficulty_source")
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


@admin.register(CodingExamQuestion)
class CodingExamQuestionAdmin(admin.ModelAdmin):
    list_display = ("title", "language", "exam_title", "max_score", "enable_code_execution")
    list_filter = ("language", "enable_code_execution", "allow_file_creation", "allow_multiple_files")
    search_fields = ("title", "problem_statement", "question__exam__title")
    inlines = [CodingTestCaseInline]

    def exam_title(self, obj):
        return obj.question.exam.title

    exam_title.short_description = "Exam"


@admin.register(CodingSubmission)
class CodingSubmissionAdmin(admin.ModelAdmin):
    list_display = ("student", "exam", "question", "execution_status", "score", "is_final", "submitted_at")
    list_filter = ("execution_status", "is_final", "selected_language", "submitted_at")
    search_fields = ("student__username", "exam__title", "question__title", "submitted_code")
    readonly_fields = ("submitted_at", "updated_at")
    inlines = [CodingFileInline]


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


@admin.register(ExamSupervisionConfig)
class ExamSupervisionConfigAdmin(admin.ModelAdmin):
    list_display = ("exam", "enabled", "template", "violation_action", "recovery_policy", "updated_at")
    list_filter = ("enabled", "template", "violation_action", "recovery_policy")
    search_fields = ("exam__title",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(SupervisionIncident)
class SupervisionIncidentAdmin(admin.ModelAdmin):
    list_display = ("student_display", "exam_display", "event_type", "severity", "timestamp")
    list_filter = ("event_type", "severity", "timestamp")
    search_fields = ("student__username", "exam__title")
    readonly_fields = ("timestamp",)
    date_hierarchy = "timestamp"

    def student_display(self, obj):
        return obj.student.username

    student_display.short_description = "Tələbə"

    def exam_display(self, obj):
        return obj.exam.title

    exam_display.short_description = "İmtahan"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("student", "exam", "attempt")


# --- Final imtahan mərkəzi ---


@admin.register(ExamRoom)
class ExamRoomAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "organization", "building", "capacity", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code", "building")


@admin.register(ExamRoomSession)
class ExamRoomSessionAdmin(admin.ModelAdmin):
    list_display = ("room", "state", "scheduled_start", "scheduled_end", "invigilator")
    list_filter = ("state",)
    search_fields = ("room__name",)
    readonly_fields = ("started_at", "started_by", "ended_at", "ended_by", "start_connected_count")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("room", "invigilator")


@admin.register(FinalExamTicket)
class FinalExamTicketAdmin(admin.ModelAdmin):
    list_display = ("student", "exam", "session", "status", "seat_number", "language")
    list_filter = ("status", "language")
    search_fields = ("student__username", "exam__title")
    # PIN sahələri (hash/şifrə) admin formasında da göstərilmir.
    exclude = ("pin_hash", "pin_cipher")
    readonly_fields = ("pin_issued_at", "pin_expires_at", "pin_revoked_at", "pin_failed_attempts")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("student", "exam", "session", "session__room")
