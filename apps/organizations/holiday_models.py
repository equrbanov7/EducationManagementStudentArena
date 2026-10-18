"""Bayram və qeyri-iş günləri təqvimi — ``AcademicHoliday`` (sahib 2026-10-19).

NİYƏ AYRI MODUL? ``organizations/models.py`` 600 sətir tavanındadır (``scripts/check_module_size.py``);
model buradadır və ``models.py``-dan import olunur (Django app_label = ``organizations``).

NÖVLƏR (``HolidayKind``):

* ``holiday``  — rəsmi bayram (Yeni il, Novruz, Zəfər günü …) — İŞ/DƏRS GÜNÜ DEYİL;
* ``day_off``  — qeyri-iş günü (hökumətin köçürdüyü istirahət günü, bayramın həftə sonuna düşməsi ilə
  əlavə olunan gün, universitetin öz qərarı) — İŞ/DƏRS GÜNÜ DEYİL;
* ``workday``  — «iş günü köçürməsi»: istirahət günü (şənbə/bazar) İŞ GÜNÜ elan olunub — iş günü
  hesablarında (müraciət SLA-sı, mühasibatlığın plan bölgüsü) iş günü sayılır.

Bir tarixdə bir qeyd (unikal: təşkilat + tarix). Oxu/keş: :mod:`apps.organizations.holidays`.
RLS: birbaşa ``organization_id`` izolyasiyası (miqrasiya ``0070_academic_holiday``).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

_CTX = "organizations.holiday"


class HolidayKind(models.TextChoices):
    HOLIDAY = "holiday", pgettext_lazy(_CTX, "Bayram")
    DAY_OFF = "day_off", pgettext_lazy(_CTX, "Qeyri-iş günü")
    WORKDAY = "workday", pgettext_lazy(_CTX, "İş günü köçürməsi")


#: İş/dərs günü OLMAYAN növlər.
NON_WORKING_KINDS = frozenset({HolidayKind.HOLIDAY.value, HolidayKind.DAY_OFF.value})


class AcademicHoliday(UUIDModel, TimeStampedModel):
    """Təşkilatın təqvimində bir gün: bayram, qeyri-iş günü və ya iş gününə köçürülmüş istirahət günü."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="academic_holidays"
    )
    date = models.DateField()
    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=20, choices=HolidayKind.choices, default=HolidayKind.HOLIDAY)
    note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["date"]
        verbose_name = pgettext_lazy(_CTX, "Bayram / qeyri-iş günü")
        verbose_name_plural = pgettext_lazy(_CTX, "Bayram və qeyri-iş günləri")
        constraints = [
            models.UniqueConstraint(fields=["organization", "date"], name="org_academic_holiday_unique_date"),
        ]

    def __str__(self):
        return f"{self.date:%d.%m.%Y} · {self.name}"

    @property
    def is_non_working(self) -> bool:
        return self.kind in NON_WORKING_KINDS

    # Keş invalidasiyası model səviyyəsindədir (signal yox — ``check_worker_atomic_coverage``): admin və
    # servis yazıları eyni yoldan keçir. Toplu yazı (``bulk_create``) servisdə ayrıca invalidasiya edir.
    def save(self, *args, **kwargs):
        previous = None
        if self.pk and not self._state.adding:
            previous = type(self).objects.filter(pk=self.pk).values_list("date", flat=True).first()
        super().save(*args, **kwargs)
        self._invalidate(previous)

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        self._invalidate(None)
        return result

    def _invalidate(self, previous_date):
        from .holidays import invalidate

        years = {self.date.year} | ({previous_date.year} if previous_date else set())
        invalidate(self.organization_id, years)
