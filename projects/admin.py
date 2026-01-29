from django.contrib import admin
from .models import Project, ProjectSubmission


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'deadline', 'max_attempts', 'status', 'created_at']
    list_filter = ['status', 'course', 'created_at']
    search_fields = ['title', 'description', 'course__title']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Əsas Məlumat', {
            'fields': ('course', 'title', 'description')
        }),
        ('Parametrlər', {
            'fields': ('start_date', 'deadline', 'max_attempts', 'max_score', 'status')
        }),
        ('Tələbələr', {
            'fields': ('assigned_students',),
            'classes': ('collapse',)
        }),
    )
    
    filter_horizontal = ['assigned_students']


@admin.register(ProjectSubmission)
class ProjectSubmissionAdmin(admin.ModelAdmin):
    list_display = ['project', 'student', 'submitted_at', 'status', 'grade', 'graded_by']
    list_filter = ['status', 'submitted_at', 'graded_at']
    search_fields = ['project__title', 'student__username', 'student__first_name']
    date_hierarchy = 'submitted_at'
    readonly_fields = ['submitted_at', 'graded_at']
    
    fieldsets = (
        ('Cavab Məlumatı', {
            'fields': ('project', 'student', 'content', 'file', 'submitted_at')
        }),
        ('Qiymətləndirmə', {
            'fields': ('status', 'grade', 'feedback', 'graded_by', 'graded_at')
        }),
    )