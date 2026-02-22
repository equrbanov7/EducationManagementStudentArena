from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import pgettext_lazy

from apps.courses.models import Course

User = get_user_model()


class Assignment(models.Model):
    """Sərbəst iş modeli - Sprint 8 Enhanced"""

    TYPE_CHOICES = [
        ("homework", pgettext_lazy("assignment.choice.type", "homework")),
        ("quiz", pgettext_lazy("assignment.choice.type", "quiz")),
        ("lab", pgettext_lazy("assignment.choice.type", "lab")),
        ("midterm", pgettext_lazy("assignment.choice.type", "midterm")),
        ("final", pgettext_lazy("assignment.choice.type", "final")),
        ("project", pgettext_lazy("assignment.choice.type", "project")),
    ]

    STATUS_CHOICES = [
        ("draft", pgettext_lazy("assignment.choice.status", "draft")),
        ("published", pgettext_lazy("assignment.choice.status", "published")),
        # Backward compatibility with older UI/API values
        ("active", pgettext_lazy("assignment.choice.status", "active")),
        ("inactive", pgettext_lazy("assignment.choice.status", "inactive")),
        ("archived", pgettext_lazy("assignment.choice.status", "archived")),
    ]

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name=pgettext_lazy("assignment.model.field", "course"),
    )

    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default="homework",
        verbose_name=pgettext_lazy("assignment.model.field", "assignment_type"),
    )

    title = models.CharField(max_length=255, verbose_name=pgettext_lazy("assignment.model.field", "title"))
    description = models.TextField(blank=True, verbose_name=pgettext_lazy("assignment.model.field", "description"))
    instructions = models.TextField(
        blank=True, verbose_name=pgettext_lazy("assignment.model.field", "instructions")
    )

    max_score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=100.00,
        verbose_name=pgettext_lazy("assignment.model.field", "max_score"),
    )

    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1.00,
        verbose_name=pgettext_lazy("assignment.model.field", "weight"),
        help_text=pgettext_lazy("assignment.model.help", "weight_ratio"),
    )

    start_date = models.DateTimeField(
        verbose_name=pgettext_lazy("assignment.model.field", "start_date"),
        help_text=pgettext_lazy("assignment.model.help", "start_date_for_submission"),
    )

    due_date = models.DateTimeField(
        verbose_name=pgettext_lazy("assignment.model.field", "due_date"),
        null=True,
        blank=True,
    )

    allow_late = models.BooleanField(
        default=False,
        verbose_name=pgettext_lazy("assignment.model.field", "allow_late_submission"),
    )

    late_penalty_per_day = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        verbose_name=pgettext_lazy("assignment.model.field", "late_penalty_per_day"),
        help_text=pgettext_lazy("assignment.model.help", "late_penalty_description"),
    )

    max_attempts = models.PositiveIntegerField(
        default=1, verbose_name=pgettext_lazy("assignment.model.field", "max_attempts")
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_assignments",
        verbose_name=pgettext_lazy("assignment.model.field", "created_by"),
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft",
        verbose_name=pgettext_lazy("assignment.model.field", "status"),
    )

    # Tələbələr və ya qruplar
    assigned_students = models.ManyToManyField(
        User,
        blank=True,
        related_name="student_assignments",
        verbose_name=pgettext_lazy("assignment.model.field", "students"),
    )
    # Qrup seçimi CourseMembership-dən group_name-ə əsasən
    # assigned_groups field-i silindi, çünki Group modeli yoxdur

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __init__(self, *args, **kwargs):
        # Backward compatibility: old code may still pass `deadline`.
        if "deadline" in kwargs and "due_date" not in kwargs:
            kwargs["due_date"] = kwargs.pop("deadline")
        super().__init__(*args, **kwargs)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = pgettext_lazy("assignment.model.meta", "verbose_name")
        verbose_name_plural = pgettext_lazy("assignment.model.meta", "verbose_name_plural")

    def __str__(self):
        return f"{self.course.title} - {self.title}"

    @property
    def deadline(self):
        # Backward compatibility for templates/old views.
        return self.due_date

    @deadline.setter
    def deadline(self, value):
        self.due_date = value

    @property
    def is_deadline_passed(self):
        from django.utils import timezone

        return self.due_date and timezone.now() > self.due_date

    @property
    def is_open_status(self):
        return self.status in {"active", "published"}

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
        if not self.is_open_status:
            return False
        if timezone.now() < self.start_date:
            return False
        attempts = self.get_user_attempts(user)
        return attempts < self.max_attempts


