from django.contrib import admin
from .models import Lab, LabBlock, LabQuestion, LabAssignment, LabSubmission


class LabBlockInline(admin.TabularInline):
    model = LabBlock
    extra = 0


class LabQuestionInline(admin.TabularInline):
    model = LabQuestion
    extra = 0


@admin.register(Lab)
class LabAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'status', 'start_datetime', 'end_datetime', 'total_questions']
    list_filter = ['status', 'course']
    search_fields = ['title', 'description']
    inlines = [LabBlockInline]


@admin.register(LabBlock)
class LabBlockAdmin(admin.ModelAdmin):
    list_display = ['title', 'lab', 'order', 'questions_to_pick', 'question_count']
    list_filter = ['lab']
    inlines = [LabQuestionInline]


@admin.register(LabQuestion)
class LabQuestionAdmin(admin.ModelAdmin):
    list_display = ['question_number', 'block', 'question_text', 'points']
    list_filter = ['block__lab']
    search_fields = ['question_text']


@admin.register(LabAssignment)
class LabAssignmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'lab', 'assigned_at']
    list_filter = ['lab']


@admin.register(LabSubmission)
class LabSubmissionAdmin(admin.ModelAdmin):
    list_display = ['assignment', 'status', 'score', 'submitted_at']
    list_filter = ['status', 'assignment__lab']