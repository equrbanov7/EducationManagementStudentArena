"""İstifadəçinin özü idarə etdiyi akademik fəaliyyət qeydləri.

``models.py`` modul ölçü budcəsindən (SOFT_CAP=600) keçdiyi üçün ayrıldı —
MƏZMUN DƏYİŞMƏYİB. ``models`` faylı bu sinfi yenidən ixrac edir, ona görə
``from apps.accounts.models import AcademicProfileItem`` işləməyə davam edir.
"""

import posixpath
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

#: Qoşma faylların saxlanma prefiksi — ``core.media_views`` üçün MƏXFİ yoldur
#: (ağ siyahıda deyil); icazə siyasəti ``AccountsConfig.ready()``-də qeyd olunur
#: (bax services/academic_attachments.check_attachment_media_access).
ACADEMIC_ATTACHMENT_PREFIX = "academic_attachments/"


def academic_attachment_upload_to(instance, filename):
    """``academic_attachments/<user_id>/<uuid>.<ext>`` — orijinal ad SAXLANMIR.

    Uzantı servis qatında ağ siyahıdan keçib (pdf/jpg/jpeg/png/webp); burada
    yalnız kiçik hərfə salınır. Orijinal ad göstəriş üçün ``attachment_name``-dədir.
    """
    extension = posixpath.splitext(str(filename or ""))[1].lower()[:8]
    return f"{ACADEMIC_ATTACHMENT_PREFIX}{instance.user_id}/{uuid4().hex}{extension}"


class AcademicProfileItem(models.Model):
    """İstifadəçinin özü idarə etdiyi akademik fəaliyyət qeydi.

    Müəllim profilində məqalə/konfrans materialı/sertifikat/tədris etdiyi fənn
    kimi bəndlər; tələbə və digər rollar da öz nailiyyətlərini (sertifikat,
    məqalə və s.) əlavə edə bilir. Yalnız sahibinə redaktə icazəsi var —
    yoxlama servis qatındadır (apps.accounts.services.academic_profile).
    """

    class Kind(models.TextChoices):
        # Sıra = görünüş sırası (akademik CV məntiqi: tədris → təhsil/təcrübə →
        # nəşrlər → layihə/patent → sertifikat/mükafat). 2026-10-01: altı yeni növ.
        SUBJECT = "subject", pgettext_lazy("accounts.academic_item_kind", "Tədris etdiyi fənn")
        EDUCATION = "education", pgettext_lazy("accounts.academic_item_kind", "Təhsil / dərəcə")
        EXPERIENCE = "experience", pgettext_lazy("accounts.academic_item_kind", "Peşəkar təcrübə")
        PUBLICATION = "publication", pgettext_lazy("accounts.academic_item_kind", "Məqalə")
        BOOK = "book", pgettext_lazy("accounts.academic_item_kind", "Kitab / dərslik")
        CONFERENCE = "conference", pgettext_lazy("accounts.academic_item_kind", "Konfrans materialı")
        PROJECT = "project", pgettext_lazy("accounts.academic_item_kind", "Elmi layihə / qrant")
        PATENT = "patent", pgettext_lazy("accounts.academic_item_kind", "Patent")
        CERTIFICATE = "certificate", pgettext_lazy("accounts.academic_item_kind", "Sertifikat")
        AWARD = "award", pgettext_lazy("accounts.academic_item_kind", "Mükafat / təltif")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="academic_items",
        verbose_name="İstifadəçi",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, verbose_name="Növ")
    title = models.CharField(max_length=200, verbose_name="Başlıq")
    detail = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Ətraflı",
        help_text="Jurnal/konfrans adı, verən qurum, kafedra və s.",
    )
    year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="İl",
    )
    link = models.URLField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Keçid",
        help_text="DOI / sertifikat / nəşr keçidi (http-https)",
    )
    # ── Qoşma (2026-10-01) — hər qeyddə ən çox BİR fayl (PDF və ya şəkil). ──
    # Yoxlama/saxlama/silmə: services/academic_attachments.py. Şəkil üçün
    # kiçik önizləmə (thumb) ayrıca saxlanılır ki, siyahı tam faylı yükləməsin.
    attachment = models.FileField(
        upload_to=academic_attachment_upload_to,
        max_length=255,
        blank=True,
        default="",
        verbose_name="Qoşma fayl",
    )
    attachment_thumb = models.FileField(
        upload_to=academic_attachment_upload_to,
        max_length=255,
        blank=True,
        default="",
        verbose_name="Qoşma önizləməsi",
    )
    attachment_name = models.CharField(max_length=160, blank=True, default="", verbose_name="Qoşmanın adı")
    attachment_size = models.PositiveIntegerField(null=True, blank=True, verbose_name="Qoşmanın ölçüsü (bayt)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Akademik fəaliyyət qeydi"
        verbose_name_plural = "Akademik fəaliyyət qeydləri"
        ordering = ["kind", "-year", "-id"]
        indexes = [models.Index(fields=["user", "kind"])]

    def __str__(self):
        return f"{self.user_id} · {self.get_kind_display()} · {self.title[:40]}"

    @property
    def attachment_is_pdf(self):
        return str(self.attachment.name or "").lower().endswith(".pdf")

    @property
    def attachment_is_image(self):
        return bool(self.attachment) and not self.attachment_is_pdf

    @property
    def attachment_url(self):
        """RBAC-dan keçən ``protected_media`` URL-i (boşdursa "")."""
        if not self.attachment:
            return ""
        from core.media_urls import protected_media_url

        return protected_media_url(self.attachment)

    @property
    def attachment_thumb_url(self):
        if not self.attachment_thumb:
            return ""
        from core.media_urls import protected_media_url

        return protected_media_url(self.attachment_thumb)


# Separate module keeps this already-large model module below the size budget.
