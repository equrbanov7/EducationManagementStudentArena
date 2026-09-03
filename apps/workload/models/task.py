"""Tapşırıq sənədi və sətirləri (spec §5.1–§5.2).

Modul sərhədi: burada ``apps.*`` importu YOXDUR — registrar/organizations
modellərinə yalnız STRING FK ilə istinad olunur (module_deps qrafında kənar
yaranmır, ``apps/syllabus/models`` naxışı).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import OrderedModel, TimeStampedModel, UUIDModel

from ..constants import (
    ACTIVITY_TOTAL_FIELD,
    CONTACT_TOTAL_FIELDS,
    TOTAL_HOUR_FIELDS,
    DegreeLevel,
    EducationForm,
    RowKind,
    RowReviewStatus,
    Season,
    TaskStatus,
)

_CTX = "workload.model"


class TeachingTask(UUIDModel, TimeStampedModel):
    """Kafedraya verilən İLLİK tədris-pedaqoji tapşırıq (bir il, bir kafedra).

    F3-də sənədi kafedra müdiri özü yaradır (tədris şöbəsi modulu — F1 — hələ
    yoxdur); F1 gələndə eyni sətirlər ``submitted``/``approved`` dövrəsindən
    keçəcək və status kataloqu artıq onları saxlayır.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="teaching_tasks"
    )
    academic_year = models.CharField(
        max_length=20,
        help_text="Tədris ili — «2026/2027» (AcademicPeriod.academic_year konvensiyası).",
    )
    chair = models.ForeignKey(
        "organizations.OrgUnit",
        on_delete=models.PROTECT,
        related_name="teaching_tasks",
        help_text="Kafedra (OrgUnit: chair/department).",
    )
    status = models.CharField(max_length=32, choices=TaskStatus.choices, default=TaskStatus.DRAFT, db_index=True)
    revision = models.PositiveIntegerField(default=0, help_text="Hər qaytarma-göndərmə dövrü artırır (F2).")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_teaching_tasks",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="submitted_teaching_tasks",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    distributed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="distributed_teaching_tasks",
    )
    distributed_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "tədris tapşırığı")
        verbose_name_plural = pgettext_lazy(_CTX, "tədris tapşırıqları")
        ordering = ["-academic_year", "chair__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "academic_year", "chair"],
                name="uniq_teaching_task_year_chair",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "academic_year"]),
            models.Index(fields=["organization", "status"]),
        ]

    def __str__(self):
        return f"{self.chair_id} · {self.academic_year}"

    @property
    def is_editable(self) -> bool:
        from ..constants import EDITABLE_STATUSES

        return self.status in EDITABLE_STATUSES

    @property
    def is_locked(self) -> bool:
        from ..constants import LOCKED_STATUSES

        return self.status in LOCKED_STATUSES


class TeachingTaskRow(UUIDModel, TimeStampedModel, OrderedModel):
    """Tapşırıq sətri — rəsmi Excel şablonunun 21 sütununun 1:1 qarşılığı."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="teaching_task_rows"
    )
    task = models.ForeignKey(TeachingTask, on_delete=models.CASCADE, related_name="rows")
    season = models.CharField(max_length=16, choices=Season.choices, default=Season.FALL, db_index=True)
    period = models.ForeignKey(
        "organizations.AcademicPeriod",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="workload_rows",
        help_text="Semestrə lövbər — offering sinxronu üçün MƏCBURİDİR.",
    )
    subject = models.ForeignKey(
        "registrar.Subject",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="workload_rows",
    )
    subject_text = models.CharField(max_length=255, blank=True, help_text="Kataloqda olmayan fənn / xüsusi sətir adı.")
    row_kind = models.CharField(max_length=16, choices=RowKind.choices, default=RowKind.TEACHING, db_index=True)
    specialty = models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="workload_rows_as_specialty",
    )
    specialty_text = models.CharField(max_length=255, blank=True)
    faculty = models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="workload_rows_as_faculty",
        help_text="Denormalizə — dilim marşrutu (F2); specialty.path-dan törədilir.",
    )
    groups = models.ManyToManyField(
        "organizations.OrgUnit",
        blank=True,
        related_name="workload_rows_as_group",
    )
    groups_text = models.CharField(max_length=255, blank=True, help_text="Birləşmə yazılışı: «036 / 336 F».")
    education_form = models.CharField(
        max_length=16, choices=EducationForm.choices, default=EducationForm.EYANI, db_index=True
    )
    degree_level = models.CharField(
        max_length=16, choices=DegreeLevel.choices, default=DegreeLevel.BACHELOR, db_index=True
    )
    student_count = models.PositiveIntegerField(default=0)
    student_count_text = models.CharField(max_length=100, blank=True, help_text="Birləşmədə «30 / 50».")
    union_count = models.PositiveSmallIntegerField(default=1, help_text="Mühazirə axını (birləşmə) sayı.")
    subgroup_count = models.PositiveSmallIntegerField(default=1, help_text="Qrup və yarımqrupların sayı.")
    lecture_plan = models.PositiveIntegerField(default=0)
    lecture_total = models.PositiveIntegerField(default=0)
    seminar_plan = models.PositiveIntegerField(default=0)
    seminar_total = models.PositiveIntegerField(default=0)
    lab_plan = models.PositiveIntegerField(default=0)
    lab_total = models.PositiveIntegerField(default=0)
    consult_hours = models.PositiveIntegerField(default=0)
    exam_hours = models.PositiveIntegerField(default=0)
    thesis_hours = models.PositiveIntegerField(default=0)
    postgrad_hours = models.PositiveIntegerField(default=0)
    practice_research_hours = models.PositiveIntegerField(default=0)
    practice_production_hours = models.PositiveIntegerField(default=0)
    total_hours = models.PositiveIntegerField(default=0, help_text="Sətir üzrə yekun (servisdə yoxlanılır).")
    credits = models.CharField(max_length=20, blank=True, help_text="Birləşmədə «6 / 7» ola bilər.")
    credits_value = models.PositiveSmallIntegerField(default=0, help_text="Əsas kredit dəyəri (aqreqat üçün).")
    review_status = models.CharField(
        max_length=16, choices=RowReviewStatus.choices, default=RowReviewStatus.PENDING, db_index=True
    )
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "tapşırıq sətri")
        verbose_name_plural = pgettext_lazy(_CTX, "tapşırıq sətirləri")
        ordering = ["task", "season", "order", "created_at"]
        indexes = [
            models.Index(fields=["task", "season"]),
            models.Index(fields=["organization", "subject"]),
        ]

    def __str__(self):
        return self.subject_label

    # ── Göstəriş köməkçiləri ────────────────────────────────────────────────
    @property
    def subject_label(self) -> str:
        if self.subject_id and getattr(self, "subject", None):
            return self.subject.name
        return self.subject_text or "—"

    @property
    def computed_total_hours(self) -> int:
        return sum(int(getattr(self, field, 0) or 0) for field in TOTAL_HOUR_FIELDS)

    @property
    def contact_hours(self) -> int:
        return sum(int(getattr(self, field, 0) or 0) for field in CONTACT_TOTAL_FIELDS)

    def activity_total(self, activity: str) -> int:
        field = ACTIVITY_TOTAL_FIELD.get(activity)
        if not field:
            return 0
        return int(getattr(self, field, 0) or 0)


__all__ = ["TeachingTask", "TeachingTaskRow"]
