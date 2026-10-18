"""«Əmək müqavilələri» modelləri — müqavilə və onun APPEND-ONLY hadisə jurnalı (sahib 2026-10-19).

* İki cədvəl də ``organization_id`` daşıyır → ``rls_tenant_isolation`` siyasəti (miqrasiya 0002).
* ``EmploymentContractEvent`` APPEND-ONLY-dir: UPDATE/DELETE həmişə, TRUNCATE yalnız cədvəl boş deyilsə və
  superuser deyilsə bloklanır (registrar 0091 naxışı). Xatırlatmalar ``(contract, kind, threshold)`` üzrə
  DB-də unikaldır — gündəlik işin təkrar işə düşməsi eyni həddi ikinci dəfə göndərmir.
* Cədvəllərarası FK-lar (bölmə, yenilənmə zənciri, hadisə → müqavilə) EYNİ təşkilatdadır — DB trigger-i
  ``hr_contracts_guard_same_org_fk`` (0002) yoxlayır.
* Fayl qorunan mediadadır (``hr_contracts/<org>/<təsadüfi ad>``), orijinal ad ``file_name``-də saxlanılır.
"""

from __future__ import annotations

import posixpath
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel, UUIDModel
from core.upload_security import FileUploadValidator

from .constants import (
    FILE_EXTENSIONS,
    FILE_MAX_MB,
    MEDIA_PREFIX,
    NOTE_MAX,
    NUMBER_MAX,
    ONCE_PER_THRESHOLD_EVENTS,
    POSITION_MAX,
    ContractStatus,
    ContractType,
    EventKind,
)


def contract_file_path(instance, filename: str) -> str:
    """``hr_contracts/<org>/<uuid>.<uzantı>`` — orijinal ad yolda saxlanılmır."""
    extension = posixpath.splitext(str(filename or ""))[1].lower()
    if extension not in FILE_EXTENSIONS:
        extension = ""
    return f"{MEDIA_PREFIX}{instance.organization_id}/{uuid4().hex}{extension}"


def contract_file_validators():
    return [FileUploadValidator(allowed_extensions=set(FILE_EXTENSIONS), max_size_mb=FILE_MAX_MB)]


