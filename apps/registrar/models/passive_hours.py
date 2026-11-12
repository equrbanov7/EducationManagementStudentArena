"""İntensiv tədrisdə «passiv saat» — auditoriyadan kənar (müstəqil iş) saatlarının jurnal qeydi (sahib 2026-11-12).

MR-000303: «… fənni intensiv keçirilir. Jurnalda passiv günləri qeyd etmək üçün xana yoxdur.» Sahib: «passiv saat
əlavə etmək olsun». Köhnə sistemdə ayrıca sahə YOX idi (müəllim adi dərs tarixinin xanasına «passiv» yazırdı), ona
görə qayda yenidir və dar saxlanılır: sətir = tarix + saat + qısa qeyd. Dərs (``Lesson``) DEYİL — davamiyyət, bal,
saat həddi (#6), yük və mühasibat dəyişmir; jurnal başlığında ayrıca «Passiv» sayı kimi görünür.
Qaydalar: :mod:`apps.registrar.passive_hours`.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

PASSIVE_NOTE_MAX_LENGTH = 200
PASSIVE_HOURS_MAX = 8


class PassiveHour(UUIDModel, TimeStampedModel):
    """Bir açılışın bir passiv saat qeydi (bir gündə bir neçə sətir ola bilər)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="passive_hours", db_index=False
    )
    offering = models.ForeignKey("registrar.CourseOffering", on_delete=models.CASCADE, related_name="passive_hours")
    date = models.DateField()
    hours = models.PositiveSmallIntegerField()
    note = models.CharField(max_length=PASSIVE_NOTE_MAX_LENGTH, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["offering_id", "date", "created_at"]
        verbose_name = pgettext_lazy("registrar.model.passive_hour.meta", "passiv saat")
        verbose_name_plural = pgettext_lazy("registrar.model.passive_hour.meta", "passiv saatlar")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(hours__gte=1, hours__lte=PASSIVE_HOURS_MAX), name="reg_passive_hours_range"
            ),
        ]

    def __str__(self):
        return f"passive<{self.offering_id}> {self.date} · {self.hours}"
