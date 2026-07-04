from django.contrib import admin

from .models import (
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    GroupElectiveChoice,
    Program,
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
    list_display = ("code", "name", "degree_level", "ects_total", "organization", "is_active")
    list_filter = ("degree_level", "is_active")
    search_fields = ("code", "name")


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "ects", "organization", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(Curriculum)
class CurriculumAdmin(admin.ModelAdmin):
    list_display = ("__str__", "program", "admission_year", "organization", "is_active")
    list_filter = ("admission_year", "is_active")
    search_fields = ("name", "program__code", "program__name")
    inlines = (CurriculumSubjectInline,)


@admin.register(StudentAcademicRecord)
class StudentAcademicRecordAdmin(admin.ModelAdmin):
    list_display = ("student", "program", "curriculum", "group", "admission_year", "is_active")
    list_filter = ("admission_year", "is_active")
    search_fields = ("student__username", "program__code")
    autocomplete_fields = ("student", "program", "curriculum", "group")


@admin.register(CourseOffering)
class CourseOfferingAdmin(admin.ModelAdmin):
    list_display = ("subject", "period", "group", "course", "organization", "is_active")
    list_filter = ("is_active",)
    search_fields = ("subject__code", "subject__name")
    autocomplete_fields = ("subject", "period", "group", "course")


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
