"""Tədris planı modelləri — ``Curriculum`` + ``CurriculumSubject``.

NİYƏ AYRI MODUL? ``models/academic.py`` 600 sətir büdcəsini (SOFT_CAP,
``scripts/check_module_size.py``) keçirdi. Sxem DƏYİŞMİR: model adları,
``app_label`` və cədvəl adları eynidir — sadəcə sinif tərifləri bu fayla köçdü
və ``models/__init__.py`` onları əvvəlki kimi re-eksport edir (migrasiyalar
toxunulmaz qalır).

Versiya/təsdiq və saat sahələrinin fabrikləri
:mod:`apps.registrar.models.curriculum_meta`-dədir; state maşını isə
:mod:`apps.registrar.curriculum_state`-dədir (model qatında qərar YOXDUR).
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import ActiveManager, OrderedModel, TimeStampedModel, UUIDModel

from ..reference_identity import ReferenceIdentityValidationMixin
from .academic import Program, Subject
from .curriculum_meta import (
    plan_actor_field,
    plan_assessment_field,
    plan_credits_field,
    plan_hours_field,
    plan_language_field,
    plan_previous_version_field,
    plan_protocol_field,
    plan_reason_field,
    plan_row_code_field,
    plan_status_field,
    plan_teaching_chair_field,
    plan_version_field,
)


class Curriculum(ReferenceIdentityValidationMixin, UUIDModel, TimeStampedModel):
    """A study plan (Tədris planı) for one program and admission cohort year.

    The set of ``CurriculumSubject`` rows defines, per semester, which subjects
    are mandatory and which belong to elective blocks the group/student chooses
    from (see docs/architecture/UNIVERSITY_SYSTEM_ROADMAP.md §2)."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="curricula")
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="curricula")
    admission_year = models.PositiveIntegerField(help_text="Qəbul ili (məs. 2024).")
    name = models.CharField(max_length=255, blank=True)
    # Versiya + təsdiq zənciri (dizayn handoff ekran 05) — bax `curriculum_meta`.
    # TƏSDİQLƏNMİŞ plan IMMUTABLE-dır: dəyişiklik yalnız yeni versiya yaradır.
    status = plan_status_field()
    version = plan_version_field()
    previous_version = plan_previous_version_field()
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = plan_actor_field("submitted_curricula")
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = plan_actor_field("approved_curricula")
    protocol_number = plan_protocol_field()
    last_reason = plan_reason_field()
    is_active = models.BooleanField(default=True, db_index=True)

    objects = models.Manager()
    active = ActiveManager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.curriculum.meta", "curriculum")
        verbose_name_plural = pgettext_lazy("registrar.model.curriculum.meta", "curricula")
        ordering = ["-admission_year", "program__name"]
        constraints = [
            # ⚠️ VERSİYA sütunu unikallığa DAXİLDİR: təsdiqlənmiş plan silinmir,
            # yeni versiya onun yanında yaşayır (eyni proqram + qəbul ili).
            models.UniqueConstraint(
                fields=["organization", "program", "admission_year", "version"],
                name="uniq_curriculum_program_year_version",
            ),
        ]

    def __str__(self):
        return self.name or f"{self.program.display_label} {self.admission_year}"


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
    # Plan sətrinin kredit/saat bölgüsü (ekran 05) — bax `curriculum_meta`.
    # `Subject.ects` KATALOQ default-udur; plan sətri onu override edir, çünki
    # eyni fənn müxtəlif ixtisaslarda fərqli kredit daşıyır (TEDRIS_PLANI_SPEC §4.2).
    row_code = plan_row_code_field()
    credits = plan_credits_field()
    total_hours = plan_hours_field("Ümumi saat = kredit × 30 (NK 348 b. 3.2.2).")
    lecture_hours = plan_hours_field("Semestrlik mühazirə saatı.")
    seminar_hours = plan_hours_field("Semestrlik seminar/məşğələ saatı.")
    lab_hours = plan_hours_field("Semestrlik laboratoriya saatı.")
    selfwork_hours = plan_hours_field("Sərbəst iş saatı (auditoriyadan kənar).")
    assessment_form = plan_assessment_field()
    language = plan_language_field()
    teaching_chair = plan_teaching_chair_field()

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
