"""Bölgü sətri və müəllimin illik yük profili (spec §5.5–§5.6)."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

from ..constants import (
    DEFAULT_ANNUAL_NORM_HOURS,
    Activity,
    TeacherPosition,
)
from .task import TeachingTaskRow

_CTX = "workload.model"


class TeacherAssignment(UUIDModel, TimeStampedModel):
    """Bir sətrin bir fəaliyyət növünün bir müəllimə (və ya «Vakant»a) bölgüsü.

    Saat balansı İKİ QATDA qorunur:

    1. servis (``services.assignments``) — sətri ``select_for_update`` ilə
       kilidləyib fəaliyyət üzrə qalığı hesablayır;
    2. Postgres trigger-i (``0002_rls_workload``) — hər INSERT/UPDATE-də
       ``Σ hours ≤ sətrin həmin fəaliyyət cəmi`` şərtini yoxlayır (servisi
       yan keçən hər yol da bağlıdır).
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="workload_assignments"
    )
    row = models.ForeignKey(TeachingTaskRow, on_delete=models.CASCADE, related_name="assignments")
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="workload_assignments",
        help_text="Boşdursa — VAKANT (saathesabı fondu / işə qəbul ehtiyacı).",
    )
    activity = models.CharField(max_length=32, choices=Activity.choices, db_index=True)
    hours = models.PositiveIntegerField(help_text="Bu müəllimə düşən saat (>0).")
    groups_note = models.CharField(
        max_length=255, blank=True, help_text="Hansı qrup/yarımqrup — «236 İ ing, 2-ci yarımqrup»."
    )
    is_hourly_paid = models.BooleanField(default=False, help_text="Saathesabı fondundan ödənilir.")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="made_workload_assignments",
    )
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "bölgü sətri")
        verbose_name_plural = pgettext_lazy(_CTX, "bölgü sətirləri")
        ordering = ["row", "activity", "created_at"]
        constraints = [
            models.CheckConstraint(check=models.Q(hours__gt=0), name="workload_assignment_hours_positive"),
        ]
        indexes = [
            models.Index(fields=["row", "activity"]),
            models.Index(fields=["organization", "teacher"]),
        ]

    def __str__(self):
        return f"{self.row_id} · {self.activity} · {self.hours}s"

    @property
    def is_vacant(self) -> bool:
        return self.teacher_id is None


class TeacherWorkloadProfile(UUIDModel, TimeStampedModel):
    """Müəllimin illik yük profili — norma müqayisəsinin YEGANƏ mənbəyi.

    Profil yoxdursa norma ``DEFAULT_ANNUAL_NORM_HOURS`` (NK №215: 500 saat)
    sayılır; universitet-daxili vəzifə differensiasiyası RƏSMİ DEYİL, ona görə
    hardcode edilmir — tenant profillə konfiqurasiya edir (spec §8).
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="workload_profiles"
    )
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workload_profiles")
    academic_year = models.CharField(max_length=20, db_index=True)
    position = models.CharField(max_length=32, choices=TeacherPosition.choices, default=TeacherPosition.MUELLIM)
    staff_fraction = models.DecimalField(
        max_digits=4, decimal_places=2, default=1, help_text="Ştat payı: 0.25 … 1.50 (KQ-12: max 1,5)."
    )
    annual_norm_hours = models.PositiveIntegerField(default=DEFAULT_ANNUAL_NORM_HOURS)
    is_external = models.BooleanField(default=False, help_text="Kənar (saathesabı) müəllim.")
    # Ekran 16 «Təsdiq / etiraz»: müəllimin illik yükü təsdiqləməsi. Etiraz
    # AYRI reyestrdədir (`LoadObjection`) — təsdiq isə bir bayraqdır, çünki
    # ildə bir dəfə verilir və tarixçəsi `core.audit`-dədir.
    load_confirmed_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "müəllim yük profili")
        verbose_name_plural = pgettext_lazy(_CTX, "müəllim yük profilləri")
        ordering = ["-academic_year"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "teacher", "academic_year"],
                name="uniq_workload_profile_teacher_year",
            ),
        ]

    def __str__(self):
        return f"{self.teacher_id} · {self.academic_year} · {self.annual_norm_hours}s"


__all__ = ["TeacherAssignment", "TeacherWorkloadProfile"]
