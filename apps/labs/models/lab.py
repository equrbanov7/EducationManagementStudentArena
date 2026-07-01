"""labs model paketi — Lab/LabBlock/LabQuestion (core)."""

from django.core.validators import MaxValueValidator
from django.db import models
from django.utils import timezone

from core.upload_security import FileUploadValidator

from ._base import (
    User,
)


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
