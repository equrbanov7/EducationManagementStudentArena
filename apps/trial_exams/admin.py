"""Admin registration for TrialExamRequest.

Acts as a review inbox: staff see the submission + the uploaded PDF, then
send the "questions added" confirmation through the custom reply view
(registered on ``get_urls``). Replies flip the request to ``added``.
"""

from __future__ import annotations

from django.contrib import admin
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .admin_views import reply_to_trial_request
from .models import TrialExamRequest


@admin.register(TrialExamRequest)
class TrialExamRequestAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "email",
        "subject_name",
        "status_pill",
        "created_at",
    )
    list_filter = (
        "status",
        "is_handled",
        "reply_delivery_status",
        "created_at",
    )
    search_fields = ("full_name", "email", "subject_name", "note", "reply_body")
    readonly_fields = (
        "full_name",
        "email",
        "subject_name",
        "note",
        "file_link",
        "original_filename",
        "user",
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
        (_("Göndərən"), {"fields": ("full_name", "email", "user")}),
        (_("Sınaq imtahanı"), {"fields": ("subject_name", "note", "file_link", "original_filename")}),
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
        (_("Status"), {"fields": ("status", "is_handled", "handled_at")}),
        (
            _("Metadata"),
            {"fields": ("ip_address", "user_agent", "created_at"), "classes": ("collapse",)},
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
                self.admin_site.admin_view(reply_to_trial_request),
                name="trial_exams_trialexamrequest_reply",
            ),
        ]
        return custom + urls

    # ---- Display helpers --------------------------------------------

    @admin.display(description=_("Suallar (PDF)"))
    def file_link(self, obj: TrialExamRequest) -> str:
        if not obj.questions_file:
            return "-"
        label = obj.original_filename or _("Faylı aç")
        return format_html(
            '<a href="{}" target="_blank" rel="noopener" class="button" '
            'style="background:#0f766e;color:#fff;padding:6px 14px;border-radius:8px;'
            'text-decoration:none;font-weight:600;">⬇ {}</a>',
            obj.questions_file.url,
            label,
        )

    @admin.display(description=_("Status"))
    def status_pill(self, obj: TrialExamRequest) -> str:
        palette = {
            TrialExamRequest.STATUS_ADDED: ("#dcfce7", "#166534", _("✓ Əlavə olundu")),
            TrialExamRequest.STATUS_PROCESSING: ("#dbeafe", "#1d4ed8", _("Hazırlanır")),
            TrialExamRequest.STATUS_REJECTED: ("#fee2e2", "#991b1b", _("Rədd edildi")),
            TrialExamRequest.STATUS_PENDING: ("#fef3c7", "#92400e", _("Gözləyir")),
        }
        bg, fg, label = palette.get(obj.status, palette[TrialExamRequest.STATUS_PENDING])
        return format_html(
            '<span style="background:{};color:{};padding:3px 10px;border-radius:999px;'
            'font-weight:600;font-size:12px;">{}</span>',
            bg,
            fg,
            label,
        )

    @admin.display(description=_("Cavab"))
    def reply_action(self, obj: TrialExamRequest) -> str:
        if not obj.pk:
            return "-"
        url = reverse("admin:trial_exams_trialexamrequest_reply", args=[obj.pk])
        if obj.reply_delivery_status == TrialExamRequest.REPLY_DELIVERY_SENT:
            return format_html(
                '<a href="{}" class="button" style="background:#0f766e;color:#fff;'
                'padding:8px 18px;border-radius:8px;text-decoration:none;font-weight:600;">{}</a>',
                url,
                _("✓ Göndərildi — yenidən göndər"),
            )
        if obj.reply_delivery_status == TrialExamRequest.REPLY_DELIVERY_FAILED:
            return format_html(
                '<a href="{}" class="button" style="background:#b91c1c;color:#fff;'
                'padding:8px 18px;border-radius:8px;text-decoration:none;font-weight:600;">{}</a>',
                url,
                _("Yenidən cəhd et"),
            )
        return format_html(
            '<a href="{}" class="button" style="background:linear-gradient(135deg,#1e40af,#0f766e);'
            "color:#fff;padding:10px 22px;border-radius:8px;text-decoration:none;font-weight:700;"
            'box-shadow:0 4px 12px rgba(15,118,110,0.3);">{}</a>',
            url,
            _("✉ Suallar əlavə olundu — təsdiq göndər"),
        )

    @admin.action(description=_("Cavablandırılmış kimi işarələ"))
    def mark_as_handled(self, request, queryset):
        from django.utils.timezone import now

        queryset.update(is_handled=True, handled_at=now())
