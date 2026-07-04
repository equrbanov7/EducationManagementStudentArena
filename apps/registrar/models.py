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
    ects_total = models.PositiveIntegerField(
        default=240, help_text="Məzuniyyət üçün tələb olunan tam ECTS kredit yükü (Boloniya)."
    )
    # Qayıb (absence) limiti: dərs saatlarının bu %-ini üzrsüz buraxan tələbə
    # imtahana buraxılmır ("kəsilir"). AZ universitetlərində adətən 25% —
    # universitetə/proqrama görə konfiqurasiya olunur.
    absence_limit_percent = models.PositiveSmallIntegerField(
        default=25, help_text="Üzrsüz qayıb həddi (dərs saatının %-i); keçilərsə imtahana buraxılmır."
    )
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


class AcademicStatus(models.TextChoices):
    """Where a student stands academically (U5+ status state-machine)."""

    ENROLLED = "enrolled", pgettext_lazy("registrar.academic_status", "Enrolled")
    ACADEMIC_LEAVE = "academic_leave", pgettext_lazy("registrar.academic_status", "Academic leave")
    EXPELLED = "expelled", pgettext_lazy("registrar.academic_status", "Expelled")
    GRADUATED = "graduated", pgettext_lazy("registrar.academic_status", "Graduated")


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
    status = models.CharField(
        max_length=20,
        choices=AcademicStatus.choices,
        default=AcademicStatus.ENROLLED,
        db_index=True,
        help_text="Akademik status (qeydiyyatlı / akademik məzuniyyət / xaric / məzun).",
    )
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
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="taught_offerings",
        help_text="Fənni tədris edən müəllim (elektron jurnal sahibi).",
    )
    lesson_hours = models.PositiveSmallIntegerField(
        default=0, help_text="Semestrdə fənnin tam dərs (kontakt) saatı — qayıb limiti üçün baza."
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
    absence_hours = models.PositiveSmallIntegerField(
        default=0, help_text="Bu fənn üzrə toplanmış üzrsüz qayıb saatı (qayıb limiti üçün)."
    )

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


# ── Elektron jurnal (davamiyyət/qiymət jurnalı, U3 — UNEC modeli) ─────────────
#
# Elektron jurnal komponent-cəm DEYİL: müəllim hər dərs günü tələbələrin
# iştirak/qayıbını (iə/qb), seminar/lab dərslərində isə balını yazır. Sistem
# keçirilən dərsləri, qayıb saatını və "giriş balı"nı (seminar/lab ballarının
# cəmi) AVTOMATİK hesablayır. Mühazirədə yalnız iə/qb; seminarda bal da yazılır.
# Yekun imtahan burada YOXDUR — bu jurnal yalnız semestr fəaliyyətidir.
# Kilid qaydaları servis qatında (``apps/registrar/gradebook.py``): dərs tarixi
# yaranışdan sonra qısa müddət, iştirak/bal isə 1 gün sonra dəyişilə bilməz.


class LessonKind(models.TextChoices):
    LECTURE = "lecture", pgettext_lazy("registrar.lesson_kind", "Lecture")  # yalnız iə/qb
    SEMINAR = "seminar", pgettext_lazy("registrar.lesson_kind", "Seminar")  # iə/qb + bal
    LAB = "lab", pgettext_lazy("registrar.lesson_kind", "Laboratory")  # iə/qb + bal


class AttendanceStatus(models.TextChoices):
    PRESENT = "present", pgettext_lazy("registrar.attendance", "Present")  # iştirak (iə)
    ABSENT = "absent", pgettext_lazy("registrar.attendance", "Absent")  # qayıb (qb)


class AssessmentScheme(UUIDModel, TimeStampedModel):
    """Per-offering journal config (tenant/offering-configurable).

    The electronic journal accumulates the semester "entry score" (giriş balı,
    max ``entry_score_max`` ≈ 50) from seminar/lab lesson scores; the final exam
    is entered elsewhere. ``is_published`` finalises/locks the journal."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="assessment_schemes"
    )
    offering = models.OneToOneField(CourseOffering, on_delete=models.CASCADE, related_name="assessment_scheme")
    entry_score_max = models.PositiveSmallIntegerField(
        default=50, help_text="Semestr 'giriş balı' tavanı (Boloniya ≈50; qalan 50 yekun imtahan)."
    )
    pass_threshold = models.PositiveSmallIntegerField(
        default=51, help_text="Keçid üçün minimum ümumi bal (giriş + imtahan, adətən 51)."
    )
    min_final_exam_score = models.PositiveSmallIntegerField(
        default=17, help_text="Yekun imtahandan keçid üçün minimum bal (kəsilmə qaydası)."
    )
    is_published = models.BooleanField(default=False, help_text="Yekunlaşdırılıb — jurnal redaktəsi bağlıdır.")

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.scheme.meta", "assessment scheme")
        verbose_name_plural = pgettext_lazy("registrar.model.scheme.meta", "assessment schemes")

    def __str__(self):
        return f"scheme<{self.offering_id}>"


class Lesson(UUIDModel, TimeStampedModel):
    """One held session (dərs) on a date — a journal column.

    ``kind`` decides what the teacher records: LECTURE → attendance only;
    SEMINAR/LAB → attendance + a score. Ordering by date gives the running
    sequence (neçənci dərs). The lesson date is editable only within a short
    window after creation (enforced in the service layer)."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="lessons")
    offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name="lessons")
    date = models.DateField(help_text="Dərsin keçirildiyi tarix.")
    kind = models.CharField(max_length=16, choices=LessonKind.choices, default=LessonKind.LECTURE)
    topic = models.CharField(max_length=255, blank=True, help_text="Mövzu (opsional).")
    hours = models.PositiveSmallIntegerField(default=2, help_text="Bu dərsin akademik saatı (qayıb hesabı üçün).")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = models.Manager()

    class Meta:
        ordering = ["date", "created_at"]
        verbose_name = pgettext_lazy("registrar.model.lesson.meta", "lesson")
        verbose_name_plural = pgettext_lazy("registrar.model.lesson.meta", "lessons")
        indexes = [models.Index(fields=["organization", "offering", "date"])]

    def __str__(self):
        return f"{self.offering_id} · {self.date} ({self.kind})"


