"""Registrar / curriculum domain models (U1).

The academic-cycle foundation from docs/UNIVERSITY_SYSTEM_ROADMAP.md §1-2:

    Program (İxtisas)  ──<  Curriculum (tədris planı, program × qəbul ili)
    Subject (Fənn)     ──<  CurriculumSubject (plan sətri: semestr + məcburi/seçmə)

Semesters reuse the existing ``organizations.AcademicPeriod``. Every model is
tenant-scoped (``organization`` FK) and RLS-protected (see migration 0002). This
layer is additive — it does not touch the existing exam/LMS core.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import ActiveManager, OrderedModel, TimeStampedModel, UUIDModel


class DegreeLevel(models.TextChoices):
    BACHELOR = "bachelor", pgettext_lazy("registrar.degree", "Bachelor")
    MASTER = "master", pgettext_lazy("registrar.degree", "Master")
    PHD = "phd", pgettext_lazy("registrar.degree", "PhD")


class Program(UUIDModel, TimeStampedModel):
    """An academic program (İxtisas) offered by the university.

    Optionally anchored to a specialty ``OrgUnit`` so the hierarchy
    (Faculty → Chair → Specialty) and the program catalogue stay linked.
    """

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="programs")
    specialty_unit = models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="programs",
        help_text="İxtisas (OrgUnit: specialty) — iyerarxiya bağlantısı.",
    )
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    degree_level = models.CharField(max_length=16, choices=DegreeLevel.choices, default=DegreeLevel.BACHELOR)
    ects_total = models.PositiveIntegerField(default=240, help_text="Proqramın tam ECTS kredit yükü.")
    is_active = models.BooleanField(default=True, db_index=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.program.meta", "program")
        verbose_name_plural = pgettext_lazy("registrar.model.program.meta", "programs")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="uniq_program_code_per_org"),
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"


class Subject(UUIDModel, TimeStampedModel):
    """A subject/course catalogue entry (Fənn) — the reusable definition that
    curricula reference and semester offerings instantiate."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="subjects")
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    ects = models.PositiveSmallIntegerField(default=5, help_text="Fənnin ECTS kredit dəyəri.")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.subject.meta", "subject")
        verbose_name_plural = pgettext_lazy("registrar.model.subject.meta", "subjects")
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="uniq_subject_code_per_org"),
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"


class Curriculum(UUIDModel, TimeStampedModel):
    """A study plan (Tədris planı) for one program and admission cohort year.

    The set of ``CurriculumSubject`` rows defines, per semester, which subjects
    are mandatory and which belong to elective blocks the group/student chooses
    from (see docs/UNIVERSITY_SYSTEM_ROADMAP.md §2)."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="curricula")
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="curricula")
    admission_year = models.PositiveIntegerField(help_text="Qəbul ili (məs. 2024).")
    name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.curriculum.meta", "curriculum")
        verbose_name_plural = pgettext_lazy("registrar.model.curriculum.meta", "curricula")
        ordering = ["-admission_year", "program__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "program", "admission_year"],
                name="uniq_curriculum_program_year",
            ),
        ]

    def __str__(self):
        return self.name or f"{self.program.code} {self.admission_year}"


class CurriculumSubject(UUIDModel, TimeStampedModel, OrderedModel):
    """A single plan row: a subject scheduled in a given semester of a plan.

    ``is_elective`` marks a subject that belongs to an elective block; every row
    sharing the same ``elective_group`` (within the same curriculum + semester)
    forms one block from which ``required_choices`` subject(s) are chosen. In the
    AZ university model the choice is made at GROUP level (see
    ``GroupElectiveChoice`` design, roadmap §2.5) — implemented in U2."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="curriculum_subjects"
    )
    curriculum = models.ForeignKey(Curriculum, on_delete=models.CASCADE, related_name="rows")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="curriculum_rows")
    semester_number = models.PositiveSmallIntegerField(help_text="Neçənci semestr (1..N).")
    is_elective = models.BooleanField(default=False, db_index=True)
    elective_group = models.CharField(
        max_length=50, blank=True, help_text="Seçmə blok adı (eyni blokun sətirləri eyni dəyəri daşıyır)."
    )
    required_choices = models.PositiveSmallIntegerField(default=1, help_text="Seçmə blokdan neçə fənn seçilməlidir.")

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.curriculum_subject.meta", "curriculum subject")
        verbose_name_plural = pgettext_lazy("registrar.model.curriculum_subject.meta", "curriculum subjects")
        ordering = ["curriculum", "semester_number", "order"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "curriculum", "subject", "semester_number"],
                name="uniq_curriculum_subject_semester",
            ),
        ]
        indexes = [
            models.Index(fields=["curriculum", "semester_number"]),
            models.Index(fields=["curriculum", "elective_group"]),
        ]

    def __str__(self):
        kind = "seçmə" if self.is_elective else "məcburi"
        return f"{self.subject.code} · sem {self.semester_number} · {kind}"


