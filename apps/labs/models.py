"""
labs/models.py
──────────────
Lab İşləri modulu.

Modellər:
1. Lab - Əsas lab işi
2. LabBlock - Sual bloku
3. LabQuestion - Sual
4. LabAssignment - Tələbəyə təyin olunan suallar
5. LabSubmission - Tələbənin cavabı
"""

import secrets

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.validators import MaxValueValidator
from django.db import models
from django.utils import timezone

from core.upload_security import FileUploadValidator

User = get_user_model()
secure_random = secrets.SystemRandom()


# ════════════════════════════════════════════════════════════════════════════
# 1. LAB MODEL
# ════════════════════════════════════════════════════════════════════════════


class Lab(models.Model):
    """
    Əsas Lab İşi modeli.

    Müəllim lab yaradır, suallar əlavə edir, tələbələrə paylayır.
    """

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("published", "Yayımlandı"),
        ("archived", "Arxivləndi"),
    ]

    allowed_students = models.ManyToManyField(
        User,
        blank=True,
        related_name="allowed_labs",
        verbose_name="İcazəli tələbələr",
    )

    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.CASCADE,
        related_name="labs",
        verbose_name="Kurs",
    )

    title = models.CharField(max_length=255, verbose_name="Lab Adı")

    description = models.TextField(
        blank=True,
        verbose_name="Təsvir",
        help_text="Lab işinin təsviri, tələblər və s.",
    )

    # Tarixlər
    start_datetime = models.DateTimeField(
        verbose_name="Başlanğıc tarixi",
        help_text="Bu tarixdən sonra tələbələr labı görə bilər",
    )

    end_datetime = models.DateTimeField(
        verbose_name="Son tarix (Deadline)",
        help_text="Bu tarixdən sonra göndəriş qəbul olunmur",
    )

    # Qiymətləndirmə
    max_score = models.PositiveIntegerField(default=100, verbose_name="Maksimum bal")

    max_attempts = models.PositiveIntegerField(
        default=1,
        verbose_name="Maksimum cəhd sayı",
        help_text="Tələbə neçə dəfə göndərə bilər",
    )

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft", verbose_name="Status")

    # Gecikmə
    allow_late_submission = models.BooleanField(default=False, verbose_name="Gecikmiş göndərişə icazə ver")

    late_penalty_percent = models.PositiveIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
        verbose_name="Gecikmə cəzası (%)",
        help_text="Hər gün üçün neçə % çıxılsın",
    )

    # Müəllim faylları
    teacher_files = models.FileField(
        upload_to="labs/teacher_files/%Y/%m/",
        blank=True,
        null=True,
        verbose_name="Müəllim faylı",
        help_text="PDF, ZIP, DOC və s.",
        validators=[FileUploadValidator()],
    )

    teacher_instructions = models.TextField(
        blank=True,
        verbose_name="Müəllim təlimatları",
        help_text="Tələbələr üçün əlavə təlimat (text formatında)",
    )

    # Submission ayarları
    allow_file_upload = models.BooleanField(default=True, verbose_name="Fayl yükləməyə icazə")

    allow_link_submission = models.BooleanField(default=True, verbose_name="Link göndərməyə icazə")

    allowed_extensions = models.CharField(
        max_length=255,
        default="zip,pdf,docx,png,jpg,txt,py,java,cpp",
        verbose_name="İcazə verilən fayl tipləri",
        help_text="Vergüllə ayırın: zip,pdf,docx",
    )

    max_file_size_mb = models.PositiveIntegerField(default=50, verbose_name="Maks fayl ölçüsü (MB)")

    # Random sual ayarları
    questions_per_student = models.PositiveIntegerField(
        default=0,
        verbose_name="Hər tələbəyə düşən sual sayı",
        help_text="0 = bütün suallar, >0 = random seçim",
    )

    # Qrup filtri (optional)
    allowed_groups = models.TextField(
        blank=True,
        verbose_name="İcazəli qruplar",
        help_text="Vergüllə ayırın: 850,860. Boş = bütün kurs",
    )

    # Metadata
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_labs",
        verbose_name="Yaradan",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Lab İşi"
        verbose_name_plural = "Lab İşləri"

    def __str__(self):
        return f"{self.course.title} - {self.title}"

    @property
    def is_open(self):
        """Lab açıqdır?"""
        now = timezone.now()
        return self.status == "published" and self.start_datetime <= now <= self.end_datetime

    @property
    def is_upcoming(self):
        """Lab hələ açılmayıb?"""
        return self.status == "published" and timezone.now() < self.start_datetime

    @property
    def is_closed(self):
        """Lab bağlanıb?"""
        return timezone.now() > self.end_datetime

    @property
    def total_questions(self):
        """Ümumi sual sayı"""
        return LabQuestion.objects.filter(block__lab=self).count()

    def get_allowed_groups_list(self):
        """İcazəli qrupları list kimi qaytar"""
        if not self.allowed_groups:
            return []
        return [g.strip() for g in self.allowed_groups.split(",") if g.strip()]

    def get_allowed_student_ids_list(self):
        """İcazəli tələbə ID-lərini list kimi qaytar"""
        return list(self.allowed_students.values_list("id", flat=True))

    def get_allowed_extensions_list(self):
        """İcazəli extension-ları list kimi qaytar"""
        return [ext.strip().lower() for ext in self.allowed_extensions.split(",") if ext.strip()]

    def _get_student_membership(self, user):
        """User bu kursda student üzvüdürsə membership qaytar"""
        if not getattr(user, "is_authenticated", False):
            return None

        from apps.courses.models import CourseMembership

        return (
            CourseMembership.objects.filter(course=self.course, user=user, role="student")
            .only("id", "group_name")
            .first()
        )

    def can_student_access(self, user):
        """
        Student access qaydası:
        - Kurs membership vacibdir
        - allowed_students / allowed_groups boşdursa bütün kurs
        - filterlərdən ən az biri uyğun gəlməlidir
        """
        membership = self._get_student_membership(user)
        if membership is None:
            return False

        has_allowed_students = self.allowed_students.exists()
        allowed_groups = {group.casefold() for group in self.get_allowed_groups_list()}

        if not has_allowed_students and not allowed_groups:
            return True

        if has_allowed_students and self.allowed_students.filter(pk=user.pk).exists():
            return True

        membership_group = (membership.group_name or "").strip().casefold()
        return bool(membership_group and membership_group in allowed_groups)

    def can_teacher_access(self, user):
        """Labı yalnız course owner və course teacher/assistant görə bilər"""
        if not getattr(user, "is_authenticated", False):
            return False

        if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
            return True

        if self.course.owner_id == user.id or self.created_by_id == user.id:
            return True

        from apps.courses.models import CourseMembership

        return CourseMembership.objects.filter(
            course=self.course,
            user=user,
            role__in=["teacher", "assistant"],
        ).exists()