class LessonMark(UUIDModel, TimeStampedModel):
    """One student's record for one lesson (the journal cell): attendance + score.

    ``status`` is the attendance (present/absent = iə/qb); ``score`` is filled
    only for seminar/lab lessons. Editable for a limited window after entry
    (see the service layer) — no back-dated tampering."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="lesson_marks"
    )
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="marks")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="lesson_marks")
    status = models.CharField(max_length=12, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT)
    score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, help_text="Seminar/lab balı (opsional)."
    )
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.mark.meta", "lesson mark")
        verbose_name_plural = pgettext_lazy("registrar.model.mark.meta", "lesson marks")
        constraints = [
            models.UniqueConstraint(fields=["lesson", "enrollment"], name="uniq_lesson_enrollment_mark"),
        ]
        indexes = [models.Index(fields=["organization", "enrollment"])]

    def __str__(self):
        return f"{self.lesson_id} · {self.enrollment_id} = {self.status}"


# ── Dərs cədvəli (timetable, U4) ─────────────────────────────────────────────
#
# Həftəlik təkrarlanan dərs slotu: fənn (offering) + həftənin günü + vaxt +
# auditoriya. Qrup və müəllim offering-dən gəlir. Konflikt yoxlaması (eyni qrup /
# müəllim / otaq × gün+vaxt üst-üstə düşməsin) servis qatındadır. Görünüş rol-
# aware: tələbə öz qrupunun, müəllim öz slotlarının cədvəlini görür.


class WeekType(models.TextChoices):
    ALL = "all", pgettext_lazy("registrar.week_type", "Every week")
    ODD = "odd", pgettext_lazy("registrar.week_type", "Odd weeks")  # üst həftə
    EVEN = "even", pgettext_lazy("registrar.week_type", "Even weeks")  # alt həftə


class ScheduleSlot(UUIDModel, TimeStampedModel):
    """One weekly recurring class slot (a timetable row)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="schedule_slots"
    )
    offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name="schedule_slots")
    weekday = models.PositiveSmallIntegerField(help_text="Həftənin günü (1=Bazar ertəsi … 7=Bazar).")
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=64, blank=True, help_text="Auditoriya (opsional).")
    week_type = models.CharField(max_length=8, choices=WeekType.choices, default=WeekType.ALL)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = models.Manager()

    class Meta:
        ordering = ["weekday", "start_time"]
        verbose_name = pgettext_lazy("registrar.model.slot.meta", "schedule slot")
        verbose_name_plural = pgettext_lazy("registrar.model.slot.meta", "schedule slots")
        indexes = [models.Index(fields=["organization", "offering", "weekday"])]

    def __str__(self):
        return f"{self.offering_id} · gün {self.weekday} {self.start_time}-{self.end_time}"


