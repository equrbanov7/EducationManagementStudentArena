from django.contrib import admin

from .models import Application, ApplicationKind, ApplicationUnit


@admin.register(ApplicationUnit)
class ApplicationUnitAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "organization", "resolve_by", "default_sla_days", "is_active")
    list_filter = ("organization", "resolve_by", "is_active")
    search_fields = ("code", "name")


@admin.register(ApplicationKind)
class ApplicationKindAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "organization", "target_unit", "sla_days", "is_active")
    list_filter = ("organization", "is_active")
    search_fields = ("code", "label")


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("number", "subject", "status", "current_unit", "created_by", "submitted_at")
    list_filter = ("organization", "status", "current_unit")
    search_fields = ("number", "subject")
    readonly_fields = ("number", "submitted_at", "resolved_at", "closed_at")