class Submission(models.Model):
    """Tapşırığa cavab modeli - Sprint 8 Enhanced"""

    STATUS_CHOICES = [
        ("submitted", pgettext_lazy("assignment.submission.choice.status", "submitted")),
        ("grading", pgettext_lazy("assignment.submission.choice.status", "grading")),
        ("graded", pgettext_lazy("assignment.submission.choice.status", "graded")),
        ("returned", pgettext_lazy("assignment.submission.choice.status", "returned")),
    ]

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="submissions",
        verbose_name=pgettext_lazy("assignment.submission.field", "assignment"),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="submissions",
        verbose_name=pgettext_lazy("assignment.submission.field", "student"),
    )

    attempt_number = models.PositiveIntegerField(
        default=1,
        verbose_name=pgettext_lazy("assignment.submission.field", "attempt_number"),
    )

    content = models.TextField(blank=True, verbose_name=pgettext_lazy("assignment.submission.field", "content"))

    files = models.JSONField(
        default=list,
        blank=True,
        verbose_name=pgettext_lazy("assignment.submission.field", "uploaded_files"),
        help_text=pgettext_lazy("assignment.submission.help", "files_json_format"),
    )

    submitted_at = models.DateTimeField(
        auto_now_add=True, verbose_name=pgettext_lazy("assignment.submission.field", "submitted_at")
    )

    is_late = models.BooleanField(
        default=False,
        verbose_name=pgettext_lazy("assignment.submission.field", "is_late"),
    )

    late_days = models.IntegerField(
        default=0,
        verbose_name=pgettext_lazy("assignment.submission.field", "late_days"),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="submitted",
        verbose_name=pgettext_lazy("assignment.submission.field", "status"),
    )

    grade = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("assignment.submission.field", "grade"),
    )

    feedback = models.TextField(blank=True, verbose_name=pgettext_lazy("assignment.submission.field", "feedback"))

    graded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="graded_submissions",
        verbose_name=pgettext_lazy("assignment.submission.field", "graded_by"),
    )

    graded_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("assignment.submission.field", "graded_at"),
    )

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = pgettext_lazy("assignment.submission.meta", "verbose_name")
        verbose_name_plural = pgettext_lazy("assignment.submission.meta", "verbose_name_plural")
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
        ("deadline", pgettext_lazy("assignment.notification.choice.type", "deadline")),
        ("submission", pgettext_lazy("assignment.notification.choice.type", "submission")),
        ("grade", pgettext_lazy("assignment.notification.choice.type", "grade")),
        ("system", pgettext_lazy("assignment.notification.choice.type", "system")),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name=pgettext_lazy("assignment.notification.field", "user"),
    )

    title = models.CharField(max_length=255, verbose_name=pgettext_lazy("assignment.notification.field", "title"))
    message = models.TextField(verbose_name=pgettext_lazy("assignment.notification.field", "message"))

    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default="system",
        verbose_name=pgettext_lazy("assignment.notification.field", "notification_type"),
    )

    is_read = models.BooleanField(default=False, verbose_name=pgettext_lazy("assignment.notification.field", "is_read"))

    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name=pgettext_lazy("assignment.notification.field", "created_at")
    )

    link = models.URLField(blank=True, null=True, verbose_name=pgettext_lazy("assignment.notification.field", "link"))

    class Meta:
        ordering = ["-created_at"]
        verbose_name = pgettext_lazy("assignment.notification.meta", "verbose_name")
        verbose_name_plural = pgettext_lazy("assignment.notification.meta", "verbose_name_plural")
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