# ── Enrollment layer (U2): student record, offerings, enrollments, group choice ──


class EnrollmentKind(models.TextChoices):
    MANDATORY = "mandatory", pgettext_lazy("registrar.enrollment_kind", "Mandatory")
    ELECTIVE = "elective", pgettext_lazy("registrar.enrollment_kind", "Elective")
    RETAKE = "retake", pgettext_lazy("registrar.enrollment_kind", "Retake")


class StudentAcademicRecord(UUIDModel, TimeStampedModel):
    """A student's academic profile within a program: which curriculum + group
    they belong to. Drives the mandatory/elective enrollment flow (roadmap §2)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="student_records"
    )
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="academic_records")
    program = models.ForeignKey(Program, on_delete=models.PROTECT, related_name="student_records")
    curriculum = models.ForeignKey(Curriculum, on_delete=models.PROTECT, related_name="student_records")
    group = models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="student_records",
        help_text="Tələbənin qrupu (bölmə/sektor OrgUnit: group).",
    )
    admission_year = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True, db_index=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.student_record.meta", "student academic record")
        verbose_name_plural = pgettext_lazy("registrar.model.student_record.meta", "student academic records")
        constraints = [
            models.UniqueConstraint(fields=["organization", "student", "program"], name="uniq_student_program"),
        ]
        indexes = [models.Index(fields=["organization", "group"])]

    def __str__(self):
        return f"{self.student_id} · {self.program.code}"


class CourseOffering(UUIDModel, TimeStampedModel):
    """A subject taught in a specific semester for a specific group (a section).

    Optionally links to the LMS ``courses.Course`` so the subject's content
    (topics/resources) is the existing course dashboard (roadmap §2.2)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="course_offerings"
    )
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="offerings")
    period = models.ForeignKey("organizations.AcademicPeriod", on_delete=models.PROTECT, related_name="offerings")
    group = models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="course_offerings",
        help_text="Bu bölmənin/qrupun dərsi (boşdursa — bütün ixtisas üçün).",
    )
    course = models.ForeignKey(
        "courses.Course",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="offerings",
        help_text="LMS kursu (fənn içi = mövzular/resurslar) — opsional.",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.offering.meta", "course offering")
        verbose_name_plural = pgettext_lazy("registrar.model.offering.meta", "course offerings")
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "subject", "period", "group"], name="uniq_offering_subject_period_group"
            ),
        ]
        indexes = [models.Index(fields=["organization", "period"])]

    def __str__(self):
        return f"{self.subject.code} @ {self.period_id}"


class Enrollment(UUIDModel, TimeStampedModel):
    """A student's enrollment in one course offering (mandatory / elective / retake)."""

    class Status(models.TextChoices):
        ENROLLED = "enrolled", pgettext_lazy("registrar.enrollment_status", "Enrolled")
        COMPLETED = "completed", pgettext_lazy("registrar.enrollment_status", "Completed")
        DROPPED = "dropped", pgettext_lazy("registrar.enrollment_status", "Dropped")

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="enrollments")
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name="enrollments")
    kind = models.CharField(max_length=16, choices=EnrollmentKind.choices, default=EnrollmentKind.MANDATORY)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ENROLLED, db_index=True)

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.enrollment.meta", "enrollment")
        verbose_name_plural = pgettext_lazy("registrar.model.enrollment.meta", "enrollments")
        constraints = [
            models.UniqueConstraint(fields=["organization", "student", "offering"], name="uniq_student_offering"),
        ]
        indexes = [
            models.Index(fields=["organization", "student"]),
            models.Index(fields=["offering", "status"]),
        ]

    def __str__(self):
        return f"{self.student_id} → {self.offering_id} ({self.kind})"


class GroupElectiveChoice(UUIDModel, TimeStampedModel):
    """A GROUP's decision for one elective block in one semester.

    In the AZ university model the elective is chosen at group level: once the
    group's choice is recorded, every group member is enrolled in the chosen
    subject (roadmap §2.5). Enforced one-choice-per (group, period, block)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="group_elective_choices"
    )
    group = models.ForeignKey("organizations.OrgUnit", on_delete=models.CASCADE, related_name="group_elective_choices")
    period = models.ForeignKey(
        "organizations.AcademicPeriod", on_delete=models.PROTECT, related_name="group_elective_choices"
    )
    elective_group = models.CharField(max_length=50, help_text="CurriculumSubject.elective_group blok adı.")
    chosen_subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="group_elective_choices")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="group_elective_decisions",
    )

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.group_elective.meta", "group elective choice")
        verbose_name_plural = pgettext_lazy("registrar.model.group_elective.meta", "group elective choices")
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "group", "period", "elective_group"],
                name="uniq_group_elective_block",
            ),
        ]

    def __str__(self):
        return f"{self.group_id} · {self.elective_group} → {self.chosen_subject.code}"
