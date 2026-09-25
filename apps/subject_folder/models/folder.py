"""Fənn qovluğu və onun mövzuları.

``SubjectFolder`` — bir müəllimin bir fənn (və semestr) üzrə iş sahəsi: bir dəfə
hazırlanır, sonra müəllimin tədris etdiyi qruplara (``FolderAssignment``) təyin
olunur. ``FolderTopic`` — təsdiqlənmiş sillabusun həftəlik planından yaranan
(və ya müəllimin əlavə etdiyi) mövzu; materiallar və tapşırıqlar mövzuya
bağlana bilər.

Modul sərhədi: registrar/organizations modellərinə yalnız STRING FK ilə
istinad olunur — ``apps.*`` Python importu yoxdur.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

from ..constants import FolderStatus, TopicSource

_CTX = "subject_folder.model"


class SubjectFolder(UUIDModel, TimeStampedModel):
    """Müəllimin fənn qovluğu — (təşkilat, fənn, sahib, semestr) üzrə TƏK."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="subject_folders"
    )
    subject = models.ForeignKey("registrar.Subject", on_delete=models.PROTECT, related_name="subject_folders")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="subject_folders")
    period = models.ForeignKey(
        "organizations.AcademicPeriod",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="subject_folders",
        help_text="Semestr. Boşdursa qovluq istənilən semestrin açılışına təyin oluna bilər.",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=FolderStatus.choices, default=FolderStatus.DRAFT, db_index=True)
    syllabus_ref = models.UUIDField(
        null=True,
        blank=True,
        help_text="Mövzuların son sinxron olunduğu TƏSDİQLƏNMİŞ sillabus versiyasının id-si (məlumat üçün).",
    )
    selfwork_option = models.CharField(
        max_length=8,
        blank=True,
        default="",
        help_text="Sillabusun sərbəst iş strukturu (1x10 / 2x5 / 10x1); boş = sillabus yoxdur.",
    )
    synced_at = models.DateTimeField(null=True, blank=True)
    source_folder = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="derived_folders",
        help_text="Keçən semestrdən köçürülübsə mənbə qovluq.",
    )

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "fənn qovluğu")
        verbose_name_plural = pgettext_lazy(_CTX, "fənn qovluqları")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "subject", "owner", "period"],
                condition=Q(period__isnull=False),
                name="sf_folder_uniq_subject_owner_period",
            ),
            models.UniqueConstraint(
                fields=["organization", "subject", "owner"],
                condition=Q(period__isnull=True),
                name="sf_folder_uniq_subject_owner_noperiod",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "owner", "status"], name="sf_folder_org_owner_status"),
            models.Index(fields=["organization", "subject", "period"], name="sf_folder_org_subject_period"),
        ]

    def __str__(self):
        return self.title or str(self.subject_id)

    @property
    def is_archived(self) -> bool:
        return self.status == FolderStatus.ARCHIVED


class FolderTopic(UUIDModel, TimeStampedModel):
    """Qovluğun mövzusu (həftə).

    ``syllabus_uid`` — sillabus sətrinin SABİT açarı (ilk sinxron zamanı sillabus
    başlığından hesablanır, sonra dəyişmir); təkrar sinxron həmin açarla uyğunlaşır.
    ``syllabus_title`` sillabusdakı son başlıqdır — müəllim ``title``-ı dəyişməyibsə
    sinxron onu yeniləyir, dəyişibsə müəllimin adı qalır.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="subject_folder_topics"
    )
    folder = models.ForeignKey(SubjectFolder, on_delete=models.CASCADE, related_name="topics")
    order = models.PositiveIntegerField(default=0)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    week_no = models.PositiveSmallIntegerField(null=True, blank=True)
    source = models.CharField(max_length=16, choices=TopicSource.choices, default=TopicSource.CUSTOM)
    syllabus_uid = models.CharField(max_length=40, null=True, blank=True)
    syllabus_title = models.CharField(max_length=255, blank=True, default="")
    is_archived = models.BooleanField(
        default=False,
        help_text="Sillabusdan çıxıb, amma bağlı materialı var — silinmir, gizlədilir.",
    )

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "qovluq mövzusu")
        verbose_name_plural = pgettext_lazy(_CTX, "qovluq mövzuları")
        ordering = ["folder", "order", "week_no", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["folder", "syllabus_uid"],
                condition=Q(syllabus_uid__isnull=False),
                name="sf_topic_uniq_syllabus_uid",
            ),
            models.CheckConstraint(
                condition=Q(source=TopicSource.CUSTOM) | Q(syllabus_uid__isnull=False),
                name="sf_topic_syllabus_has_uid",
            ),
        ]
        indexes = [models.Index(fields=["organization", "folder", "order"], name="sf_topic_org_folder_order")]

    def __str__(self):
        return self.title


__all__ = ["FolderTopic", "SubjectFolder"]
