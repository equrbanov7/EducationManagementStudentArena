"""Sorğu kampaniyası — akademik dövr başına BİR (``(organization, period)`` unikal).

Vəziyyət: ``draft`` → ``open`` → ``closed`` (``closed`` → ``open`` yenidən açılış
kimi mümkündür). «Effektiv» vəziyyət tarixdən də asılıdır: ``open`` olsa belə
``opens_on``-dan əvvəl və ``closes_on``-dan sonra kampaniya AKTİV sayılmır —
cron olmadan da qapı özü bağlanır (bax :meth:`SurveyCampaign.is_active_on`).
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

from ..constants import (
    DEFAULT_MIN_GROUP_SIZE,
    MIN_GROUP_SIZE_CEIL,
    MIN_GROUP_SIZE_FLOOR,
    CampaignStatus,
    OpenedVia,
)
from .templates import SurveyTemplate

_CTX = "surveys.model"


class SurveyCampaign(UUIDModel, TimeStampedModel):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="survey_campaigns"
    )
    period = models.ForeignKey(
        "organizations.AcademicPeriod", on_delete=models.PROTECT, related_name="survey_campaigns"
    )
    template = models.ForeignKey(SurveyTemplate, on_delete=models.PROTECT, related_name="campaigns")
    status = models.CharField(
        max_length=12, choices=CampaignStatus.choices, default=CampaignStatus.DRAFT, db_index=True
    )
    opens_on = models.DateField(null=True, blank=True)
    closes_on = models.DateField(null=True, blank=True)
    mandatory = models.BooleanField(default=True)
    #: Bu tarixə qədər (daxil) qapı «Sonra doldur» təklif edir; sonra qapı sərtdir.
    grace_until = models.DateField(null=True, blank=True)
    #: k-anonimlik həddi — nəticələr bu saydan az cavablı qrup üçün gizlədilir.
    min_group_size = models.PositiveSmallIntegerField(
        default=DEFAULT_MIN_GROUP_SIZE,
        validators=[MinValueValidator(MIN_GROUP_SIZE_FLOOR), MaxValueValidator(MIN_GROUP_SIZE_CEIL)],
    )
    opened_via = models.CharField(max_length=20, choices=OpenedVia.choices, default=OpenedVia.MANUAL)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    opened_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "sorğu kampaniyası")
        verbose_name_plural = pgettext_lazy(_CTX, "sorğu kampaniyaları")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "period"], name="surveys_campaign_period_uniq"),
            models.CheckConstraint(
                condition=models.Q(min_group_size__gte=MIN_GROUP_SIZE_FLOOR),
                name="surveys_campaign_min_group_floor",
            ),
            models.CheckConstraint(
                condition=models.Q(closes_on__isnull=True)
                | models.Q(opens_on__isnull=True)
                | models.Q(closes_on__gte=models.F("opens_on")),
                name="surveys_campaign_dates_ordered",
            ),
        ]

    def __str__(self):
        return f"campaign<{self.period_id}:{self.status}>"

    def is_active_on(self, day) -> bool:
        """``open`` + tarix pəncərəsinin içində (hər iki sərhəd daxil)."""
        if self.status != CampaignStatus.OPEN:
            return False
        if self.opens_on and day < self.opens_on:
            return False
        if self.closes_on and day > self.closes_on:
            return False
        return True

    def effective_status(self, day) -> str:
        """UI üçün: ``open`` + ``closes_on`` keçib → ``closed``; ``opens_on`` gəlməyib → ``scheduled``."""
        if self.status == CampaignStatus.OPEN:
            if self.closes_on and day > self.closes_on:
                return CampaignStatus.CLOSED
            if self.opens_on and day < self.opens_on:
                return "scheduled"
        return self.status

    def grace_applies_on(self, day) -> bool:
        return bool(self.grace_until and day <= self.grace_until)
