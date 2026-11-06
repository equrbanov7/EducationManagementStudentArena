"""Jurnalın laboratoriya qrupu — nömrə + istəyə bağlı ad (sahib 2026-11-06: «lab qruplarını yaratmaq üçün yer olsun»).

Üzvlük DƏYİŞMİR: tələbənin qrupu ``Enrollment.lab_group``, dərsin qrupu ``Lesson.lab_group`` (nömrə) qalır.
Bu cədvəl yalnız iki şeyi saxlayır:

* qrupun MÖVCUDLUĞU — hələ üzvü olmayan təzə «Lab-3» də jurnalda görünsün (dərs modalı onu təklif etsin);
* görünən AD — boşdursa «Lab-N».

Köhnə data (``apply_lab_groups_20261106`` — Lab-1 / Lab-2, sətirsiz) dəyişmədən işləyir: jurnalın qrupları
``LabGroup`` sətirləri ∪ aktiv siyahıdakı ``lab_group`` dəyərləridir (:func:`apps.registrar.lab_groups.offering_groups`).
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

#: Qrup adının uzunluğu (qrid başlığındakı nişana sığsın).
LAB_GROUP_NAME_MAX_LENGTH = 40
#: Nömrə tavanı — ``lab_groups.MAX_LAB_GROUP`` ilə eyni (DB CHECK).
LAB_GROUP_MAX_NUMBER = 9


class LabGroup(UUIDModel, TimeStampedModel):
    """Bir açılışın bir laboratoriya qrupu (açılış × nömrə üzrə BİR sətir)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="lab_groups", db_index=False
    )
    offering = models.ForeignKey("registrar.CourseOffering", on_delete=models.CASCADE, related_name="lab_groups")
    number = models.PositiveSmallIntegerField(help_text="Qrup nömrəsi (Enrollment.lab_group / Lesson.lab_group).")
    name = models.CharField(
        max_length=LAB_GROUP_NAME_MAX_LENGTH, blank=True, default="", help_text="Görünən ad; boş = «Lab-N»."
    )

    class Meta:
        ordering = ["offering_id", "number"]
        verbose_name = pgettext_lazy("registrar.model.lab_group.meta", "laboratoriya qrupu")
        verbose_name_plural = pgettext_lazy("registrar.model.lab_group.meta", "laboratoriya qrupları")
        constraints = [
            models.UniqueConstraint(fields=["offering", "number"], name="reg_labgroup_offering_number_uniq"),
            models.CheckConstraint(
                condition=models.Q(number__gte=1, number__lte=LAB_GROUP_MAX_NUMBER), name="reg_labgroup_number_range"
            ),
        ]

    def __str__(self):
        return f"lab<{self.offering_id}·{self.number}> {self.name}".rstrip()
