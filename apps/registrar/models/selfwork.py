"""Sərbəst iş modelləri — mövzu (sillabus slotu) + tələbə işarəsi / balı.

``grading.py`` modul-ölçü büdcəsinə (600 sətir) görə bölünüb; adlar oradan
(və ``apps.registrar.models``-dən) re-eksport olunur — sxem dəyişmir, köhnə
importlar işləyir.

BAL MODELİ (2026-09-25, sahib: «sillabusda seçilmiş struktur: 2 × 5 / 1 × 10 /
10 × 1; maksimum 10, ikinci dəfə bal yoxdur»):

* ``SelfWorkTopic.max_points`` — mövzunun (sillabus slotunun) tavanı: 1 (köhnə
  çeklist və 10 × 1), 5 (2 × 5) və ya 10 (1 × 10). ``slot_index`` — sillabus
  slotu (1…N); köhnə çeklist mövzusunda boşdur.
* ``SelfWorkMark.points`` — real bal (``0 < points ≤ max_points``); boşdursa
  işarə çeklistdir.

EFFEKTİV BAL (TƏK qayda — :mod:`apps.registrar.selfwork_points`)::

    points  varsa → points
    yoxdursa      → topic.max_points  (done=True)  /  0  (done=False)

Köhnə datada (``max_points=1``, ``points=NULL``) bu, ƏVVƏLKİ «təhvil sayı»
ilə eynidir — heç bir tələbənin rəqəmi dəyişmir.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import pgettext_lazy

from core.models import OrderedModel, TimeStampedModel, UUIDModel

from ..reference_identity import ReferenceIdentityValidationMixin
from .academic import CourseOffering, Enrollment

#: Sərbəst işin universitet siyasəti ilə ümumi balı (``apps.syllabus`` —
#: ``SELFWORK_TOTAL_SCORE``; iki sabitin bərabərliyi testlə kilidlənib).
SELFWORK_TOTAL_POINTS = 10

_CTX = "registrar.selfwork"


class SelfWorkSource(models.TextChoices):
    """Balın mənbəyi: jurnalın öz lövhəsi və ya «Fənn qovluğu» (müəllim qiymətləndirməsi)."""

    JOURNAL = "journal", pgettext_lazy(_CTX, "Jurnal")
    SUBJECT_FOLDER = "subject_folder", pgettext_lazy(_CTX, "Fənn qovluğu")


class SelfWorkTopic(ReferenceIdentityValidationMixin, UUIDModel, TimeStampedModel, OrderedModel):
    """Sərbəst iş mövzusu (offering üzrə sıralı siyahı; struktur varsa sillabus slotu)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="self_work_topics"
    )
    offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name="self_work_topics")
    title = models.CharField(max_length=255)
    # ``db_default`` — ORM-dən keçməyən xam INSERT (legacy/repair alətləri, köhnə
    # kodun deploy pəncərəsi) sütunu buraxsa belə köhnə çeklist semantikası alınır
    # (bax registrar.0068 — eyni naxış).
    max_points = models.PositiveSmallIntegerField(
        default=1,
        db_default=1,
        help_text="Mövzunun maksimum balı: 1 (çeklist / 10 × 1), 5 (2 × 5), 10 (1 × 10).",
    )
    slot_index = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Sillabusun sərbəst iş slotu (1…N); köhnə çeklist mövzusunda boşdur.",
    )

    objects = models.Manager()

    class Meta:
        ordering = ["offering", "order", "created_at"]
        verbose_name = pgettext_lazy("registrar.model.selfwork_topic.meta", "independent work topic")
        verbose_name_plural = pgettext_lazy("registrar.model.selfwork_topic.meta", "independent work topics")
        indexes = [models.Index(fields=["organization", "offering"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(max_points__gte=1) & Q(max_points__lte=SELFWORK_TOTAL_POINTS),
                name="selfwork_topic_max_points_range",
            ),
            models.CheckConstraint(
                condition=Q(slot_index__isnull=True) | (Q(slot_index__gte=1) & Q(slot_index__lte=SELFWORK_TOTAL_POINTS)),
                name="selfwork_topic_slot_index_range",
            ),
            # Slot → mövzu xəritəsi SABİTDİR: fənn qovluğu «Sərbəst iş 2»-ni həmişə
            # eyni mövzuya yazır; paralel struktur qurulması dublikat yarada bilməz.
            models.UniqueConstraint(
                fields=["offering", "slot_index"],
                condition=Q(slot_index__isnull=False),
                name="uniq_selfwork_topic_offering_slot",
            ),
        ]

    def __str__(self):
        return f"{self.offering_id} · {self.title[:40]}"


class SelfWorkMark(ReferenceIdentityValidationMixin, UUIDModel, TimeStampedModel):
    """Bir tələbənin bir sərbəst iş mövzusu üzrə təhvil işarəsi (1/0) və ya balı."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="self_work_marks"
    )
    topic = models.ForeignKey(SelfWorkTopic, on_delete=models.CASCADE, related_name="marks")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="self_work_marks")
    done = models.BooleanField(default=False)
    points = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Real bal (0 < bal ≤ mövzunun max balı); boşdursa işarə çeklistdir.",
    )
    source = models.CharField(
        max_length=16,
        choices=SelfWorkSource.choices,
        default=SelfWorkSource.JOURNAL,
        db_default="journal",
        help_text="Balın mənbəyi — fənn qovluğundan gələn bal jurnalda yalnız sənədli düzəlişlə dəyişir.",
    )
    source_ref = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_default="",
        help_text="Mənbə istinadı (məs. «subject_folder.submission:<uuid>») — idempotentlik + audit.",
    )
    graded_at = models.DateTimeField(null=True, blank=True)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.selfwork_mark.meta", "independent work mark")
        verbose_name_plural = pgettext_lazy("registrar.model.selfwork_mark.meta", "independent work marks")
        constraints = [
            models.UniqueConstraint(fields=["topic", "enrollment"], name="uniq_selfwork_topic_enrollment"),
            models.CheckConstraint(
                condition=Q(points__isnull=True) | (Q(points__gt=0) & Q(points__lte=SELFWORK_TOTAL_POINTS)),
                name="selfwork_mark_points_range",
            ),
            # Bal = təhvil: ``done=False`` sətri bal daşıya bilməz («0 düşmür»).
            models.CheckConstraint(
                condition=Q(points__isnull=True) | Q(done=True),
                name="selfwork_mark_points_imply_done",
            ),
            models.CheckConstraint(
                condition=Q(source__in=[choice.value for choice in SelfWorkSource]),
                name="selfwork_mark_source_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "enrollment"]),
            # «Təhvil verilmiş sərbəst iş sayı» aqreqatı (akademik-qeyd icmalı,
            # ``accounts.academic_records``) ``WHERE done AND enrollment_id IN (…)
            # GROUP BY enrollment_id`` şəklindədir — org-səviyyəli çağırışda
            # (7 700 tələbə) mövcud indekslərin heç biri onu ÖRTMÜRDÜ
            # (2026-09-02 performans auditi, F3).
            models.Index(fields=["enrollment", "done"], name="selfwork_enrollment_done"),
        ]

    def __str__(self):
        value = self.points if self.points is not None else int(self.done)
        return f"{self.topic_id} · {self.enrollment_id} = {value}"
