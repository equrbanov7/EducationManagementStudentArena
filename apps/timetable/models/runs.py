"""Cədvəl İŞLƏMƏSİ (run) və onun QARALAMA slotları.

Qaralama canlı cədvəl DEYİL: ``TimetableDraftSlot`` yalnız «Dərc et» anında
``registrar.ScheduleSlot``-a çevrilir (registrar servis qatı, bir transaksiya).
Beləcə koordinator bir neçə variantı müqayisə edə, kilidləyə, əl ilə düzəldə və
yalnız razı qalanda dərc edə bilir.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

from ..constants import RunStatus

_CTX = "timetable.model"


class TimetableRun(UUIDModel, TimeStampedModel):
    """Bir avtomatik yerləşdirmə cəhdi (əhatə + parametrlər + nəticə KPI-ları).

    ``scope`` — ``{"kind": faculty|program|groups, "unit_ids": [...],
    "group_ids": [...], "label": str}``; ``params`` — vaxt limiti, tədris günləri,
    axın siyasəti, çəkilər…; ``priorities`` — ``{"teachers": [user_id, …]}``
    (yuxarıdakı daha vacib); ``progress`` — işləyərkən faza/faiz/ürək döyüntüsü.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="timetable_runs"
    )
    period = models.ForeignKey("organizations.AcademicPeriod", on_delete=models.CASCADE, related_name="timetable_runs")
    title = models.CharField(max_length=160, blank=True)
    scope = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=RunStatus.choices, default=RunStatus.DRAFT, db_index=True)
    seed = models.PositiveIntegerField(default=1)
    params = models.JSONField(default=dict, blank=True)
    priorities = models.JSONField(default=dict, blank=True)
    kpis = models.JSONField(default=dict, blank=True)
    progress = models.JSONField(default=dict, blank=True)
    log = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    source_run = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="reruns")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "cədvəl işləməsi")
        verbose_name_plural = pgettext_lazy(_CTX, "cədvəl işləmələri")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "period", "status"])]

    def __str__(self):
        return self.title or str(self.pk)


class TimetableDraftSlot(UUIDModel, TimeStampedModel):
    """İşləmənin bir dərs cütü (bir açılış üçün).

    Axın mühazirəsi bir neçə qrupu birlikdə tutur → eyni ``event_key`` ilə hər
    açılışa bir sətir düşür; köçürmə/kilid bütün sətirlərə birlikdə tətbiq olunur.
    ``weekday``/``pair`` boşdursa dərs YERLƏŞDİRİLMƏYİB — ``reason`` səbəbi deyir.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="timetable_draft_slots"
    )
    run = models.ForeignKey(TimetableRun, on_delete=models.CASCADE, related_name="slots")
    event_key = models.CharField(max_length=160, db_index=True)
    offering = models.ForeignKey(
        "registrar.CourseOffering", on_delete=models.CASCADE, related_name="timetable_draft_slots"
    )
    kind = models.CharField(max_length=16)
    weekday = models.PositiveSmallIntegerField(null=True, blank=True)
    pair = models.PositiveSmallIntegerField(null=True, blank=True)
    week_type = models.CharField(max_length=8, default="all")
    is_biweekly = models.BooleanField(default=False)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    room = models.CharField(max_length=64, blank=True)
    room_ref = models.CharField(max_length=64, blank=True)
    locked = models.BooleanField(default=False)
    is_manual = models.BooleanField(default=False)
    penalty = models.IntegerField(default=0)
    reason_code = models.CharField(max_length=32, blank=True)
    reason = models.TextField(blank=True)

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "qaralama slot")
        verbose_name_plural = pgettext_lazy(_CTX, "qaralama slotlar")
        ordering = ["weekday", "pair", "event_key"]
        indexes = [
            models.Index(fields=["run", "weekday", "pair"]),
            models.Index(fields=["run", "offering"]),
        ]

    def __str__(self):
        return f"{self.event_key} · {self.weekday}/{self.pair}"

    @property
    def is_placed(self) -> bool:
        return self.weekday is not None and self.pair is not None


__all__ = ["TimetableDraftSlot", "TimetableRun"]
