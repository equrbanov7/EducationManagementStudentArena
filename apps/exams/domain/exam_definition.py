from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.text import slugify
from django.utils.translation import pgettext_lazy

from apps.exams.constants import (
    ATTEMPT_FINISHED_STATUSES,
    EXAM_STATUS_ACTIVE,
    EXAM_STATUS_ARCHIVED,
    EXAM_STATUS_DRAFT,
    EXAM_STATUS_SCHEDULED,
)

from .access_policy import ExamAccessPolicyMixin

User = get_user_model()


class Exam(ExamAccessPolicyMixin, models.Model):
    EXAM_TYPE_CHOICES = (
        ("test", pgettext_lazy("exams.model.exam.choice.exam_type", "test")),
        ("written", pgettext_lazy("exams.model.exam.choice.exam_type", "written")),
        ("coding", pgettext_lazy("exams.model.exam.choice.exam_type", "Practical Coding Exam")),
    )
    EXAM_TYPE_EXTENDED_CHOICES = (
        ("quiz", pgettext_lazy("exams.model.exam.choice.exam_type_extended", "quiz")),
        ("midterm", pgettext_lazy("exams.model.exam.choice.exam_type_extended", "midterm")),
        ("final", pgettext_lazy("exams.model.exam.choice.exam_type_extended", "final")),
        ("placement", pgettext_lazy("exams.model.exam.choice.exam_type_extended", "placement")),
        ("practice", pgettext_lazy("exams.model.exam.choice.exam_type_extended", "practice")),
    )
    MODE_CHOICES = (
        ("online", pgettext_lazy("exams.model.exam.choice.mode", "online")),
        ("offline", pgettext_lazy("exams.model.exam.choice.mode", "offline")),
        ("hybrid", pgettext_lazy("exams.model.exam.choice.mode", "hybrid")),
    )
    PROCTORING_LEVEL_CHOICES = (
        ("none", pgettext_lazy("exams.model.exam.choice.proctoring_level", "none")),
        ("basic", pgettext_lazy("exams.model.exam.choice.proctoring_level", "basic")),
        ("strict", pgettext_lazy("exams.model.exam.choice.proctoring_level", "strict")),
    )

    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="exams",
        verbose_name=pgettext_lazy("exams.model.exam.field", "author"),
    )
    title = models.CharField(
        max_length=200,
        verbose_name=pgettext_lazy("exams.model.exam.field", "title"),
    )
    description = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.exam.field", "description"),
    )
    exam_type = models.CharField(
        pgettext_lazy("exams.model.exam.field", "exam_type"),
        max_length=20,
        choices=EXAM_TYPE_CHOICES,
        default="test",
    )
    start_datetime = models.DateTimeField(
        pgettext_lazy("exams.model.exam.field", "start_datetime"),
        blank=True,
        null=True,
        help_text=pgettext_lazy("exams.model.exam.help", "start_datetime"),
    )
    end_datetime = models.DateTimeField(
        pgettext_lazy("exams.model.exam.field", "end_datetime"),
        blank=True,
        null=True,
        help_text=pgettext_lazy("exams.model.exam.help", "end_datetime"),
    )
    is_active = models.BooleanField(
        pgettext_lazy("exams.model.exam.field", "is_active"),
        default=False,
        help_text=pgettext_lazy("exams.model.exam.help", "is_active"),
    )
    results_hidden_from_students = models.BooleanField(
        pgettext_lazy("exams.model.exam.field", "results_hidden_from_students"),
        default=False,
        help_text=pgettext_lazy("exams.model.exam.help", "results_hidden_from_students"),
    )
    total_duration_minutes = models.PositiveIntegerField(
        pgettext_lazy("exams.model.exam.field", "total_duration_minutes"),
        blank=True,
        null=True,
        help_text=pgettext_lazy("exams.model.exam.help", "total_duration_minutes"),
    )
    default_question_time_seconds = models.PositiveIntegerField(
        pgettext_lazy("exams.model.exam.field", "default_question_time_seconds"),
        blank=True,
        null=True,
        help_text=pgettext_lazy("exams.model.exam.help", "default_question_time_seconds"),
    )
    max_attempts_per_user = models.PositiveIntegerField(
        pgettext_lazy("exams.model.exam.field", "max_attempts_per_user"),
        blank=True,
        null=True,
        help_text=pgettext_lazy("exams.model.exam.help", "max_attempts_per_user"),
    )
    random_question_count = models.PositiveIntegerField(
        pgettext_lazy("exams.model.exam.field", "random_question_count"),
        default=10,
        help_text=pgettext_lazy("exams.model.exam.help", "random_question_count"),
    )
    fair_question_distribution_enabled = models.BooleanField(
        pgettext_lazy("exams.model.exam.field", "fair_question_distribution_enabled"),
        default=True,
        help_text=pgettext_lazy("exams.model.exam.help", "fair_question_distribution_enabled"),
    )
    ai_difficulty_balance_enabled = models.BooleanField(
        pgettext_lazy("exams.model.exam.field", "ai_difficulty_balance_enabled"),
        default=False,
        help_text=pgettext_lazy("exams.model.exam.help", "ai_difficulty_balance_enabled"),
    )
    default_question_points = models.PositiveIntegerField(default=1)
    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exams",
        verbose_name=pgettext_lazy("exams.model.exam.field", "course"),
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="exams",
        verbose_name=pgettext_lazy("exams.model.exam.field", "organization"),
        help_text=pgettext_lazy("exams.model.exam.help", "organization"),
    )
    exam_type_extended = models.CharField(
        pgettext_lazy("exams.model.exam.field", "exam_type_extended"),
        max_length=20,
        choices=EXAM_TYPE_EXTENDED_CHOICES,
        blank=True,
        null=True,
        help_text=pgettext_lazy("exams.model.exam.help", "exam_type_extended"),
    )
    mode = models.CharField(
        pgettext_lazy("exams.model.exam.field", "mode"),
        max_length=20,
        choices=MODE_CHOICES,
        default="online",
    )
    proctoring_level = models.CharField(
        pgettext_lazy("exams.model.exam.field", "proctoring_level"),
        max_length=20,
        choices=PROCTORING_LEVEL_CHOICES,
        default="none",
    )
    settings = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.exam.field", "settings"),
        help_text=pgettext_lazy("exams.model.exam.help", "settings"),
    )
    is_public = models.BooleanField(
        pgettext_lazy("exams.model.exam.field", "is_public"),
        default=True,
        help_text=pgettext_lazy("exams.model.exam.help", "is_public"),
    )
    allowed_users = models.ManyToManyField(
        User,
        related_name="allowed_exams",
        blank=True,
        verbose_name=pgettext_lazy("exams.model.exam.field", "allowed_users"),
        help_text=pgettext_lazy("exams.model.exam.help", "allowed_users"),
    )
    allowed_groups = models.ManyToManyField(
        "exams.StudentGroup",
        related_name="exams",
        blank=True,
        verbose_name=pgettext_lazy("exams.model.exam.field", "allowed_groups"),
        help_text=pgettext_lazy("exams.model.exam.help", "allowed_groups"),
    )
    access_code = models.CharField(
        pgettext_lazy("exams.model.exam.field", "access_code"),
        max_length=6,
        blank=True,
        help_text=pgettext_lazy("exams.model.exam.help", "access_code"),
    )
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    enable_paint = models.BooleanField(
        pgettext_lazy("exams.model.exam.field", "enable_paint"),
        default=False,
        help_text=pgettext_lazy("exams.model.exam.help", "enable_paint"),
    )
    # Müəllim imtahanı arxivləyə bilər: nəticələr saxlanır, amma siyahıda
    # "Arxiv" bölməsinə keçir və tələbələrə təqdim olunmur (is_active ayrıca
    # idarə olunur). Soft-state — silmə deyil, geri qaytarıla bilər.
    is_archived = models.BooleanField(
        pgettext_lazy("exams.model.exam.field", "is_archived"),
        default=False,
        db_index=True,
        help_text=pgettext_lazy("exams.model.exam.help", "is_archived"),
    )
    archived_at = models.DateTimeField(
        pgettext_lazy("exams.model.exam.field", "archived_at"),
        blank=True,
        null=True,
        help_text=pgettext_lazy("exams.model.exam.help", "archived_at"),
    )

    class Meta:
        verbose_name = pgettext_lazy("exams.model.exam.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.exam.meta", "plural")
        ordering = ["-created_at"]
        indexes = [
            # Tenant-scoped exam lists are the hottest query on this table:
            # dashboards and exam pages always filter by organization, then
            # narrow by active state / type, and order newest-first.
            # Explicit name= keeps the DB index name readable and stops Django
            # from generating a RenameIndex migration.
            models.Index(
                fields=["organization", "is_active", "-created_at"],
                name="exam_org_active_created_idx",
            ),
            models.Index(
                fields=["organization", "exam_type", "-created_at"],
                name="exam_org_type_created_idx",
            ),
            # Course detail pages list a course's exams newest-first.
            models.Index(fields=["course", "-created_at"], name="exam_course_created_idx"),
            # "My exams" (teacher) — exams authored by a given user.
            models.Index(fields=["author", "-created_at"], name="exam_author_created_idx"),
            # "My exams" arxiv qruplaşdırması — müəllimin aktiv/arxiv imtahanları.
            models.Index(fields=["author", "is_archived", "-created_at"], name="exam_author_archived_idx"),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_exam_type_display()})"

    def save(self, *args, **kwargs):
        if self.course_id and getattr(self.course, "organization_id", None):
            self.organization = self.course.organization
        elif self.organization_id is None and self.author_id:
            profile = getattr(self.author, "profile", None)
            self.organization = getattr(profile, "organization", None)

        if self.organization_id is None:
            raise ValidationError(pgettext_lazy("exams.model.exam.error", "organization_required"))

        if not self.slug:
            base_slug = slugify(self.title)
            self.slug = f"{base_slug}-{get_random_string(6)}"
        super().save(*args, **kwargs)

    def is_before_start(self) -> bool:
        if not self.start_datetime:
            return False
        return timezone.now() < self.start_datetime

    def is_after_end(self) -> bool:
        if not self.end_datetime:
            return False
        return timezone.now() > self.end_datetime

    def is_currently_active(self) -> bool:
        return not self.is_before_start() and not self.is_after_end()

    @property
    def lifecycle_status(self) -> str:
        """
        Müəllim panelində qruplaşdırma üçün hesablanmış status:

        * ``archived``  — müəllim arxivləyib (``is_archived``).
        * ``draft``     — hələ dərc edilməyib (``is_active`` = False).
        * ``scheduled`` — aktiv, amma başlama vaxtından əvvəl.
        * ``active``    — aktiv və indi tələbələrə açıqdır.

        Mənbə yeganədir: şablonlar, KPI sayğacları və filtrlər hamısı bu
        propertydən istifadə edir ki, status məntiqi bir yerdə qalsın.
        """
        if self.is_archived:
            return EXAM_STATUS_ARCHIVED
        if not self.is_active:
            return EXAM_STATUS_DRAFT
        if self.is_before_start():
            return EXAM_STATUS_SCHEDULED
        return EXAM_STATUS_ACTIVE

    def attempts_left_for(self, user: User) -> int | None:
        if not self.max_attempts_per_user:
            return None

        self._expire_stale_attempts_for(user)
        used = self.attempts.filter(user=user, status__in=ATTEMPT_FINISHED_STATUSES).count()
        left = self.max_attempts_per_user - used
        return max(left, 0)


class QuestionBlock(models.Model):
    exam = models.ForeignKey(
        "exams.Exam",
        on_delete=models.CASCADE,
        related_name="question_blocks",
        verbose_name=pgettext_lazy("exams.model.question_block.field", "exam"),
    )
    name = models.CharField(
        max_length=100,
        verbose_name=pgettext_lazy("exams.model.question_block.field", "name"),
    )
    order = models.PositiveIntegerField(
        default=1,
        verbose_name=pgettext_lazy("exams.model.question_block.field", "order"),
    )
    time_limit_minutes = models.PositiveIntegerField(
        pgettext_lazy("exams.model.question_block.field", "time_limit_minutes"),
        null=True,
        blank=True,
        help_text=pgettext_lazy("exams.model.question_block.help", "time_limit_minutes"),
    )
    enable_paint = models.BooleanField(
        null=True,
        blank=True,
        default=None,
        help_text=pgettext_lazy("exams.model.question_block.help", "enable_paint"),
    )

    class Meta:
        verbose_name = pgettext_lazy("exams.model.question_block.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.question_block.meta", "plural")
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.exam.title} - {self.name}"


__all__ = [
    "Exam",
    "QuestionBlock",
]
