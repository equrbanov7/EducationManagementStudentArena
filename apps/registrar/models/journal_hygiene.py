"""«Jurnal təmizliyi» qərar jurnalı — APPEND-ONLY (sahib 2026-10-10).

Sahib: «jurnalda çıxarılmış, yəni oxumayan çıxmış amma jurnalda adı qalan tələbələri tapmaq; qrupdakı
tələbələrə keçmədiyi dərs düşüb sistemdən nəticələrinə — onu ordan təyin edib çıxarmaq».

Alət qeydiyyatı SİLMİR — yalnız statusunu dəyişir (``enrolled → suspended`` / ``→ dropped``). Hər
dəyişiklik burada bir sətir yazır: hansı qeydiyyat, hansı statusdan hansına, hansı kateqoriya və sübut
(yazıldığı andakı sübut snapshot-u + sha256 izi), kim, niyə. «Bərpa et» YALNIZ bu jurnaldakı qərarı
geri qaytarır: status əvvəlki dəyərə dönür, sətirdə ``reverted_*`` sahələri BİR DƏFƏ doldurulur.

DB qoruyucusu (miqrasiya ``0086``): DELETE qadağandır; UPDATE yalnız (1) bir dəfəlik geri qaytarma
sahələrinə və ya (2) hesab silinəndə aktor FK-larının NULL-a düşməsinə (Django ``SET_NULL``
emulyasiyası) icazə verir. Ad snapshot-ları (``*_name``) dəyişmir.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

#: Səbəbin minimum uzunluğu — handoff §8/6 (≥20 simvol, audit üçün).
HYGIENE_REASON_MIN_LENGTH = 20

#: Geri qaytarma zamanı dəyişə bilən YEGANƏ sahələr (DB trigger-i ilə eyni siyahı).
REVERT_FIELDS = ("reverted_at", "reverted_by", "reverted_by_name", "revert_reason", "updated_at")


class HygieneCategory(models.TextChoices):
    LEFT_STUDENT = "left_student", pgettext_lazy("registrar.journal_hygiene", "Ayrılmış tələbə")
    EMPTY_SUBJECT = "empty_subject", pgettext_lazy("registrar.journal_hygiene", "Boş fənn")
    #: Qrupda heç kimin imtahan («çıxış») balı yoxdur — fənn keçirilməyib (sahib 2026-10-11).
    NOT_HELD = "not_held", pgettext_lazy("registrar.journal_hygiene", "Keçirilməyən fənn")


class JournalHygieneDecision(UUIDModel, TimeStampedModel):
    """Bir qeydiyyatın «Jurnal təmizliyi» qərarı (yazıldıqdan sonra yalnız bir dəfə geri qaytarıla bilir)."""

    # `organization` tək indeksi lazım deyil: (organization, -created_at) onu prefiks kimi örtür.
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="journal_hygiene_decisions",
        db_index=False,
    )
    enrollment = models.ForeignKey(
        "registrar.Enrollment", on_delete=models.PROTECT, related_name="hygiene_decisions", db_index=False
    )
    #: Bir tətbiq əməli (≤500 sətir) — tarixçədə qrup halında göstərilir, audit sətri ilə bağlanır.
    batch = models.UUIDField()
    category = models.CharField(max_length=24, choices=HygieneCategory.choices)
    #: Əsas səbəb kodu: ayrılmış tələbədə akademik vəziyyət, boş fənndə mənbə etiketi.
    reason_code = models.CharField(max_length=32)
    from_status = models.CharField(max_length=16)
    to_status = models.CharField(max_length=16)
    evidence = models.JSONField(default=dict, help_text="Qərar anındakı sübut snapshot-u (saylar, etiketlər).")
    evidence_digest = models.CharField(max_length=64, help_text="Sübut snapshot-unun sha256 izi.")
    reason = models.TextField(help_text="Qərarın səbəbi — ən azı 20 simvol.")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_by_name = models.CharField(max_length=200, blank=True, default="")

    # ── Geri qaytarma (bir dəfə) ──────────────────────────────────────────────
    reverted_at = models.DateTimeField(null=True, blank=True)
    reverted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reverted_by_name = models.CharField(max_length=200, blank=True, default="")
    revert_reason = models.TextField(blank=True, default="")

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = pgettext_lazy("registrar.model.journal_hygiene.meta", "journal hygiene decision")
        verbose_name_plural = pgettext_lazy("registrar.model.journal_hygiene.meta", "journal hygiene decisions")
        indexes = [
            models.Index(fields=["organization", "-created_at"], name="reg_hygiene_org_created"),
            models.Index(fields=["enrollment", "-created_at"], name="reg_hygiene_enrollment"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(category__in=[choice.value for choice in HygieneCategory]),
                name="reg_hygiene_category_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(to_status__in=["suspended", "dropped"]),
                name="reg_hygiene_to_status_valid",
            ),
            # Geri qaytarma ya tam yoxdur, ya da vaxtı + səbəbi ilə birlikdədir.
            models.CheckConstraint(
                condition=(
                    models.Q(reverted_at__isnull=True, revert_reason="")
                    | (models.Q(reverted_at__isnull=False) & ~models.Q(revert_reason=""))
                ),
                name="reg_hygiene_revert_complete",
            ),
        ]

    def __str__(self):
        return f"{self.category}<{self.enrollment_id}> {self.from_status}→{self.to_status}"

    @property
    def is_reverted(self) -> bool:
        return self.reverted_at is not None

    def save(self, *args, **kwargs):
        """Tətbiq qatının qapısı (PG trigger-i əsasdır): yeni sətir və ya yalnız geri qaytarma sahələri."""
        if not self._state.adding:
            update_fields = kwargs.get("update_fields")
            if not update_fields or not set(update_fields) <= set(REVERT_FIELDS):
                raise ValidationError("Journal hygiene decisions are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Journal hygiene decisions cannot be deleted.")


__all__ = [
    "HYGIENE_REASON_MIN_LENGTH",
    "REVERT_FIELDS",
    "HygieneCategory",
    "JournalHygieneDecision",
]
