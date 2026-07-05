"""Registrar qiymətləndirmə/jurnal modelləri (U3/U7).

Elektron jurnal (Lesson/LessonMark), qiymətləndirmə sxemi + təsdiq zənciri
(AssessmentScheme/ApprovalStatus), çəkili komponentlər, yekun qiymət və təkrar
imtahan. Akademik-struktur modelləri :mod:`apps.registrar.models.academic`-dədir.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import OrderedModel, TimeStampedModel, UUIDModel

from .academic import CourseOffering, Enrollment

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


class ApprovalStatus(models.TextChoices):
    """Journal grade-approval chain (U7.2): teacher → chair → dean → official."""

    DRAFT = "draft", pgettext_lazy("registrar.approval", "Draft")
    SUBMITTED = "submitted", pgettext_lazy("registrar.approval", "Submitted (awaiting chair)")
    CHAIR_APPROVED = "chair_approved", pgettext_lazy("registrar.approval", "Chair approved (awaiting dean)")
    APPROVED = "approved", pgettext_lazy("registrar.approval", "Approved (official)")
    RETURNED = "returned", pgettext_lazy("registrar.approval", "Returned for revision")


class AssessmentScheme(UUIDModel, TimeStampedModel):
    """Per-offering journal config + grade-approval state (tenant-configurable).

    The electronic journal accumulates the semester "entry score" (giriş balı,
    max ``entry_score_max`` ≈ 50) from seminar/lab lesson scores; the final exam
    is entered elsewhere. The grade-approval chain (``approval_status``) locks the
    journal while under review and, on final dean approval, sets ``is_published``
    (official / transcript-ready)."""

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
    approval_status = models.CharField(
        max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.DRAFT, db_index=True
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    chair_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    dean_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    returned_reason = models.TextField(blank=True, help_text="Geri qaytarılma səbəbi (varsa).")

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


# ── Çəkili qiymətləndirmə komponentləri (U7.1) ───────────────────────────────
#
# Sadələşdirilmiş jurnal "giriş balı"nı seminar/lab dərs ballarının cəmindən alır.
# Universitetlər isə tez-tez struktur qiymətləndirmə işlədir: cari bal = seminar +
# kollokvium(lar) + SDF/sərbəst iş + layihə, hər komponentin öz tavanı (max_score)
# ilə (cəmi ≈ entry_score_max). Bu, ADDİTİVdir: offering üçün komponent təyin
# olunmayıbsa, jurnal əvvəlki dərs-cəm məntiqi ilə işləyir (geriyə-uyğun).


class Rubric(UUIDModel, TimeStampedModel):
    """Təkrar istifadə olunan qiymətləndirmə rubriki (U22) — org-səviyyəli şablon.

    Meyar dəsti (:class:`RubricCriterion`) komponentə qoşulur; müəllim tələbəni
    meyar-meyar qiymətləndirir, meyar ballarının cəmi komponent balına yazılır
    (komponentin ``max_score``-u ilə clamp). Şablon olduğu üçün eyni rubrik
    bir neçə fənnin komponentlərində paylaşıla bilir."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="rubrics")
    name = models.CharField(max_length=150, help_text="Rubrik adı (məs. Layihə təqdimatı).")
    description = models.CharField(max_length=300, blank=True, default="")
    is_active = models.BooleanField(default=True)

    objects = models.Manager()

    class Meta:
        ordering = ["name"]
        verbose_name = pgettext_lazy("registrar.model.rubric.meta", "rubric")
        verbose_name_plural = pgettext_lazy("registrar.model.rubric.meta", "rubrics")
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="uniq_rubric_org_name"),
        ]

    def __str__(self):
        return self.name


