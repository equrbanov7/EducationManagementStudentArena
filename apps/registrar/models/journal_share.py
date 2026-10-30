"""Bölünmüş jurnal — açılışın bir hissəsi (dərs növü / tələbələr) başqa müəllimə (sahib 2026-10-26).

Sahib: «Fənn 2 müəllim arasında bölünübsə mühazirəçi mühazirəni, seminarçı yalnız öz ballarını görsün.»
Xarici dil SƏVİYYƏ jurnalları: «qrupda hər səviyyədən tələbə ola bilər — müəllim jurnalını açanda yalnız öz
tələbələrini görsün, hamını yox. Nə tələbə artıq şey görsün, nə də müəllimin jurnalı itsin.»

Köhnə sistemdə hər müəllimin ÖZ jurnalı var idi (mühazirəçinin, seminarçının; səviyyə jurnalı bir neçə qrupu
əhatə edib yalnız o səviyyənin tələbələrini daşıyırdı). Köçürmə onları BİR açılışa birləşdirdi
(``CourseOffering`` — fənn × dövr × qrup, bir ``instructor``). Bu sətir həmin köhnə bölgünü bərpa edir:

* ``kinds`` — müəllimin dərs növləri (``LessonKind`` dəyərləri); BOŞ siyahı = bütün növlər;
* ``enrollments`` — müəllimin tələbələri; BOŞ = açılışın bütün tələbələri.

Hesablama (kim nəyi görür, nəyi yazır) :mod:`apps.registrar.journal_shares`-dadır. Bal riyaziyyatı
DƏYİŞMİR — yalnız göstərilən/yazıla bilən sətir və sütunlar daralır.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel


class JournalShareSource(models.TextChoices):
    LEGACY = "legacy", pgettext_lazy("registrar.journal_share", "Köhnə sistem")
    MANUAL = "manual", pgettext_lazy("registrar.journal_share", "Əl ilə")
    WORKLOAD = "workload", pgettext_lazy("registrar.journal_share", "Dərs yükü")


class JournalShare(UUIDModel, TimeStampedModel):
    """Bir müəllimin bölünmüş jurnaldakı payı (açılış × müəllim üzrə bir AKTİV sətir)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="journal_shares", db_index=False
    )
    offering = models.ForeignKey("registrar.CourseOffering", on_delete=models.CASCADE, related_name="shares")
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="journal_shares")
    #: ``LessonKind`` dəyərlərinin alt çoxluğu; boş = bütün növlər.
    kinds = models.JSONField(default=list, blank=True)
    #: Müəllimin tələbələri; boş = açılışın bütün tələbələri.
    enrollments = models.ManyToManyField("registrar.Enrollment", blank=True, related_name="journal_shares")
    source = models.CharField(max_length=16, choices=JournalShareSource.choices, default=JournalShareSource.MANUAL)
    #: İdarə əmrinin paketi (``shares-YYYYMMDD-HHMMSS-xxxx``) — ``--undo`` bununla geri qaytarır.
    batch = models.CharField(max_length=32, blank=True, default="", db_index=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["offering_id", "created_at"]
        verbose_name = pgettext_lazy("registrar.model.journal_share.meta", "jurnal payı")
        verbose_name_plural = pgettext_lazy("registrar.model.journal_share.meta", "jurnal payları")
        indexes = [models.Index(fields=["organization", "teacher"], name="reg_share_org_teacher")]
        constraints = [
            models.UniqueConstraint(
                fields=["offering", "teacher"], condition=models.Q(is_active=True), name="reg_share_active_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(source__in=[choice.value for choice in JournalShareSource]),
                name="reg_share_source_valid",
            ),
        ]

    def __str__(self):
        return f"share<{self.offering_id}·{self.teacher_id}> {','.join(self.kinds or []) or '*'}"
