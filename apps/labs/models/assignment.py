"""labs model paketi — tapşırıq/təqdim/cavab."""

from django.core.exceptions import PermissionDenied
from django.db import models

from core.upload_security import FileUploadValidator

from ._base import (
    User,
    secure_random,
)
from .lab import (
    Lab,
    LabQuestion,
)


class LabAssignment(models.Model):
    """
    Tələbəyə verilmiş lab tapşırığı.
    Hər tələbəyə unikal sual dəsti təyin olunur.
    """

    lab = models.ForeignKey(Lab, on_delete=models.CASCADE, related_name="assignments", verbose_name="Lab")

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="lab_assignments",
        verbose_name="Tələbə",
    )

    assigned_questions = models.ManyToManyField(
        "LabQuestion", related_name="assignments", verbose_name="Təyin edilmiş suallar"
    )

    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["lab", "student"]
        verbose_name = "Lab Tapşırığı"
        verbose_name_plural = "Lab Tapşırıqları"

    def __str__(self):
        return f"{self.student.username} - {self.lab.title}"

    @classmethod
    def get_or_create_for_student(cls, lab, student):
        """
        Tələbə üçün assignment yarat və sualları təyin et
        """
        if not lab.can_student_access(student):
            raise PermissionDenied("You do not have permission to access this lab.")

        assignment, created = cls.objects.get_or_create(lab=lab, student=student)

        # Yeni assignment üçün həmişə sual təyin et.
        # Mövcud assignment üçün yalnız hələ submission yoxdursa və assignment köhnəlibsə yenilə.
        if created or not assignment.assigned_questions.exists():
            assignment.assign_questions()
        elif assignment.needs_reassignment():
            assignment.assign_questions()

        return assignment

    def _candidate_count(self):
        """
        Blok limitlərinə əsasən lab üçün potensial seçilə bilən sual sayını qaytarır.
        """
        total = 0
        # annotate(Count): əvvəl hər blok üçün block.questions.count() ayrı sorğu
        # idi (N+1) — indi blok siyahısı ilə birlikdə tək sorğuda.
        for block in self.lab.blocks.annotate(_q_count=models.Count("questions")).order_by("order"):
            block_count = block._q_count
            if block_count == 0:
                continue
            if block.questions_to_pick > 0:
                total += min(block.questions_to_pick, block_count)
            else:
                total += block_count
        return total

    def expected_assigned_count(self):
        """
        Cari lab ayarlarına görə assignment-da neçə sual olmalı olduğunu qaytarır.
        """
        candidate_count = self._candidate_count()
        if self.lab.questions_per_student > 0:
            return min(self.lab.questions_per_student, candidate_count)
        return candidate_count

    def needs_reassignment(self):
        """
        Assignment köhnəlibsə (blok/sual sayı dəyişib və ya silinmiş suallar qalıbsa) True qaytarır.
        """
        assigned_ids = set(self.assigned_questions.values_list("id", flat=True))
        if not assigned_ids:
            return True

        valid_ids = set(LabQuestion.objects.filter(block__lab=self.lab).values_list("id", flat=True))
        if not assigned_ids.issubset(valid_ids):
            return True

        return len(assigned_ids) != self.expected_assigned_count()

    def assign_questions(self):
        """
        Bu tələbəyə random suallar təyin et
        """

        all_questions = []

        # Hər blokdan sualları topla
        for block in self.lab.blocks.all().order_by("order"):
            block_questions = list(block.questions.all())

            if block.questions_to_pick > 0 and block.questions_to_pick < len(block_questions):
                # Bu blokdan məhdud sayda seç
                selected = secure_random.sample(block_questions, block.questions_to_pick)
            else:
                # Bütün sualları götür
                selected = block_questions

            all_questions.extend(selected)

        # Əgər lab səviyyəsində limit varsa
        if self.lab.questions_per_student > 0 and self.lab.questions_per_student < len(all_questions):
            all_questions = secure_random.sample(all_questions, self.lab.questions_per_student)

        # Sualları təyin et
        self.assigned_questions.set(all_questions)


class LabSubmission(models.Model):
    """
    Tələbənin Lab Cavabı.

    Fayl və/və ya link göndərə bilər.
    """

    STATUS_CHOICES = [
        ("submitted", "Göndərilib"),
        ("late", "Gecikmiş"),
        ("graded", "Qiymətləndirilib"),
        ("returned", "Qaytarıldı"),
    ]

    assignment = models.ForeignKey(
        LabAssignment,
        on_delete=models.CASCADE,
        related_name="submissions",
        verbose_name="Təyinat",
    )

    # Cavab
    submission_text = models.TextField(blank=True, verbose_name="Cavab mətni", help_text="Əlavə qeyd, izahat")

    submission_file = models.FileField(upload_to="labs/submissions/%Y/%m/", blank=True, null=True, verbose_name="Fayl")

    submission_link = models.URLField(blank=True, verbose_name="Link", help_text="GitHub, Google Drive, Figma və s.")

    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="submitted",
        verbose_name="Status",
    )

    # Qiymətləndirmə
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Qiymət")

    feedback = models.TextField(blank=True, verbose_name="Müəllim rəyi")

    graded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="graded_lab_submissions",
        verbose_name="Qiymətləndirən",
    )

    graded_at = models.DateTimeField(null=True, blank=True, verbose_name="Qiymətləndirmə tarixi")

    # Metadata
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Attempt tracking
    attempt_number = models.PositiveIntegerField(default=1, verbose_name="Cəhd nömrəsi")

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = "Lab Cavabı"
        verbose_name_plural = "Lab Cavabları"
        indexes = [
            # Teacher grading queue: a lab assignment's submissions by status.
            models.Index(
                fields=["assignment", "status", "-submitted_at"],
                name="labsub_assign_status_idx",
            ),
        ]

    def __str__(self):
        return f"{self.assignment.student.username} - {self.assignment.lab.title} (Cəhd {self.attempt_number})"

    @property
    def is_late(self):
        """Gecikmiş göndəriş?"""
        if not self.submitted_at:
            return False
        if not self.assignment or not self.assignment.lab:
            return False
        if not self.assignment.lab.end_datetime:
            return False
        return self.submitted_at > self.assignment.lab.end_datetime

    def save(self, *args, **kwargs):
        # Gecikmiş göndərişi avtomatik işarələ - yalnız yeni submission üçün
        if not self.pk:
            try:
                if self.is_late:
                    self.status = "late"
            except Exception:
                pass
        super().save(*args, **kwargs)


class LabAnswer(models.Model):
    """
    Tələbənin hər suala verdiyi cavab - hər cəhd üçün ayrı
    """

    lab = models.ForeignKey(Lab, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey("LabQuestion", on_delete=models.CASCADE, related_name="answers")
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="lab_answers")

    # Hansı cəhdə aiddir
    submission = models.ForeignKey(
        "LabSubmission",
        on_delete=models.CASCADE,
        related_name="answers",
        null=True,
        blank=True,
    )

    # Cəhd nömrəsi (submission olmadan da işləsin)
    attempt_number = models.PositiveIntegerField(default=1)

    answer = models.TextField(blank=True)
    answer_file = models.FileField(
        upload_to="labs/answers/%Y/%m/", blank=True, null=True, validators=[FileUploadValidator()]
    )

    is_draft = models.BooleanField(default=True)
    is_correct = models.BooleanField(null=True, blank=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Hər cəhd üçün ayrı cavab
        unique_together = ["lab", "question", "student", "attempt_number"]

    def __str__(self):
        return f"{self.student.username} - Q{self.question.id} - Cəhd {self.attempt_number}"
