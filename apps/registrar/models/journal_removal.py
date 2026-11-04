"""Jurnaldan çıxarılmanın SƏBƏBİ — APPEND-ONLY qeyd (sahib 2026-11-04).

Sahib: «Jurnalda hansısa tələbəni çıxardarkən səbəb seçmə olsun … uzaqlaşdırmadan əlavə seçim də olsun ki,
bəlkə hansısa sənəd gətirib bu fənn əvəz olunub o tələbədə. Daha sonra mən harada isə onda baxa bilim o tip
hadisələrə — nəyə görə olub.»

Hər jurnaldan çıxarılma əməli («Fəndən azad et», alt qrupdan əlavənin «Çıxar»-ı, xarici nəticənin tanınması ilə
avtomatik azadlıq) burada BİR sətir yazır: hansı qeydiyyat, hansı əməl, hansı səbəb kateqoriyası, qeyd, kim.
Əməlin özü (status dəyişikliyi, qərar jurnalı, audit) öz modulundadır — bu cədvəl yalnız «niyə» sualına cavabdır
və RİM-in mərkəzi «Jurnaldan çıxarılmalar» siyahısının mənbəyidir.

DB qoruyucusu (miqrasiya ``0114``): DELETE qadağandır; UPDATE yalnız hesab silinəndə ``actor_id``-nin NULL-a
düşməsinə (Django ``SET_NULL`` emulyasiyası) icazə verir.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

_CTX = "registrar.journal_removal"

#: Qeydin tavanı (modal textarea ilə eyni).
REMOVAL_NOTE_MAX_LENGTH = 1000


class RemovalReason(models.TextChoices):
    """Çıxarılmanın səbəb kateqoriyası (modalın seçim siyahısı)."""

    SUSPENSION = "suspension", pgettext_lazy(_CTX, "Uzaqlaşdırma")
    SUBJECT_SUBSTITUTION = "subject_substitution", pgettext_lazy(_CTX, "Fənn əvəzlənməsi (sənəd təqdim edib)")
    CREDIT_RECOGNITION = "credit_recognition", pgettext_lazy(_CTX, "Kredit tanınması / köçürmə")
    ADDED_BY_MISTAKE = "added_by_mistake", pgettext_lazy(_CTX, "Səhv əlavə olunub")
    GROUP_TRANSFER = "group_transfer", pgettext_lazy(_CTX, "Başqa qrupa / alt qrupa keçid")
    OTHER = "other", pgettext_lazy(_CTX, "Digər")


class RemovalAction(models.TextChoices):
    """Çıxarılmanın hansı əməllə edildiyi."""

    SUBJECT_EXEMPT = "subject_exempt", pgettext_lazy(_CTX, "Fəndən azad")
    GUEST_REMOVE = "guest_remove", pgettext_lazy(_CTX, "Alt qrupdan əlavə geri götürüldü")


class JournalRemoval(UUIDModel, TimeStampedModel):
    """Bir qeydiyyatın jurnaldan çıxarılma səbəbi (yazıldıqdan sonra dəyişmir)."""

    # `organization` tək indeksi lazım deyil: (organization, -created_at) onu prefiks kimi örtür.
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="journal_removals", db_index=False
    )
    enrollment = models.ForeignKey(
        "registrar.Enrollment", on_delete=models.PROTECT, related_name="removal_reasons", db_index=False
    )
    action = models.CharField(max_length=24, choices=RemovalAction.choices)
    reason = models.CharField(max_length=32, choices=RemovalReason.choices)
    note = models.TextField(blank=True, default="")
    #: «Fəndən azad» əməlinin qərar sətri — «Bərpa et» vəziyyəti buradan oxunur.
    hygiene_decision = models.ForeignKey(
        "registrar.JournalHygieneDecision",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="removal_reasons",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    actor_name = models.CharField(max_length=200, blank=True, default="")

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = pgettext_lazy("registrar.model.journal_removal.meta", "journal removal")
        verbose_name_plural = pgettext_lazy("registrar.model.journal_removal.meta", "journal removals")
        indexes = [
            models.Index(fields=["organization", "-created_at"], name="reg_removal_org_created"),
            models.Index(fields=["enrollment", "-created_at"], name="reg_removal_enrollment"),
            models.Index(fields=["organization", "reason"], name="reg_removal_org_reason"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(reason__in=[choice.value for choice in RemovalReason]),
                name="reg_removal_reason_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(action__in=[choice.value for choice in RemovalAction]),
                name="reg_removal_action_valid",
            ),
            # «Digər» qeydsiz yazılmır (modal + servis + DB eyni qayda).
            models.CheckConstraint(
                condition=~models.Q(reason="other", note=""),
                name="reg_removal_other_has_note",
            ),
        ]

    def __str__(self):
        return f"{self.action}<{self.enrollment_id}> {self.reason}"

    def save(self, *args, **kwargs):
        """Tətbiq qatının qapısı (PG trigger-i əsasdır): yalnız yeni sətir."""
        if not self._state.adding:
            raise ValidationError("Journal removal records are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Journal removal records cannot be deleted.")


__all__ = [
    "REMOVAL_NOTE_MAX_LENGTH",
    "JournalRemoval",
    "RemovalAction",
    "RemovalReason",
]
