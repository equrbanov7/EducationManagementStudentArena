from django.contrib.auth import get_user_model
from django.db import models

from apps.courses.models import Course

User = get_user_model()


class Assignment(models.Model):
    """Sərbəst iş modeli - Sprint 8 Enhanced"""

    TYPE_CHOICES = [
        ("homework", "Ev Tapşırığı"),
        ("quiz", "Kviz"),
        ("lab", "Laboratoriya"),
        ("midterm", "Midterm İmtahan"),
        ("final", "Final İmtahan"),
        ("project", "Layihə"),
    ]

    STATUS_CHOICES = [
        ("draft", "Qaralama"),
        ("published", "Yayımlandı"),
        ("archived", "Arxivləndi"),
    ]

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name="Kurs",
    )

    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default="homework",
        verbose_name="Tapşırıq Tipi",
    )

    title = models.CharField(max_length=255, verbose_name="Başlıq")
    description = models.TextField(blank=True, verbose_name="Təsvir")
    instructions = models.TextField(blank=True, verbose_name="Təlimatlar")

    max_score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=100.00,
        verbose_name="Maksimum Bal",
    )

    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1.00,
        verbose_name="Çəki/Əhəmiyyət",
        help_text="Ümumi qiymətdə çəkisi (məs: 0.1 = 10%)",
    )

    start_date = models.DateTimeField(
        verbose_name="Başlanğıc tarixi",
        help_text="Tələbələr bu tarixdən sonra cavab verə bilər",
    )

    due_date = models.DateTimeField(
        verbose_name="Son Tarix",
        null=True,
        blank=True,
    )

    allow_late = models.BooleanField(
        default=False,
        verbose_name="Gecikmiş Təslimatı İcazə Ver",
    )

    late_penalty_per_day = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        verbose_name="Gecikmiş Cərimə (gün başına)",
        help_text="Hər gün üçün çıxılacaq bal faizi (məs: 10.00 = 10%)",
    )

    max_attempts = models.PositiveIntegerField(default=1, verbose_name="Maksimum cəhd")

    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_assignments",
        verbose_name="Yaradan",
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="draft", verbose_name="Status"
    )

    # Tələbələr və ya qruplar
    assigned_students = models.ManyToManyField(
        User, blank=True, related_name="student_assignments", verbose_name="Tələbələr"
    )
    # Qrup seçimi CourseMembership-dən group_name-ə əsasən
    # assigned_groups field-i silindi, çünki Group modeli yoxdur

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Sərbəst İş"
        verbose_name_plural = "Sərbəst İşlər"

    def __str__(self):
        return f"{self.course.title} - {self.title}"

    @property
    def is_deadline_passed(self):
        from django.utils import timezone

        return self.due_date and timezone.now() > self.due_date

    def get_user_attempts(self, user):
        """İstifadəçinin cəhd sayını qaytarır"""
        return self.submissions.filter(user=user).count()

    def get_submissions_count(self):
        """Ümumi cavab sayı"""
        return self.submissions.count()

    def get_pending_submissions(self):
        """Yoxlanılmayan cavablar"""
        return self.submissions.filter(status="submitted").count()

    def can_user_submit(self, user):
        """İstifadəçi cavab verə bilərmi?"""
        from django.utils import timezone

        if not self.allow_late and self.is_deadline_passed:
            return False
        if self.status != "published":
            return False
        if timezone.now() < self.start_date:
            return False
        attempts = self.get_user_attempts(user)
        return attempts < self.max_attempts


class Submission(models.Model):
    """Tapşırığa cavab modeli - Sprint 8 Enhanced"""

    STATUS_CHOICES = [
        ("submitted", "Təslim Edilib"),
        ("grading", "Qiymətləndiriliir"),
        ("graded", "Qiymətləndirilib"),
        ("returned", "Qaytarılıb"),
    ]

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="submissions",
        verbose_name="Tapşırıq",
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="submissions",
        verbose_name="Tələbə",
    )

    attempt_number = models.PositiveIntegerField(
        default=1,
        verbose_name="Cəhd Nömrəsi",
    )

    content = models.TextField(blank=True, verbose_name="Cavab Mətni")

    files = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Yüklənmiş Fayllar",
        help_text="JSON siyahısı: [{name, path, size}]",
    )

    submitted_at = models.DateTimeField(auto_now_add=True, verbose_name="Təslim Tarixi")

    is_late = models.BooleanField(
        default=False,
        verbose_name="Gecikib?",
    )

    late_days = models.IntegerField(
        default=0,
        verbose_name="Gecikən Gün Sayı",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="submitted",
        verbose_name="Status",
    )

    grade = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Qiymət",
    )

    feedback = models.TextField(blank=True, verbose_name="Rəy")

    graded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="graded_submissions",
        verbose_name="Qiymətləndirən",
    )

    graded_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Qiymətləndirmə Tarixi"
    )

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = "Təslimat"
        verbose_name_plural = "Təslimatlar"
        indexes = [
            models.Index(fields=["assignment", "user"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.assignment.title} (Cəhd #{self.attempt_number})"

    def save(self, *args, **kwargs):
        """Calculate if late on save"""
        if not self.pk and self.assignment.due_date:
            from django.utils import timezone

            if timezone.now() > self.assignment.due_date:
                self.is_late = True
                delta = timezone.now() - self.assignment.due_date
                self.late_days = delta.days
        super().save(*args, **kwargs)


# Keep old model for backward compatibility
AssignmentSubmission = Submission


class Notification(models.Model):
    """Bildiriş modeli - Sprint 8"""

    TYPE_CHOICES = [
        ("deadline", "Son Tarix Xatırlatması"),
        ("submission", "Yeni Təslimat"),
        ("grade", "Qiymət Verildi"),
        ("system", "Sistem Bildirişi"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="İstifadəçi",
    )

    title = models.CharField(max_length=255, verbose_name="Başlıq")
    message = models.TextField(verbose_name="Mesaj")

    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default="system",
        verbose_name="Bildiriş Tipi",
    )

    is_read = models.BooleanField(default=False, verbose_name="Oxunub?")

    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Yaradılma Tarixi"
    )

    link = models.URLField(blank=True, null=True, verbose_name="Link")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Bildiriş"
        verbose_name_plural = "Bildirişlər"
        indexes = [
            models.Index(fields=["user", "is_read"]),
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.title}"

    def mark_as_read(self):
        """Bildirişi oxunmuş kimi işarələ"""
        self.is_read = True
        self.save(update_fields=["is_read"])