# ── Yekun qiymət + təkrar imtahan (U3+, kəsilmə/resit qaydası) ────────────────
#
# Yekun bal = jurnaldan "giriş balı" (semestr, ≈50) + yekun imtahan balı (≈50).
# Tələbə kəsilir (imtahana buraxılmır/keçmir) → ``ResitRecord`` (təkrar imtahan
# hüququ). Hesablama servis qatındadır (``apps/registrar/finals.py``).


class FinalGrade(UUIDModel, TimeStampedModel):
    """The final-exam score for one enrollment (the other half of the total)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="final_grades"
    )
    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name="final_grade")
    exam_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, help_text="Yekun imtahan balı (≈max 50)."
    )
    is_published = models.BooleanField(default=False, help_text="Nəticə rəsmiləşdirilib.")
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.final.meta", "final grade")
        verbose_name_plural = pgettext_lazy("registrar.model.final.meta", "final grades")
        indexes = [models.Index(fields=["organization", "enrollment"])]

    def __str__(self):
        return f"final<{self.enrollment_id}> exam={self.exam_score}"


class ResitReason(models.TextChoices):
    ABSENCE = "absence", pgettext_lazy("registrar.resit_reason", "Barred by absence")
    TOTAL = "total", pgettext_lazy("registrar.resit_reason", "Total below pass mark")
    EXAM = "exam", pgettext_lazy("registrar.resit_reason", "Exam below minimum")


class ResitStatus(models.TextChoices):
    ELIGIBLE = "eligible", pgettext_lazy("registrar.resit_status", "Eligible")
    COMPLETED = "completed", pgettext_lazy("registrar.resit_status", "Completed")


class ResitRecord(UUIDModel, TimeStampedModel):
    """A student's resit (təkrar imtahan) right for one enrollment.

    Created when the student fails; once a ``resit_score`` is entered the final
    result is recomputed with it in place of the original exam score."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="resits")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="resit_records")
    reason = models.CharField(max_length=12, choices=ResitReason.choices)
    status = models.CharField(max_length=12, choices=ResitStatus.choices, default=ResitStatus.ELIGIBLE)
    resit_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, help_text="Təkrar imtahan balı."
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = pgettext_lazy("registrar.model.resit.meta", "resit record")
        verbose_name_plural = pgettext_lazy("registrar.model.resit.meta", "resit records")
        constraints = [
            models.UniqueConstraint(fields=["enrollment"], name="uniq_resit_per_enrollment"),
        ]
        indexes = [models.Index(fields=["organization", "enrollment"])]

    def __str__(self):
        return f"resit<{self.enrollment_id}> {self.status}"
