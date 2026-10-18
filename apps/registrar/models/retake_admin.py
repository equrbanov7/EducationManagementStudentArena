"""25% müraciətinin İDARƏ cədvəlləri — müraciət pəncərəsi və təhsil haqqı cədvəli (sahib 2026-10-19).

* ``RetakeWindow`` — «İmtahan mərkəzi açsın bunu»: təşkilat × akademik dövr üzrə müraciət pəncərəsi
  (``exam_center.decide``). Açılış / bağlanış kim, nə vaxt — sətir silinmir, bağlanış eyni sətrə yazılır
  (tarixçə = bütün sətirlər). Kollokvium pəncərəsi ilə eyni yer (İmtahan mərkəzi menyusu).
* ``RetakeTuition`` — «İlliyə görə hesablanır»: illik təhsil haqqı tədris ili × qəbul ili (× ixtisas, opsional).
  İxtisassız sətir defoltdur. Mühasibatlıq saxlayır (``retake.payment_verify`` / ``accounting.manage_fees``).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

_CTX = "registrar.retake"


class RetakeWindow(UUIDModel, TimeStampedModel):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="+")
    period = models.ForeignKey("organizations.AcademicPeriod", on_delete=models.PROTECT, related_name="+")
    opens_at = models.DateTimeField()
    closes_at = models.DateTimeField(null=True, blank=True, help_text="Boşdursa əl ilə bağlanana qədər açıqdır.")
    note = models.CharField(max_length=300, blank=True)
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    opened_by_name = models.CharField(max_length=200, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    closed_by_name = models.CharField(max_length=200, blank=True)
    close_note = models.CharField(max_length=300, blank=True)

    objects = models.Manager()

    class Meta:
        ordering = ["-opens_at"]
        verbose_name = pgettext_lazy("registrar.model.retake_window.meta", "retake application window")
        verbose_name_plural = pgettext_lazy("registrar.model.retake_window.meta", "retake application windows")
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "period"],
                condition=Q(closed_at__isnull=True),
                name="registrar_retake_window_one_open_per_period",
            ),
        ]
        indexes = [models.Index(fields=["organization", "-opens_at"], name="reg_retake_win_org_idx")]

    def __str__(self):
        return f"retake-window<{self.period_id}> {self.opens_at:%Y-%m-%d} → {self.closes_at or '…'}"

    def is_open_at(self, moment) -> bool:
        if self.closed_at is not None or self.opens_at > moment:
            return False
        return self.closes_at is None or moment < self.closes_at


class RetakeTuition(UUIDModel, TimeStampedModel):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="+")
    academic_year = models.CharField(max_length=20, help_text="Məs. «2025/2026» (AcademicPeriod.academic_year).")
    admission_year = models.PositiveIntegerField()
    program = models.ForeignKey("registrar.Program", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    annual_amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="İllik təhsil haqqı (AZN).")
    note = models.CharField(max_length=300, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = models.Manager()

    class Meta:
        ordering = ["-academic_year", "-admission_year"]
        verbose_name = pgettext_lazy("registrar.model.retake_tuition.meta", "annual tuition")
        verbose_name_plural = pgettext_lazy("registrar.model.retake_tuition.meta", "annual tuition table")
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "academic_year", "admission_year"],
                condition=Q(program__isnull=True),
                name="registrar_retake_tuition_default_unique",
            ),
            models.UniqueConstraint(
                fields=["organization", "academic_year", "admission_year", "program"],
                condition=Q(program__isnull=False),
                name="registrar_retake_tuition_program_unique",
            ),
            models.CheckConstraint(condition=Q(annual_amount__gte=0), name="registrar_retake_tuition_amount_gte0"),
        ]
        indexes = [models.Index(fields=["organization", "admission_year"], name="reg_retake_tuit_adm_idx")]

    def __str__(self):
        return f"tuition<{self.academic_year}/{self.admission_year}/{self.program_id or '*'}> {self.annual_amount}"


__all__ = ["RetakeTuition", "RetakeWindow"]
