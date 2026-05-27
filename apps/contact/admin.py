"""Admin registration for ContactMessage.

The admin acts primarily as a read-only inbox. Replies go through a
custom view registered on the ModelAdmin's ``get_urls`` so the standard
admin permission machinery still applies (login + staff + superuser
gate enforced by ``admin_views.reply_to_contact_message``).
"""

from __future__ import annotations

from django.contrib import admin
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .admin_views import reply_to_contact_message
from .models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "email",
        "subject",
        "reply_status_pill",
        "created_at",
    )
    list_filter = (
        "subject",
        "is_handled",
        "reply_delivery_status",
        "reply_from",
        "created_at",
    )
    search_fields = ("name", "email", "phone", "message", "reply_body")
    readonly_fields = (
        "name",
        "email",
        "phone",
        "subject",
        "message",
        "ip_address",
        "user_agent",
        "created_at",
        "reply_action",
        "reply_sent_by",
        "reply_delivery_status",
        "reply_delivery_error",
        "reply_sent_at",
    )
    fieldsets = (
        (_("Göndərən"), {"fields": ("name", "email", "phone")}),
        (_("Mesaj"), {"fields": ("subject", "message")}),
        (
            _("Cavab"),
            {
                "fields": (
                    "reply_action",
                    "reply_body",
                    "reply_from",
                    "reply_sent_by",
                    "reply_delivery_status",
                    "reply_delivery_error",
                    "reply_sent_at",
                ),
            },
        ),
        (_("Status"), {"fields": ("is_handled", "handled_at")}),
        (
            _("Metadata"),
            {
                "fields": ("ip_address", "user_agent", "created_at"),
                "classes": ("collapse",),
            },
        ),
    )
    actions = ("mark_as_handled",)

    # ---- Permissions -------------------------------------------------

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    # ---- Custom URL: reply view -------------------------------------

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:pk>/reply/",
                self.admin_site.admin_view(reply_to_contact_message),
                name="contact_contactmessage_reply",
            ),
        ]
        return custom + urls

    # ---- Display helpers --------------------------------------------

    @admin.display(description=_("Status"))
    def reply_status_pill(self, obj: ContactMessage) -> str:
        if obj.reply_delivery_status == ContactMessage.REPLY_DELIVERY_SENT:
            return format_html(
                '<span style="background:#dcfce7;color:#166534;padding:3px 10px;'
                'border-radius:999px;font-weight:600;font-size:12px;">{}</span>',
                _("✓ Cavablandı"),
            )
        if obj.reply_delivery_status == ContactMessage.REPLY_DELIVERY_PENDING:
            return format_html(
                '<span style="background:#dbeafe;color:#1d4ed8;padding:3px 10px;'
                'border-radius:999px;font-weight:600;font-size:12px;">{}</span>',
                _("Göndərilir"),
            )
        if obj.reply_delivery_status == ContactMessage.REPLY_DELIVERY_FAILED:
            return format_html(
                '<span style="background:#fee2e2;color:#991b1b;padding:3px 10px;'
                'border-radius:999px;font-weight:600;font-size:12px;">{}</span>',
                _("Göndərilmədi"),
            )
        if obj.reply_delivery_status == ContactMessage.REPLY_DELIVERY_RECORDED:
            return format_html(
                '<span style="background:#e2e8f0;color:#475569;padding:3px 10px;'
                'border-radius:999px;font-weight:600;font-size:12px;">{}</span>',
                _("Qeyd edildi"),
            )
        if obj.is_handled:
            return format_html(
                '<span style="background:#fef3c7;color:#92400e;padding:3px 10px;'
                'border-radius:999px;font-weight:600;font-size:12px;">{}</span>',
                _("Cavabsız bağlandı"),
            )
        return format_html(
            '<span style="background:#fee2e2;color:#991b1b;padding:3px 10px;'
            'border-radius:999px;font-weight:600;font-size:12px;">{}</span>',
            _("Yeni"),
        )

    @admin.display(description=_("Cavab"))
    def reply_action(self, obj: ContactMessage) -> str:
        if not obj.pk:
            return "-"
        url = reverse("admin:contact_contactmessage_reply", args=[obj.pk])
        if obj.reply_delivery_status == ContactMessage.REPLY_DELIVERY_SENT:
            return format_html(
                '<a href="{}" class="button" style="background:#0f766e;color:#fff;'
                'padding:8px 18px;border-radius:8px;text-decoration:none;font-weight:600;">'
                "{}</a>",
                url,
                _("✓ Cavablandı — yenidən göndər"),
            )
        if obj.reply_delivery_status == ContactMessage.REPLY_DELIVERY_FAILED:
            return format_html(
                '<a href="{}" class="button" style="background:#b91c1c;color:#fff;'
                'padding:8px 18px;border-radius:8px;text-decoration:none;font-weight:600;">'
                "{}</a>",
                url,
                _("Yenidən cəhd et"),
            )
        if obj.reply_delivery_status == ContactMessage.REPLY_DELIVERY_RECORDED:
            return format_html(
                '<a href="{}" class="button" style="background:#475569;color:#fff;'
                'padding:8px 18px;border-radius:8px;text-decoration:none;font-weight:600;">'
                "{}</a>",
                url,
                _("Göndərişi təsdiqlə"),
            )
        return format_html(
            '<a href="{}" class="button" style="background:linear-gradient(135deg,#1e40af,#0f766e);'
            "color:#fff;padding:10px 22px;border-radius:8px;text-decoration:none;font-weight:700;"
            'box-shadow:0 4px 12px rgba(15,118,110,0.3);">'
            "{}</a>",
            url,
            _("✉ Müştəriyə cavablandır"),
        )

    @admin.action(description=_("Cavablandırılmış kimi işarələ"))
    def mark_as_handled(self, request, queryset):
        from django.utils.timezone import now

        queryset.update(is_handled=True, handled_at=now())
