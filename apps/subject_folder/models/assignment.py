"""Qovluğun qruplara (fənn açılışlarına) təyinatı və tapşırıq son tarixləri.

Auditoriya = təyin olunmuş açılışın ``Enrollment(status=ENROLLED)`` sətirləri:
alt qrupdan əlavə olunmuş (guest) tələbə DAXİLDİR, köçürülmüş (``dropped`` +
``superseded_by``) tələbə DAXİL DEYİL.

Sərbəst iş balı jurnalda açılış × tələbə üzrə cəmi 10-dur. Bir açılışa bir neçə
qovluq təyin oluna bilər (məs. mühazirə və seminar müəllimi), amma sərbəst işi
YALNIZ BİRİ qiymətləndirir (``grades_selfwork``) — əks halda tələbə eyni
sillabus slotunu iki qovluqda görər və cəm 10-u keçərdi. DB-də açılış üzrə
aktiv ``grades_selfwork`` təyinatı UNİKALDIR.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

from ..constants import LatePolicy
from .folder import SubjectFolder
from .tasks import FolderTask

_CTX = "subject_folder.model"


class FolderAssignment(UUIDModel, TimeStampedModel):
    """Qovluq → fənn açılışı (qrup) təyinatı."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="subject_folder_assignments"
    )
    folder = models.ForeignKey(SubjectFolder, on_delete=models.CASCADE, related_name="assignments")
    offering = models.ForeignKey(
        "registrar.CourseOffering", on_delete=models.PROTECT, related_name="subject_folder_assignments"
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    assigned_at = models.DateTimeField()
    syllabus_version_ref = models.UUIDField(
        null=True, blank=True, help_text="Təyin anında açılışın TƏSDİQLƏNMİŞ sillabus versiyası (snapshot)."
    )
    selfwork_option = models.CharField(
        max_length=8, blank=True, default="", help_text="Təyin anında açılışın sillabusundakı sərbəst iş strukturu."
    )
    grades_selfwork = models.BooleanField(
        default=True, help_text="Bu təyinat açılışın sərbəst işini qiymətləndirirmi (açılış üzrə yalnız biri)."
    )
    is_active = models.BooleanField(default=True, db_index=True)
    unassigned_at = models.DateTimeField(null=True, blank=True)
    unassigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "qovluq təyinatı")
        verbose_name_plural = pgettext_lazy(_CTX, "qovluq təyinatları")
        ordering = ["folder", "assigned_at"]
        constraints = [
            models.UniqueConstraint(fields=["folder", "offering"], name="sf_assignment_uniq_folder_offering"),
            models.UniqueConstraint(
                fields=["offering"],
                condition=Q(is_active=True, grades_selfwork=True),
                name="sf_assignment_one_selfwork_grader",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "offering", "is_active"], name="sf_assignment_org_offering"),
        ]

    def __str__(self):
        return f"{self.folder_id} → {self.offering_id}"


class TaskDeadline(UUIDModel, TimeStampedModel):
    """Bir təyinatda bir tapşırığın açılma/son tarixi və gecikmə siyasəti."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="subject_folder_deadlines"
    )
    assignment = models.ForeignKey(FolderAssignment, on_delete=models.CASCADE, related_name="deadlines")
    task = models.ForeignKey(FolderTask, on_delete=models.CASCADE, related_name="deadlines")
    opens_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    late_policy = models.CharField(max_length=8, choices=LatePolicy.choices, default=LatePolicy.NONE)
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "tapşırıq son tarixi")
        verbose_name_plural = pgettext_lazy(_CTX, "tapşırıq son tarixləri")
        constraints = [
            models.UniqueConstraint(fields=["assignment", "task"], name="sf_deadline_uniq_assignment_task"),
            models.CheckConstraint(
                condition=Q(opens_at__isnull=True) | Q(due_at__isnull=True) | Q(opens_at__lt=F("due_at")),
                name="sf_deadline_opens_before_due",
            ),
        ]
        indexes = [models.Index(fields=["organization", "task"], name="sf_deadline_org_task")]

    def __str__(self):
        return f"{self.assignment_id} · {self.task_id}"


__all__ = ["FolderAssignment", "TaskDeadline"]
