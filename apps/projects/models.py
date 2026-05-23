"""
projects/models.py
"""

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.courses.models import Course
from core.upload_security import FileUploadValidator

User = get_user_model()


class Project(models.Model):
    STATUS_CHOICES = [
        ("active", pgettext_lazy("projects.model.project.choice.status", "active")),
        ("inactive", pgettext_lazy("projects.model.project.choice.status", "inactive")),
        ("archived", pgettext_lazy("projects.model.project.choice.status", "archived")),
    ]

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="projects",
        verbose_name=pgettext_lazy("projects.model.project.field", "course"),
    )
    title = models.CharField(max_length=255, verbose_name=pgettext_lazy("projects.model.project.field", "title"))
    description = models.TextField(
        blank=True, verbose_name=pgettext_lazy("projects.model.project.field", "description")
    )
    start_date = models.DateTimeField(verbose_name=pgettext_lazy("projects.model.project.field", "start_date"))
    deadline = models.DateTimeField(verbose_name=pgettext_lazy("projects.model.project.field", "deadline"))
    max_attempts = models.PositiveIntegerField(
        default=1,
        verbose_name=pgettext_lazy("projects.model.project.field", "max_attempts"),
    )
    max_score = models.PositiveIntegerField(
        default=100,
        verbose_name=pgettext_lazy("projects.model.project.field", "max_score"),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

    assigned_students = models.ManyToManyField(
        User,
        blank=True,
        related_name="student_projects",
        verbose_name=pgettext_lazy("projects.model.project.field", "assigned_students"),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = pgettext_lazy("projects.model.project.meta", "singular")
        verbose_name_plural = pgettext_lazy("projects.model.project.meta", "plural")
        indexes = [
            # Course detail pages list a course's projects, often by status.
            models.Index(
                fields=["course", "status", "-created_at"],
                name="project_course_status_idx",
            ),
        ]

    def __str__(self):
        return f"{self.course.title} - {self.title}"

    @property
    def is_deadline_passed(self):
        return timezone.now() > self.deadline

    def get_submissions_count(self):
        return self.submissions.count()

    def get_pending_submissions(self):
        return self.submissions.filter(status="pending").count()

    def get_user_attempts(self, user):
        return self.submissions.filter(student=user).count()

    def can_user_submit(self, user):
        if not getattr(user, "is_authenticated", False):
            return False
        if not self.assigned_students.filter(id=user.id).exists():
            return False
        if self.is_deadline_passed:
            return False
        if self.status != "active":
            return False
        return self.get_user_attempts(user) < self.max_attempts


class ProjectSubmission(models.Model):
    STATUS_CHOICES = [
        ("pending", pgettext_lazy("projects.model.submission.choice.status", "pending")),
        ("graded", pgettext_lazy("projects.model.submission.choice.status", "graded")),
        ("rejected", pgettext_lazy("projects.model.submission.choice.status", "rejected")),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="project_submissions")
    content = models.TextField(verbose_name=pgettext_lazy("projects.model.submission.field", "content"))
    file = models.FileField(
        upload_to="projects/submissions/", blank=True, null=True, validators=[FileUploadValidator()]
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    grade = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    graded_at = models.DateTimeField(null=True, blank=True)
    graded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="graded_project_submissions",
    )

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = pgettext_lazy("projects.model.submission.meta", "singular")
        verbose_name_plural = pgettext_lazy("projects.model.submission.meta", "plural")
        indexes = [
            # Teacher review queue: a project's submissions filtered by status.
            models.Index(
                fields=["project", "status", "-submitted_at"],
                name="projsub_project_status_idx",
            ),
            # A student's own submissions across projects.
            models.Index(fields=["student", "-submitted_at"], name="projsub_student_idx"),
        ]
