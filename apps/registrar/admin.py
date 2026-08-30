from django.contrib import admin

from core.admin_security import AcademicScoreReadOnlyAdminMixin

from .models import (
    AssessmentScheme,
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    FinalGrade,
    GroupElectiveChoice,
    Lesson,
    LessonMark,
    Program,
    ResitRecord,
    ScheduleSlot,
    StudentAcademicRecord,
    Subject,
)


class CurriculumSubjectInline(admin.TabularInline):
    model = CurriculumSubject
    extra = 0
    fields = ("subject", "semester_number", "is_elective", "elective_group", "required_choices", "order")
    autocomplete_fields = ("subject",)


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ("name", "official_code", "code", "degree_level", "ects_total", "organization", "is_active")
    list_filter = ("degree_level", "is_active")
    search_fields = ("code", "official_code", "name")


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "ects", "organization", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(Curriculum)
class CurriculumAdmin(admin.ModelAdmin):
    list_display = ("__str__", "program", "admission_year", "organization", "is_active")
    list_filter = ("admission_year", "is_active")
    search_fields = ("name", "program__official_code", "program__name")
    inlines = (CurriculumSubjectInline,)


@admin.register(StudentAcademicRecord)
class StudentAcademicRecordAdmin(admin.ModelAdmin):
    list_display = ("student", "program", "curriculum", "group", "admission_year", "is_active")
    list_filter = ("admission_year", "is_active")
    search_fields = ("student__username", "program__official_code", "program__name")
    autocomplete_fields = ("student", "program", "curriculum", "group")


@admin.register(CourseOffering)
class CourseOfferingAdmin(admin.ModelAdmin):
    list_display = ("subject", "period", "group", "instructor", "course", "organization", "is_active")
    list_filter = ("is_active",)
    search_fields = ("subject__code", "subject__name")
    autocomplete_fields = ("subject", "period", "group", "instructor", "course")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "offering", "kind", "status", "organization")
    list_filter = ("kind", "status")
    search_fields = ("student__username",)
    autocomplete_fields = ("student", "offering")


@admin.register(GroupElectiveChoice)
class GroupElectiveChoiceAdmin(admin.ModelAdmin):
    list_display = ("group", "period", "elective_group", "chosen_subject", "decided_by")
    search_fields = ("elective_group", "chosen_subject__code")
    autocomplete_fields = ("group", "period", "chosen_subject", "decided_by")


@admin.register(AssessmentScheme)
class AssessmentSchemeAdmin(admin.ModelAdmin):
    list_display = ("offering", "entry_score_max", "is_published", "organization")
    list_filter = ("is_published",)
    autocomplete_fields = ("offering",)


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("offering", "date", "kind", "topic", "hours", "organization")
    list_filter = ("kind",)
    search_fields = ("offering__subject__code", "topic")
    raw_id_fields = ("offering", "created_by")
    date_hierarchy = "date"


@admin.register(LessonMark)
class LessonMarkAdmin(AcademicScoreReadOnlyAdminMixin, admin.ModelAdmin):
    # Bal/davamiyyət yalnız jurnal servisləri (2 saat pəncərəsi) və ya sənədli
    # düzəliş (PDF + audit) ilə dəyişir — admin formasından yox.
    protected_score_fields = ("status", "score")
    list_display = ("lesson", "enrollment", "status", "score", "entered_by", "organization")
    list_filter = ("status",)
    search_fields = ("enrollment__student__username",)
    raw_id_fields = ("lesson", "enrollment", "entered_by")


@admin.register(ScheduleSlot)
class ScheduleSlotAdmin(admin.ModelAdmin):
    list_display = ("offering", "weekday", "start_time", "end_time", "room", "week_type", "organization")
    list_filter = ("weekday", "week_type")
    search_fields = ("offering__subject__code", "room")
    raw_id_fields = ("offering", "created_by")


@admin.register(FinalGrade)
class FinalGradeAdmin(AcademicScoreReadOnlyAdminMixin, admin.ModelAdmin):
    protected_score_fields = ("exam_score", "bonus", "is_published")
    list_display = ("enrollment", "exam_score", "is_published", "entered_by", "organization")
    list_filter = ("is_published",)
    search_fields = ("enrollment__student__username",)
    raw_id_fields = ("enrollment", "entered_by")


@admin.register(ResitRecord)
class ResitRecordAdmin(AcademicScoreReadOnlyAdminMixin, admin.ModelAdmin):
    protected_score_fields = ("resit_score", "status")
    list_display = ("enrollment", "reason", "status", "resit_score", "decided_by", "organization")
    list_filter = ("reason", "status")
    search_fields = ("enrollment__student__username",)
    raw_id_fields = ("enrollment", "decided_by")
