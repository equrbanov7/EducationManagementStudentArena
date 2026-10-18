"""«Dərs saatının ödəniş dərəcələri» — Mühasibatlığın saxladığı saat dərəcəsi cədvəli (sahib 2026-10-19).

Sətir: tədris ili × vəzifə (``workload.TeacherWorkloadProfile.position`` açarları — Professor / Dosent / Baş müəllim /
Müəllim / Assistent) × fəaliyyət növü (mühazirə / seminar / laboratoriya; BOŞ = bütün növlər) × saat dərəcəsi (AZN).

TARİXÇƏ (sətir HEÇ VAXT silinmir): dəyişiklik köhnə sətri ARXİVLƏYİR (``archived_at`` + səbəb «əvəzləndi») və yeni
sətir yaradır; «Sil» də yalnız arxivləyir (səbəb «ləğv edildi»). Beləliklə keçmiş ixracda istifadə olunmuş dərəcə
həmişə oxunur. Aktiv sətir (org, il, vəzifə, növ) üzrə UNİKALDIR. PostgreSQL trigger-i (miqrasiya
``0033_teaching_pay_rate``) DELETE-i və arxivləmədən başqa hər UPDATE-i bloklayır; ``rls_tenant_isolation``
təşkilatları ayırır. Vəzifə sahəsi seçimsiz ``CharField``-dir — açarlar ``workload`` modulundan app registry ilə
oxunur (statik import yoxdur, modul sərhədi), yoxlama servis qatındadır (``services/accounting/rates.py``).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

_CTX = "accounts.accounting"

#: Fəaliyyət növləri — ``services/accounting/constants.KIND_KEYS`` ilə eyni sətirlər; boş = bütün növlər.
PAY_RATE_ACTIVITIES = ("lecture", "seminar", "lab")


class PayRateArchiveReason(models.TextChoices):
    REPLACED = "replaced", pgettext_lazy(_CTX, "Yeni dərəcə ilə əvəzləndi")
    REMOVED = "removed", pgettext_lazy(_CTX, "Ləğv edildi")


class TeachingPayRate(UUIDModel, TimeStampedModel):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="+")
    academic_year = models.CharField(max_length=20, help_text="Məs. «2026/2027» (AcademicPeriod.academic_year).")
    position = models.CharField(max_length=32, help_text="workload.TeacherWorkloadProfile.position açarı.")
    activity = models.CharField(max_length=16, blank=True, help_text="lecture / seminar / lab; boş — bütün növlər.")
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, help_text="1 akademik saatın dərəcəsi (AZN).")
    note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_by_name = models.CharField(max_length=200, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    archived_by_name = models.CharField(max_length=200, blank=True)
    archive_reason = models.CharField(max_length=16, choices=PayRateArchiveReason.choices, blank=True)

    objects = models.Manager()

    class Meta:
        ordering = ["-academic_year", "position", "activity", "-created_at"]
        verbose_name = pgettext_lazy("accounts.model.pay_rate.meta", "teaching pay rate")
        verbose_name_plural = pgettext_lazy("accounts.model.pay_rate.meta", "teaching pay rates")
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "academic_year", "position", "activity"],
                condition=Q(archived_at__isnull=True),
                name="accounts_pay_rate_active_unique",
            ),
            models.CheckConstraint(condition=Q(hourly_rate__gt=0), name="accounts_pay_rate_positive"),
            models.CheckConstraint(
                condition=Q(activity__in=("", *PAY_RATE_ACTIVITIES)), name="accounts_pay_rate_activity_valid"
            ),
            models.CheckConstraint(
                condition=Q(archive_reason__in=("", *PayRateArchiveReason.values)),
                name="accounts_pay_rate_archive_reason_valid",
            ),
        ]
        indexes = [models.Index(fields=["organization", "academic_year"], name="acc_pay_rate_org_year_idx")]

    def __str__(self):
        return f"pay-rate<{self.academic_year}/{self.position}/{self.activity or '*'}> {self.hourly_rate}"

    @property
    def is_active(self) -> bool:
        return self.archived_at is None


__all__ = ["PAY_RATE_ACTIVITIES", "PayRateArchiveReason", "TeachingPayRate"]
