"""Jurnalın seminar alt qrupu — nömrə + ad + reyestr alt qrupu (sahib 2026-11-07).

Sahib: «mühazirədə 234 K bir göstərsin; seminarda 234 K1 və 234 K2-ni ayrı göstərsin, dərs əlavə edəndə onu
seçsin, ad olaraq görsün». Bir jurnal (ana qrup) qalır; tələbənin seminar alt qrupu ``Enrollment.seminar_group``,
dərsinki ``Lesson.seminar_group`` (nömrə). Bu cədvəl qrupun MÖVCUDLUĞUNU, görünən ADINI («234 K1») və mənbə reyestr
alt qrupunu saxlayır. Qaydalar: :mod:`apps.registrar.seminar_groups`.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

from .lab_group import LAB_GROUP_MAX_NUMBER, LAB_GROUP_NAME_MAX_LENGTH


class SeminarGroup(UUIDModel, TimeStampedModel):
    """Bir açılışın bir seminar alt qrupu (açılış × nömrə üzrə BİR sətir)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="seminar_groups", db_index=False
    )
    offering = models.ForeignKey("registrar.CourseOffering", on_delete=models.CASCADE, related_name="seminar_groups")
    number = models.PositiveSmallIntegerField(
        help_text="Qrup nömrəsi (Enrollment.seminar_group / Lesson.seminar_group)."
    )
    name = models.CharField(
        max_length=LAB_GROUP_NAME_MAX_LENGTH, blank=True, default="", help_text="Görünən ad; boş = «Seminar-N»."
    )
    unit = models.ForeignKey(
        "organizations.OrgUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Mənbə reyestr alt qrupu (məs. «234 K1»); boş — əl ilə yaradılıb.",
    )

    class Meta:
        ordering = ["offering_id", "number"]
        verbose_name = pgettext_lazy("registrar.model.seminar_group.meta", "seminar alt qrupu")
        verbose_name_plural = pgettext_lazy("registrar.model.seminar_group.meta", "seminar alt qrupları")
        constraints = [
            models.UniqueConstraint(fields=["offering", "number"], name="reg_semgroup_offering_number_uniq"),
            models.CheckConstraint(
                condition=models.Q(number__gte=1, number__lte=LAB_GROUP_MAX_NUMBER), name="reg_semgroup_number_range"
            ),
        ]

    def __str__(self):
        return f"seminar<{self.offering_id}·{self.number}> {self.name}".rstrip()