class RubricCriterion(UUIDModel, TimeStampedModel):
    """Rubrikin bir meyarı: ad + maksimum bal (sıralı)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="rubric_criteria"
    )
    rubric = models.ForeignKey(Rubric, on_delete=models.CASCADE, related_name="criteria")
    name = models.CharField(max_length=150)
    max_points = models.PositiveSmallIntegerField(default=5, help_text="Bu meyar üzrə maksimum bal.")
    order = models.PositiveSmallIntegerField(default=0)

    objects = models.Manager()

    class Meta:
        ordering = ["order", "name"]
        verbose_name = pgettext_lazy("registrar.model.rubric_criterion.meta", "rubric criterion")
        verbose_name_plural = pgettext_lazy("registrar.model.rubric_criterion.meta", "rubric criteria")
        constraints = [
            models.UniqueConstraint(fields=["rubric", "name"], name="uniq_criterion_rubric_name"),
        ]
        indexes = [models.Index(fields=["organization", "rubric"])]

    def __str__(self):
        return f"{self.name} ({self.max_points})"


class AssessmentComponent(UUIDModel, TimeStampedModel, OrderedModel):
    """One weighted entry-score component of an offering (seminar / kollokvium /
    SDF / layihə). ``max_score`` is its contribution ceiling; the components'
    ``max_score`` values normally sum to the scheme's ``entry_score_max`` (≈50)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="assessment_components"
    )
    offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name="assessment_components")
    name = models.CharField(max_length=100, help_text="Komponent adı (məs. Seminar, Kollokvium 1, SDF, Layihə).")
    max_score = models.PositiveSmallIntegerField(default=10, help_text="Bu komponentin giriş balına maksimum töhfəsi.")
    rubric = models.ForeignKey(
        Rubric,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="components",
        help_text="Qoşulubsa, bu komponent meyar-meyar (rubrik ilə) qiymətləndirilir (U22).",
    )

    objects = models.Manager()

    class Meta:
        ordering = ["offering", "order", "name"]
        verbose_name = pgettext_lazy("registrar.model.component.meta", "assessment component")
        verbose_name_plural = pgettext_lazy("registrar.model.component.meta", "assessment components")
        constraints = [
            models.UniqueConstraint(fields=["offering", "name"], name="uniq_component_offering_name"),
        ]
        indexes = [models.Index(fields=["organization", "offering"])]

    def __str__(self):
        return f"{self.offering_id} · {self.name} (≤{self.max_score})"


class ComponentScore(UUIDModel, TimeStampedModel):
    """One student's score for one assessment component (manual, capped at max)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="component_scores"
    )
    component = models.ForeignKey(AssessmentComponent, on_delete=models.CASCADE, related_name="scores")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="component_scores")
    score = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Komponent balı.")
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.component_score.meta", "component score")
        verbose_name_plural = pgettext_lazy("registrar.model.component_score.meta", "component scores")
        constraints = [
            models.UniqueConstraint(fields=["component", "enrollment"], name="uniq_component_enrollment_score"),
        ]
        indexes = [models.Index(fields=["organization", "enrollment"])]

    def __str__(self):
        return f"{self.component_id} · {self.enrollment_id} = {self.score}"


class CriterionScore(UUIDModel, TimeStampedModel):
    """Bir tələbənin bir rubrik meyarı üzrə balı (U22)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="criterion_scores"
    )
    criterion = models.ForeignKey(RubricCriterion, on_delete=models.CASCADE, related_name="scores")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="criterion_scores")
    points = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy("registrar.model.criterion_score.meta", "criterion score")
        verbose_name_plural = pgettext_lazy("registrar.model.criterion_score.meta", "criterion scores")
        constraints = [
            models.UniqueConstraint(fields=["criterion", "enrollment"], name="uniq_criterion_enrollment_score"),
        ]
        indexes = [models.Index(fields=["organization", "enrollment"])]

    def __str__(self):
        return f"{self.criterion_id} · {self.enrollment_id} = {self.points}"


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
    # U15 — bonus/cərimə: müsbət (əlavə fəallıq) və ya mənfi (gecikmə cəriməsi)
    # düzəliş; ümumi bal 0..100 aralığında clamp olunur (finals.compute_final_result).
    bonus = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Bonus (+) / cərimə (−) düzəlişi — ümumi bala əlavə olunur.",
    )
    comment = models.CharField(
        max_length=500, blank=True, help_text="Müəllimin yekun rəyi — tələbəyə görünür (opsional)."
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
