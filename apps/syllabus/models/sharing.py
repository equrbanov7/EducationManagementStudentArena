"""Bir sillabus — bir neçə jurnal (sahib 2026-10-27, «öz yerində»).

Sahib: «müəllim köhnə jurnalda o sillabusu 2 qrup üçün istifadə edib; jurnalı aktivləşdirərkən indi o bir qrup
üçün görünür, 2-ci üçün yox … köhnədən gələndə elə olsun — bir sillabus» və «müəllim istəsə eynisini istifadə
etsin eyni qrupa öz yerində» (məsələn potok dərsləri).

``SyllabusShare`` — dosyenin ÖZ açılışından (``Syllabus.offering``) başqa, həmin sillabusu ÖZ YERİNDƏ istifadə
edən açılış (jurnal). Surət YOXDUR: məzmun, versiyalar, təsdiq və redaktə dosyenin özündədir, ona görə təsdiq
vəziyyəti, tamamlanma faizi və həftəlik plan bütün bağlı jurnallar üçün BİRDİR.

* Bir açılış ən çox BİR paylaşılan sillabusa bağlanır (``uniq_syllabus_share_offering``); açılışın ÖZ dosyesi
  varsa o üstündür (``syllabus_for_offering`` pillə sırası: öz → paylaşılan → fənn+semestr → baza).
* Paylaşılan sillabus yalnız açılışın müəllimi dosyenin müəllifi (və ya öz açılışının müəllimi) olanda
  tətbiq olunur — başqa müəllimin sillabusu heç vaxt götürülmür (qaydalar ``services/sharing.py``-dadır).
* ``reused_from`` (2026-10-08, «bağla») ayrıca dosye + eyni nüsxədir; bu model isə TƏK dosyedir.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

_CTX = "syllabus.model"


class ShareSource(models.TextChoices):
    """Paylaşımın necə yarandığı."""

    TEACHER = "teacher", pgettext_lazy(_CTX, "Müəllimin seçimi")
    LEGACY = "legacy", pgettext_lazy(_CTX, "Köhnə sistem (bir sillabus bir neçə jurnalda)")


class SyllabusShare(UUIDModel, TimeStampedModel):
    """Sillabusu ÖZ YERİNDƏ istifadə edən əlavə açılış (jurnal)."""

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="syllabus_shares",
        db_index=False,  # ``syllabus_share_org_syl`` (organization, syllabus) prefiksi örtür
    )
    syllabus = models.ForeignKey("syllabus.Syllabus", on_delete=models.CASCADE, related_name="shares")
    offering = models.ForeignKey(
        "registrar.CourseOffering",
        on_delete=models.CASCADE,
        related_name="syllabus_shares",
        db_index=False,  # ``uniq_syllabus_share_offering`` indeksi örtür (dublikat indeks yox)
        help_text="Sillabusu öz yerində istifadə edən açılış (jurnal) — dosyenin öz açılışı DEYİL.",
    )
    source = models.CharField(max_length=16, choices=ShareSource.choices, default=ShareSource.TEACHER)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "paylaşılan sillabus")
        verbose_name_plural = pgettext_lazy(_CTX, "paylaşılan sillabuslar")
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["offering"], name="uniq_syllabus_share_offering"),
            models.CheckConstraint(
                condition=models.Q(source__in=["teacher", "legacy"]), name="syllabus_share_source_valid"
            ),
        ]
        indexes = [models.Index(fields=["organization", "syllabus"], name="syllabus_share_org_syl")]

    def __str__(self):
        return f"{self.syllabus_id} → {self.offering_id}"


__all__ = ["ShareSource", "SyllabusShare"]
