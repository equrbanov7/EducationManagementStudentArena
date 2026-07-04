from django.contrib import admin

from .models import Curriculum, CurriculumSubject, Program, Subject


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