class EmploymentContract(UUIDModel, TimeStampedModel):
    #: PROTECT (rəy A7): CASCADE silmə append-only hadisə trigger-inə dəyib yarımçıq qalırdı (registrar kimi).
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="employment_contracts"
    )
    #: İşçi — aktiv heyət üzvlüyü olan istənilən şəxs (müəllim, inzibati heyət…); tələbə deyil.
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    number = models.CharField(max_length=NUMBER_MAX)
    contract_type = models.CharField(max_length=16, choices=ContractType.choices, default=ContractType.FIXED_TERM)
    position = models.CharField(max_length=POSITION_MAX, blank=True, default="")
    unit = models.ForeignKey(
        "organizations.OrgUnit", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    start_date = models.DateField()
    #: Müddətsiz müqavilədə boşdur; müddətlidə məcburidir (CHECK-lər aşağıda).
    end_date = models.DateField(null=True, blank=True)
    probation_end = models.DateField(null=True, blank=True)
    weekly_hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    #: Ştat vahidi (1,00 · 0,50 · 0,25 …).
    staff_rate = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    file = models.FileField(
        upload_to=contract_file_path, blank=True, max_length=200, validators=contract_file_validators()
    )
    file_name = models.CharField(max_length=255, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    status = models.CharField(max_length=12, choices=ContractStatus.choices, default=ContractStatus.ACTIVE)
    #: Yenilənmə zənciri: KÖHNƏ müqavilə → onu əvəz edən YENİ müqavilə (bir dəfə).
    renewed_by = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="renewal_of"
    )
    terminated_at = models.DateField(null=True, blank=True)
    termination_reason = models.TextField(blank=True, default="")
    #: «Müqavilə göndərildi» — HR yeni / yenilənmiş müqaviləni işçinin e-poçtuna göndərdiyini qeyd edir.
    sent_at = models.DateTimeField(null=True, blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    sent_note = models.CharField(max_length=NOTE_MAX, blank=True, default="")
    #: İşçinin «Tanış oldum, təsdiqləyirəm» təsdiqi (geri alınmır).
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledge_note = models.CharField(max_length=NOTE_MAX, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ("-start_date", "-created_at")
        verbose_name = "Əmək müqaviləsi"
        verbose_name_plural = "Əmək müqavilələri"
        indexes = [
            models.Index(fields=["organization", "employee", "-start_date"], name="hrc_org_employee_idx"),
            models.Index(fields=["organization", "status", "end_date"], name="hrc_org_status_end_idx"),
        ]
        constraints = [
            # Ləğv edilmiş qaralamanın nömrəsi yenidən istifadə oluna bilər (rəy A2).
            models.UniqueConstraint(
                fields=["organization", "number"],
                condition=~Q(number="") & ~Q(status=ContractStatus.DISCARDED),
                name="hrc_unique_number_per_org",
            ),
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                name="hrc_end_after_start",
            ),
            models.CheckConstraint(
                condition=Q(probation_end__isnull=True) | Q(probation_end__gte=models.F("start_date")),
                name="hrc_probation_after_start",
            ),
            models.CheckConstraint(
                condition=~Q(contract_type=ContractType.INDEFINITE) | Q(end_date__isnull=True),
                name="hrc_indefinite_has_no_end",
            ),
            models.CheckConstraint(
                condition=~Q(contract_type=ContractType.FIXED_TERM) | Q(end_date__isnull=False),
                name="hrc_fixed_term_has_end",
            ),
            models.CheckConstraint(
                condition=Q(acknowledged_at__isnull=True) | Q(sent_at__isnull=False),
                name="hrc_ack_requires_sent",
            ),
            models.CheckConstraint(
                condition=~Q(status=ContractStatus.TERMINATED)
                | (Q(terminated_at__isnull=False) & ~Q(termination_reason="")),
                name="hrc_terminated_has_reason",
            ),
            models.CheckConstraint(condition=Q(status__in=ContractStatus.values), name="hrc_status_valid"),
            models.CheckConstraint(
                condition=Q(renewed_by__isnull=True) | ~Q(renewed_by=models.F("id")), name="hrc_not_renewed_by_self"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.number} · {self.employee_id}"


class EmploymentContractEvent(UUIDModel):
    """APPEND-ONLY hadisə — kim, nə vaxt, nə etdi (redaktədə fərq ``data["changes"]``-dədir)."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="+")
    contract = models.ForeignKey(EmploymentContract, on_delete=models.PROTECT, related_name="events")
    kind = models.CharField(max_length=20, choices=EventKind.choices)
    #: Hesab silinəndə Django ``SET_NULL`` edir — trigger YALNIZ bu keçidə icazə verir (rəy A7); ad ``actor_name``-də qalır.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    actor_name = models.CharField(max_length=200, blank=True, default="")
    #: Xatırlatma həddi (gün) — yalnız ``reminder_sent`` / ``expired_notice`` üçün.
    threshold = models.IntegerField(null=True, blank=True)
    #: Xatırlatmanın aid olduğu BİTMƏ TARİXİ (rəy A4): müddət uzadılanda yeni tarix üçün hədlər yenidən işləyir.
    end_date = models.DateField(null=True, blank=True)
    note = models.TextField(blank=True, default="")
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["contract", "-created_at"], name="hrc_event_contract_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["contract", "kind", "threshold", "end_date"],
                condition=Q(kind__in=[kind.value for kind in ONCE_PER_THRESHOLD_EVENTS]),
                name="hrc_event_once_per_threshold",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} · {self.contract_id}"


__all__ = ["EmploymentContract", "EmploymentContractEvent", "contract_file_path", "contract_file_validators"]
