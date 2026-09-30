"""Sorğu qurucusu (2026-09-30) — ``Survey``: bir sorğunun tərifi + icrası.

Hər sorğunun ÖZ sual dəsti var (``template`` — ``SurveyTemplate``, 1:1, ``PROTECT``):
suallar, bölmələr və cavablar dəst üzərindən bağlanır, dublikat yeni dəst yaradır.

Növlər:

* ``teacher_evaluation`` — mövcud semestr axını (müəllim × fənn, anonim). Burada yalnız
  SUAL DƏSTİ idarə olunur; auditoriya (jurnalı bağlanmış fənlərin tələbələri), tarixlər
  və məcburilik dövr kampaniyasındadır (``SurveyCampaign.template``). Anonimlik məcburidir
  (DB məhdudiyyəti).
* ``general`` / ``course_feedback`` / ``event`` — müstəqil sorğu: auditoriya (tələbə /
  müəllim / heyət / hamı + struktur daraltması), tarix pəncərəsi, könüllü və ya məcburi
  (qapı siyasəti ilə), anonim və ya şəxsli.

Vəziyyət: ``draft`` → ``published`` → ``closed`` (→ yenidən ``published``) → ``archived``.
Effektiv vəziyyət tarixdən də asılıdır (``published`` + ``closes_on`` keçib → bağlı;
``opens_on`` gəlməyib → planlaşdırılıb) — kampaniya ilə eyni qayda, cron-suz.
"""

from __future__ import annotations

import datetime

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

from ..constants import (
    DEFAULT_DEFER_DAYS,
    DEFAULT_MIN_GROUP_SIZE,
    MAX_DEFER_DAYS,
    MIN_GROUP_SIZE_CEIL,
    MIN_GROUP_SIZE_FLOOR,
    Audience,
    GatePolicy,
    SurveyKind,
    SurveyStatus,
)
from .templates import SurveyTemplate

_CTX = "surveys.model"


class Survey(UUIDModel, TimeStampedModel):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="surveys")
    template = models.OneToOneField(SurveyTemplate, on_delete=models.PROTECT, related_name="survey")
    kind = models.CharField(max_length=24, choices=SurveyKind.choices, default=SurveyKind.GENERAL)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    anonymous = models.BooleanField(default=True)
    audience = models.CharField(max_length=16, choices=Audience.choices, default=Audience.STUDENTS)
    #: Struktur daraltması: ``{"units": [uuid], "programs": [uuid], "course_years": [int]}``
    #: (bax ``services/audience.py``; proqram / kurs yalnız tələbələrə aiddir).
    audience_filter = models.JSONField(default=dict, blank=True)
    opens_on = models.DateField(null=True, blank=True)
    closes_on = models.DateField(null=True, blank=True)
    mandatory = models.BooleanField(default=False)
    gate_policy = models.CharField(max_length=16, choices=GatePolicy.choices, default=GatePolicy.DEFER_DAYS)
    defer_days = models.PositiveSmallIntegerField(
        default=DEFAULT_DEFER_DAYS, validators=[MinValueValidator(0), MaxValueValidator(MAX_DEFER_DAYS)]
    )
    #: k-anonimlik həddi (yalnız anonim sorğuda işlənir).
    min_group_size = models.PositiveSmallIntegerField(
        default=DEFAULT_MIN_GROUP_SIZE,
        validators=[MinValueValidator(MIN_GROUP_SIZE_FLOOR), MaxValueValidator(MIN_GROUP_SIZE_CEIL)],
    )
    status = models.CharField(max_length=12, choices=SurveyStatus.choices, default=SurveyStatus.DRAFT, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    #: Anonim sorğunun nəticələrinin İLK dərc anı (Audit 2026-09-28 SV-2 ilə eyni qayda).
    results_published_at = models.DateTimeField(null=True, blank=True)
    #: Auditoriyaya «sorğu açıldı» bildirişi göndərilib (bir dəfə; atomik bayraq).
    notified_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "sorğu")
        verbose_name_plural = pgettext_lazy(_CTX, "sorğular")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "status"], name="surveys_survey_org_status")]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(kind=SurveyKind.TEACHER_EVALUATION) | models.Q(anonymous=True),
                name="surveys_survey_teacher_eval_anonymous",
            ),
            models.CheckConstraint(
                condition=models.Q(min_group_size__gte=MIN_GROUP_SIZE_FLOOR), name="surveys_survey_min_group_floor"
            ),
            models.CheckConstraint(
                condition=models.Q(closes_on__isnull=True)
                | models.Q(opens_on__isnull=True)
                | models.Q(closes_on__gte=models.F("opens_on")),
                name="surveys_survey_dates_ordered",
            ),
        ]

    def __str__(self):
        return f"survey<{self.kind}:{self.status}>"

    @property
    def is_teacher_evaluation(self) -> bool:
        return self.kind == SurveyKind.TEACHER_EVALUATION

    @property
    def grace_until(self):
        """«Sonra doldur» son günü — yalnız ``defer_days`` siyasətində (açılış + N gün, bağlanışa qədər)."""
        if not self.mandatory or self.gate_policy != GatePolicy.DEFER_DAYS or not self.defer_days:
            return None
        if self.opens_on is None:
            return None
        day = self.opens_on + datetime.timedelta(days=int(self.defer_days))
        return min(day, self.closes_on) if self.closes_on else day

    def is_active_on(self, day) -> bool:
        if self.is_teacher_evaluation or self.status != SurveyStatus.PUBLISHED:
            return False
        if self.opens_on and day < self.opens_on:
            return False
        if self.closes_on and day > self.closes_on:
            return False
        return True

    def effective_status(self, day) -> str:
        if self.status == SurveyStatus.PUBLISHED and not self.is_teacher_evaluation:
            if self.closes_on and day > self.closes_on:
                return SurveyStatus.CLOSED
            if self.opens_on and day < self.opens_on:
                return "scheduled"
        return self.status
