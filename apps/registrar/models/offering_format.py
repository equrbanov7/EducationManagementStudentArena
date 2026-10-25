"""Açılışın FORMATI — adi (qrup, semestr boyu) və ya İNTENSİV kurs (sahib 2026-10-25).

Sahib: «İntensiv dediyimiz — dərs saatı az olur, 1-2 nəfər üçün açılır, müəllim təyin olunur, tez bitir …
müəllim 10 saatlıq dərsi 5 günə də keçə bilər — orada sərbəstlikdir». Rəsmi ad TƏKDİR: «İntensiv»
(«fərdi dərs» eyni anlayışdır, ayrıca növ yoxdur).

YENİ MODEL YOXDUR — intensiv kurs adi :class:`CourseOffering`-dir, yalnız:

* ``course_format = "intensive"``;
* ``group`` BOŞDUR (tələbələr adla seçilir, qrupları fərqli ola bilər — hər qeydiyyat «alt qrupdan əlavə»
  provenansı ilə: ``Enrollment.source_group`` tələbənin öz qrupudur, bax ``apps.registrar.intensive``);
* ``starts_on`` / ``ends_on`` — kursun öz tarix aralığı (semestrdən qısa); dərs tarixi bu aralıqda olmalıdır;
* ``lesson_hours`` — kursun ümumi saatı (məs. 10): saat həddi (#6) və «Kurs tamamlandı» göstəricisi ondan;
* ``format_note`` — açılışın səbəbi (sərbəst mətn: yenidən tədris, akademik fərq …).

NİYƏ AYRI MODUL? ``models/academic.py`` modul ölçüsü qapısına yaxındır — sahələr burada abstrakt bazada
tərif olunur (``admission_meta`` naxışı). ``db_default`` QƏSDƏNDİR: cədvələ xam SQL INSERT-lər də var
(köçürmə / RLS testləri) — onlar yeni NOT NULL sütunu tanımır.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import pgettext_lazy

_CTX = "registrar.course_format"


class CourseFormat(models.TextChoices):
    REGULAR = "regular", pgettext_lazy(_CTX, "Adi")
    INTENSIVE = "intensive", pgettext_lazy(_CTX, "İntensiv")


class OfferingFormatFields(models.Model):
    course_format = models.CharField(
        max_length=16,
        choices=CourseFormat.choices,
        default=CourseFormat.REGULAR,
        db_default=CourseFormat.REGULAR,
        db_index=True,
        help_text="«intensive» — qrupsuz, öz tarix aralığı olan qısa kurs (1–2 tələbə).",
    )
    starts_on = models.DateField(null=True, blank=True, help_text="İntensiv kursun başlama tarixi.")
    ends_on = models.DateField(null=True, blank=True, help_text="İntensiv kursun bitmə tarixi.")
    format_note = models.CharField(
        max_length=255, blank=True, db_default="", help_text="İntensiv kursun açılma səbəbi (sərbəst mətn)."
    )

    class Meta:
        abstract = True

    @property
    def is_intensive(self) -> bool:
        return self.course_format == CourseFormat.INTENSIVE


def offering_format_constraints() -> list:
    """``CourseOffering.Meta.constraints``-ə əlavə: intensiv → qrupsuz + iki tarix + düzgün sıra."""
    intensive = models.Q(course_format=CourseFormat.INTENSIVE)
    return [
        models.CheckConstraint(
            condition=~intensive | models.Q(group__isnull=True, starts_on__isnull=False, ends_on__isnull=False),
            name="offering_intensive_shape",
        ),
        models.CheckConstraint(
            condition=models.Q(starts_on__isnull=True)
            | models.Q(ends_on__isnull=True)
            | models.Q(starts_on__lte=models.F("ends_on")),
            name="offering_dates_ordered",
        ),
    ]


__all__ = ["CourseFormat", "OfferingFormatFields", "offering_format_constraints"]
