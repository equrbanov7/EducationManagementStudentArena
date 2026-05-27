"""Contact form persistence model.

Every submission is stored so the owner has an audit trail even if email
delivery fails. The model is intentionally minimal and lives outside the
multi-tenant scope (no organization FK) because it represents inbound
inquiries from the public web — including users who are not yet part of
any organization.

Replies are tracked on the same row so we have a complete audit trail:
who replied, when, from which mailbox, and the body of the reply itself.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class ContactMessage(models.Model):
    SUBJECT_CHOICES = [
        ("general", _("Ümumi sual")),
        ("sales", _("Satış / Demo")),
        ("support", _("Texniki dəstək")),
        ("partnership", _("Əməkdaşlıq")),
        ("feedback", _("Rəy və təklif")),
        ("other", _("Digər")),
    ]

    REPLY_FROM_CHOICES = [
        ("info", _("info@emsarena.com")),
        ("support", _("support@emsarena.com")),
    ]

    REPLY_DELIVERY_PENDING = "pending"
    REPLY_DELIVERY_SENT = "sent"
    REPLY_DELIVERY_FAILED = "failed"
    REPLY_DELIVERY_RECORDED = "recorded"
    REPLY_DELIVERY_STATUS_CHOICES = [
        (REPLY_DELIVERY_PENDING, _("Göndərilir")),
        (REPLY_DELIVERY_SENT, _("Göndərildi")),
        (REPLY_DELIVERY_FAILED, _("Göndərilmədi")),
        (REPLY_DELIVERY_RECORDED, _("Qeyd edildi")),
    ]

    name = models.CharField(_("Ad Soyad"), max_length=120)
    email = models.EmailField(_("Email"), max_length=254)
    phone = models.CharField(_("Telefon"), max_length=32, blank=True)
    subject = models.CharField(
        _("Mövzu"),
        max_length=32,
        choices=SUBJECT_CHOICES,
        default="general",
    )
    message = models.TextField(_("Mesaj"), max_length=5000)

    # Metadata — never displayed to the public, only to staff.
    ip_address = models.GenericIPAddressField(_("IP ünvan"), null=True, blank=True)
    user_agent = models.CharField(_("User-Agent"), max_length=512, blank=True)
    is_handled = models.BooleanField(_("Cavablandırılıb"), default=False)

    created_at = models.DateTimeField(_("Göndərilmə tarixi"), auto_now_add=True)
    handled_at = models.DateTimeField(_("Cavab tarixi"), null=True, blank=True)

    # ---- Reply tracking ----
    reply_body = models.TextField(_("Cavab mətni"), blank=True, max_length=10000)
    reply_from = models.CharField(
        _("Hansı maildən"),
        max_length=16,
        choices=REPLY_FROM_CHOICES,
        blank=True,
    )
    reply_delivery_status = models.CharField(
        _("Cavab email statusu"),
        max_length=16,
        choices=REPLY_DELIVERY_STATUS_CHOICES,
        blank=True,
    )
    reply_delivery_error = models.CharField(
        _("Cavab email xətası"),
        max_length=500,
        blank=True,
    )
    reply_sent_at = models.DateTimeField(_("Cavab göndərilmə tarixi"), null=True, blank=True)
    reply_sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_replies",
        verbose_name=_("Cavab verən admin"),
    )

    class Meta:
        verbose_name = _("Əlaqə mesajı")
        verbose_name_plural = _("Əlaqə mesajları")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["is_handled", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} <{self.email}> — {self.get_subject_display()}"

    @property
    def has_been_replied(self) -> bool:
        return bool(self.reply_sent_at)

    @property
    def reply_delivery_failed(self) -> bool:
        return self.reply_delivery_status == self.REPLY_DELIVERY_FAILED

    @property
    def reply_delivery_pending(self) -> bool:
        return self.reply_delivery_status == self.REPLY_DELIVERY_PENDING
