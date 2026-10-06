"""Django admin — yalnız oxu/diaqnostika üçün (idarə kabinetdədir: ``/elanlar/idare/``)."""

from django.contrib import admin

from .models import Announcement, AnnouncementAttachment, AnnouncementReceipt


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "status", "category", "priority", "show_as_popup", "publish_at")
    list_filter = ("status", "category", "show_as_popup")
    search_fields = ("title", "summary")
    raw_id_fields = ("organization", "created_by", "updated_by", "apply_kind", "apply_unit")


@admin.register(AnnouncementAttachment)
class AnnouncementAttachmentAdmin(admin.ModelAdmin):
    list_display = ("original_name", "announcement", "size", "created_at")
    raw_id_fields = ("organization", "announcement", "uploaded_by")


@admin.register(AnnouncementReceipt)
class AnnouncementReceiptAdmin(admin.ModelAdmin):
    list_display = ("announcement", "user", "popup_seen_at", "read_at", "applied_at", "application_number")
    raw_id_fields = ("organization", "announcement", "user")
