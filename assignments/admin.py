from django.contrib import admin
from .models import Assignment, AssignmentSubmission


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'deadline', 'max_attempts', 'status', 'created_at']
    list_filter = ['status', 'course', 'created_at']
    search_fields = ['title', 'description', 'course__title']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Əsas Məlumat', {
            'fields': ('course', 'title', 'description')
        }),
        ('Parametrlər', {
            'fields': ('deadline', 'max_attempts', 'status')
        }),
        ('Tələbələr', {
            'fields': ('assigned_students',),
            'classes': ('collapse',)
        }),
    )
    
    filter_horizontal = ['assigned_students']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('course')


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ['assignment', 'student', 'submitted_at', 'status', 'grade', 'graded_by']
    list_filter = ['status', 'submitted_at', 'graded_at']
    search_fields = ['assignment__title', 'student__username', 'student__first_name', 'student__last_name']
    date_hierarchy = 'submitted_at'
    readonly_fields = ['submitted_at', 'graded_at']
    
    fieldsets = (
        ('Cavab Məlumatı', {
            'fields': ('assignment', 'student', 'content', 'file', 'submitted_at')
        }),
        ('Qiymətləndirmə', {
            'fields': ('status', 'grade', 'feedback', 'graded_by', 'graded_at')
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('assignment', 'student', 'graded_by')