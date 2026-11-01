"""Language teaching cohorts are separate from students' academic home groups."""

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel, UUIDModel

from .corrections import ImmutableCorrectionEvidence


class LanguageLevelCohort(UUIDModel, TimeStampedModel):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    department = models.ForeignKey("organizations.OrgUnit", on_delete=models.PROTECT, related_name="language_cohorts")
    group = models.OneToOneField("organizations.OrgUnit", on_delete=models.PROTECT, related_name="language_cohort")
    offering = models.OneToOneField(
        "registrar.CourseOffering", on_delete=models.PROTECT, related_name="language_cohort"
    )
    period = models.ForeignKey("organizations.AcademicPeriod", on_delete=models.PROTECT)
    source_offering = models.ForeignKey(
        "registrar.CourseOffering", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    lecture_hours = models.PositiveSmallIntegerField(default=0)
    seminar_hours = models.PositiveSmallIntegerField(default=0)
    lab_hours = models.PositiveSmallIntegerField(default=0)
    name = models.CharField(max_length=100)
    family = models.CharField(max_length=255)
    level = models.CharField(max_length=32)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "department", "period", "name"], name="uniq_language_cohort_name"
            )
        ]


class LanguageLevelPlacement(ImmutableCorrectionEvidence):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    cohort = models.ForeignKey(LanguageLevelCohort, on_delete=models.PROTECT, related_name="placements")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    home_group = models.ForeignKey("organizations.OrgUnit", on_delete=models.PROTECT, related_name="+")
    action = models.CharField(
        max_length=8, choices=[("add", "Əlavə edildi"), ("remove", "Çıxarıldı"), ("move", "Səviyyə dəyişdirildi")]
    )
    source_enrollment = models.ForeignKey(
        "registrar.Enrollment", null=True, blank=True, on_delete=models.PROTECT, related_name="level_departures"
    )
    target_enrollment = models.ForeignKey(
        "registrar.Enrollment", null=True, blank=True, on_delete=models.PROTECT, related_name="level_arrivals"
    )
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reason = models.CharField(max_length=500)
