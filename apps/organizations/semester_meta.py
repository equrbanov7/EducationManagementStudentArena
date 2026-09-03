"""Semestr açılışının kilid qatı — ``AcademicPeriod`` üçün abstrakt mixin.

Dizayn handoff Mərhələ 2, ekran 07 «Semestr açılışı».

NİYƏ AYRI MODUL? ``organizations/models.py`` 597/600 sətirdir
(``scripts/check_module_size.py`` SOFT_CAP=600) — sahələr birbaşa oraya
yazılsaydı qapı qırmızıya düşərdi. Mixin abstraktdır: öz cədvəli YOXDUR,
sütunlar ``AcademicPeriod``-un öz cədvəlində yaranır.

──────────────────────────────────────────────────────────────────────────────
KİLİD GERİ QAYTARILMIR (handoff ekran 07 + §8 qayda 6)
──────────────────────────────────────────────────────────────────────────────
Kilidlənmiş semestrdə açılış sətirləri dəyişmir. Açmaq üçün AYRICA səlahiyyət
(``semester.unlock``) və ≥20 simvol səbəb tələb olunur; səbəb həm sətirdə
(``lock_reason``), həm də ``core.audit`` yazısında saxlanılır.

``opening_status`` 5 addımlı mərhələ zolağının (stepper) SON tamamlanmış
addımıdır — addımların özü hesablanır (neçə açılış yaradılıb, neçəsinə müəllim
təyin olunub, neçə jurnal açılıb), yalnız «göndərildi» və «kilidləndi» insan
qərarıdır və ona görə SAXLANILIR.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy


class SemesterOpeningStatus(models.TextChoices):
    """Semestrin açılış vəziyyəti — ekran 07 stepper-inin saxlanılan hissəsi."""

    NOT_STARTED = "not_started", pgettext_lazy("organizations.semester_opening", "Başlanmayıb")
    GENERATED = "generated", pgettext_lazy("organizations.semester_opening", "Plandan açılış yaradıldı")
    SENT_TO_CHAIRS = "sent", pgettext_lazy("organizations.semester_opening", "Kafedraya göndərildi")
    LOCKED = "locked", pgettext_lazy("organizations.semester_opening", "Semestr kilidləndi")


class SemesterLockMixin(models.Model):
    """Açılış vəziyyəti + kilid rekvizitləri (abstrakt — öz cədvəli yoxdur)."""

    opening_status = models.CharField(
        max_length=16,
        choices=SemesterOpeningStatus.choices,
        default=SemesterOpeningStatus.NOT_STARTED,
        db_index=True,
        help_text="Semestr açılışının mərhələsi (plandan yaradıldı → kafedraya göndərildi → kilidləndi).",
    )
    locked_at = models.DateTimeField(null=True, blank=True, help_text="Semestrin kilidləndiyi an.")
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="locked_periods",
    )
    lock_reason = models.TextField(blank=True, help_text="Kilid / kilidin açılması səbəbi (≥20 simvol).")

    class Meta:
        abstract = True

    @property
    def is_locked(self) -> bool:
        return self.locked_at is not None


__all__ = ["SemesterLockMixin", "SemesterOpeningStatus"]
