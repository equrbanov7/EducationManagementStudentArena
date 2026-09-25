"""Cədvəl GİRİŞ modelləri — müəllim əlçatanlığı və qrup növbə siyasəti.

Modul sərhədi: burada ``apps.*`` importu YOXDUR — registrar/organizations
modellərinə yalnız STRING FK ilə istinad olunur (``apps/workload/models`` naxışı).
Hər iki cədvəl tenant-scoped-dur (``organization`` FK) və RLS ilə qorunur
(``migrations/0002_rls_timetable``).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

_CTX = "timetable.model"


class TeacherAvailability(UUIDModel, TimeStampedModel):
    """Müəllimin semestr üzrə həftəlik əlçatanlığı (gün × dərs saatı).

    ``grid`` — kompakt JSON: ``{"1": "nnnnuudd", "2": …}``; açar ISO həftə günü
    (1 = B.e.), dəyər hər dərs saatı üçün bir simvol:

    * ``n`` — neytral, ``p`` — üstünlük verilir;
    * ``d`` — «dəyişdirilə bilən saat» (gələ bilər, amma arzuolunmaz — yumşaq cərimə);
    * ``u`` — «olmayan saat / gələ bilmədiyi gün» (SƏRT — heç vaxt istifadə olunmur).

    Olmayan gün / qısa sətir → neytral. Prioritet (1–5) mühərrikdə yerləşdirmə
    sırasını və bu müəllimin yumşaq cərimələrinin çəkisini artırır;
    ``subject_priorities`` fənn üzrə əlavə çəkidir (``{subject_id: 1..5}``).
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="timetable_availabilities"
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="timetable_availabilities"
    )
    period = models.ForeignKey(
        "organizations.AcademicPeriod", on_delete=models.CASCADE, related_name="timetable_availabilities"
    )
    grid = models.JSONField(default=dict, blank=True)
    max_pairs_per_day = models.PositiveSmallIntegerField(null=True, blank=True)
    max_days_per_week = models.PositiveSmallIntegerField(null=True, blank=True)
    priority = models.PositiveSmallIntegerField(default=1)
    subject_priorities = models.JSONField(default=dict, blank=True)
    note = models.TextField(blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "müəllim əlçatanlığı")
        verbose_name_plural = pgettext_lazy(_CTX, "müəllim əlçatanlıqları")
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "teacher", "period"], name="uniq_timetable_availability_teacher_period"
            ),
            models.CheckConstraint(
                check=models.Q(priority__gte=1) & models.Q(priority__lte=5),
                name="timetable_availability_priority_1_5",
            ),
        ]
        indexes = [models.Index(fields=["organization", "period"])]

    def __str__(self):
        return f"{self.teacher_id} · {self.period_id}"


class GroupTimePolicy(UUIDModel, TimeStampedModel):
    """Qrupun icazəli növbələri (səhər / günorta / axşam) və gündəlik limiti.

    İki növ sətir:

    * ``group`` boş, ``level`` dolu — pillə defoltu (bakalavr / magistr /
      doktorantura / qiyabi); yoxdursa ``constants.BUILTIN_POLICY`` işləyir
      (bakalavr: səhər+günorta, magistr: YALNIZ axşam, qiyabi: daxil edilmir);
    * ``group`` dolu — konkret qrup üçün istisna (override).

    ``weekdays`` boşdursa işləmənin tədris günləri götürülür.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="timetable_group_policies"
    )
    group = models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="timetable_policies",
    )
    level = models.CharField(max_length=16, blank=True)
    bands = models.JSONField(default=list, blank=True)
    weekdays = models.JSONField(default=list, blank=True)
    max_pairs_per_day = models.PositiveSmallIntegerField(null=True, blank=True)
    is_excluded = models.BooleanField(default=False)
    note = models.TextField(blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "qrup növbə siyasəti")
        verbose_name_plural = pgettext_lazy(_CTX, "qrup növbə siyasətləri")
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "group"],
                condition=models.Q(group__isnull=False),
                name="uniq_timetable_policy_group",
            ),
            models.UniqueConstraint(
                fields=["organization", "level"],
                condition=models.Q(group__isnull=True),
                name="uniq_timetable_policy_level",
            ),
        ]

    def __str__(self):
        return f"{self.group_id or self.level}"


__all__ = ["GroupTimePolicy", "TeacherAvailability"]