# ════════════════════════════════════════════════════════════════════════════
# 2. LAB BLOCK MODEL
# ════════════════════════════════════════════════════════════════════════════


class LabBlock(models.Model):
    """
    Sual Bloku.

    Müəllim sualları bloklara ayıra bilər.
    Hər blokdan neçə sual düşəcəyini təyin edə bilər.
    """

    lab = models.ForeignKey(Lab, on_delete=models.CASCADE, related_name="blocks", verbose_name="Lab")

    title = models.CharField(
        max_length=255,
        verbose_name="Blok adı",
        help_text='Məs: "Asan suallar", "Orta", "Çətin"',
    )

    description = models.TextField(blank=True, verbose_name="Blok təsviri")

    order = models.PositiveIntegerField(default=1, verbose_name="Sıra")

    # Bu blokdan neçə sual düşsün?
    questions_to_pick = models.PositiveIntegerField(
        default=0,
        verbose_name="Bu blokdan seçiləcək sual sayı",
        help_text="0 = bütün suallar",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["lab", "order"]
        verbose_name = "Sual Bloku"
        verbose_name_plural = "Sual Blokları"

    def __str__(self):
        return f"{self.lab.title} - {self.title}"

    @property
    def question_count(self):
        return self.questions.count()


# ════════════════════════════════════════════════════════════════════════════
# 3. LAB QUESTION MODEL
# ════════════════════════════════════════════════════════════════════════════


class LabQuestion(models.Model):
    """
    Lab Sualı.

    Hər sual bir bloka aiddir.
    Müəllim tək-tək və ya toplu əlavə edə bilər.
    """

    block = models.ForeignKey(
        LabBlock,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="Blok",
    )

    question_number = models.PositiveIntegerField(default=1, verbose_name="Sual nömrəsi")

    question_text = models.TextField(verbose_name="Sual mətni")

    # Əlavə materiallar
    attachment = models.FileField(
        upload_to="labs/questions/%Y/%m/",
        blank=True,
        null=True,
        verbose_name="Əlavə fayl",
        validators=[FileUploadValidator()],
    )

    # Sual balı (optional, əgər suallar fərqli bal daşıyırsa)
    points = models.PositiveIntegerField(default=0, verbose_name="Bal", help_text="0 = bərabər paylanacaq")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["block", "question_number"]
        verbose_name = "Lab Sualı"
        verbose_name_plural = "Lab Sualları"

    def __str__(self):
        return f"Sual {self.question_number}: {self.question_text[:50]}..."


# ════════════════════════════════════════════════════════════════════════════
# 4. LAB ASSIGNMENT MODEL (Tələbəyə təyin olunan suallar)
# ════════════════════════════════════════════════════════════════════════════


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


# ════════════════════════════════════════════════════════════════════════════
# 5. LAB SUBMISSION MODEL
# ════════════════════════════════════════════════════════════════════════════


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


# ════════════════════════════════════════════════════════════════════════════
# 6. LAB ANSWER MODEL (Tələbənin hər suala verdiyi cavab)
## ════════════════════════════════════════════════════════════════════════════


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
