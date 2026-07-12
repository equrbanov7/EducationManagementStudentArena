from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import pgettext_lazy

User = get_user_model()


class CodingExamQuestion(models.Model):
    LANGUAGE_JAVASCRIPT = "javascript"
    LANGUAGE_PYTHON = "python"
    LANGUAGE_CPP = "cpp"
    LANGUAGE_JAVA = "java"
    LANGUAGE_HTML = "html"

    LANGUAGE_CHOICES = (
        (LANGUAGE_JAVASCRIPT, pgettext_lazy("exams.model.coding.choice.language", "JavaScript")),
        (LANGUAGE_PYTHON, pgettext_lazy("exams.model.coding.choice.language", "Python")),
        (LANGUAGE_CPP, pgettext_lazy("exams.model.coding.choice.language", "C++")),
        (LANGUAGE_JAVA, pgettext_lazy("exams.model.coding.choice.language", "Java")),
        (LANGUAGE_HTML, pgettext_lazy("exams.model.coding.choice.language", "HTML/CSS/JS")),
    )

    DEFAULT_FILENAMES = {
        LANGUAGE_JAVASCRIPT: "main.js",
        LANGUAGE_PYTHON: "main.py",
        LANGUAGE_CPP: "main.cpp",
        LANGUAGE_JAVA: "Main.java",
        LANGUAGE_HTML: "index.html",
    }

    question = models.OneToOneField(
        "exams.ExamQuestion",
        on_delete=models.CASCADE,
        related_name="coding_details",
        verbose_name=pgettext_lazy("exams.model.coding_question.field", "question"),
    )
    language = models.CharField(
        max_length=30,
        choices=LANGUAGE_CHOICES,
        default=LANGUAGE_PYTHON,
        verbose_name=pgettext_lazy("exams.model.coding_question.field", "language"),
    )
    title = models.CharField(
        max_length=255,
        verbose_name=pgettext_lazy("exams.model.coding_question.field", "title"),
    )
    problem_statement = models.TextField(
        verbose_name=pgettext_lazy("exams.model.coding_question.field", "problem_statement"),
    )
    input_description = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.coding_question.field", "input_description"),
    )
    output_description = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.coding_question.field", "output_description"),
    )
    example_input = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.coding_question.field", "example_input"),
    )
    example_output = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.coding_question.field", "example_output"),
    )
    time_limit_seconds = models.PositiveIntegerField(
        default=2,
        verbose_name=pgettext_lazy("exams.model.coding_question.field", "time_limit_seconds"),
    )
    memory_limit_mb = models.PositiveIntegerField(
        default=128,
        verbose_name=pgettext_lazy("exams.model.coding_question.field", "memory_limit_mb"),
    )
    max_score = models.PositiveIntegerField(
        default=100,
        verbose_name=pgettext_lazy("exams.model.coding_question.field", "max_score"),
    )
    starter_code = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.coding_question.field", "starter_code"),
    )
    allow_file_creation = models.BooleanField(
        default=False,
        verbose_name=pgettext_lazy("exams.model.coding_question.field", "allow_file_creation"),
    )
    allow_multiple_files = models.BooleanField(
        default=False,
        verbose_name=pgettext_lazy("exams.model.coding_question.field", "allow_multiple_files"),
    )
    enable_code_execution = models.BooleanField(
        default=False,
        verbose_name=pgettext_lazy("exams.model.coding_question.field", "enable_code_execution"),
        help_text=pgettext_lazy("exams.model.coding_question.help", "enable_code_execution"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = pgettext_lazy("exams.model.coding_question.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.coding_question.meta", "plural")
        ordering = ["question__order", "id"]

    def __str__(self):
        return f"{self.title} ({self.get_language_display()})"

    @property
    def exam(self):
        return self.question.exam

    @property
    def default_filename(self):
        return self.DEFAULT_FILENAMES.get(self.language, "main.txt")


class CodingTestCase(models.Model):
    VISIBILITY_VISIBLE = "visible"
    VISIBILITY_HIDDEN = "hidden"

    VISIBILITY_CHOICES = (
        (VISIBILITY_VISIBLE, pgettext_lazy("exams.model.coding_test_case.choice.visibility", "visible")),
        (VISIBILITY_HIDDEN, pgettext_lazy("exams.model.coding_test_case.choice.visibility", "hidden")),
    )

    coding_question = models.ForeignKey(
        "exams.CodingExamQuestion",
        on_delete=models.CASCADE,
        related_name="test_cases",
        verbose_name=pgettext_lazy("exams.model.coding_test_case.field", "coding_question"),
    )
    input_data = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.coding_test_case.field", "input_data"),
    )
    expected_output = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.coding_test_case.field", "expected_output"),
    )
    visibility = models.CharField(
        max_length=12,
        choices=VISIBILITY_CHOICES,
        default=VISIBILITY_VISIBLE,
        verbose_name=pgettext_lazy("exams.model.coding_test_case.field", "visibility"),
    )
    point_value = models.PositiveIntegerField(
        default=1,
        verbose_name=pgettext_lazy("exams.model.coding_test_case.field", "point_value"),
    )
    order = models.PositiveIntegerField(
        default=1,
        verbose_name=pgettext_lazy("exams.model.coding_test_case.field", "order"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = pgettext_lazy("exams.model.coding_test_case.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.coding_test_case.meta", "plural")
        ordering = ["order", "id"]
        indexes = [
            models.Index(fields=["coding_question", "visibility", "order"]),
        ]

    def __str__(self):
        return f"{self.coding_question.title} - {self.get_visibility_display()} #{self.order}"


class CodingSubmission(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_SUCCESS = "success"
    STATUS_RUNTIME_ERROR = "runtime_error"
    STATUS_COMPILE_ERROR = "compile_error"
    STATUS_TIMEOUT = "timeout"
    STATUS_EXECUTION_DISABLED = "execution_disabled"
    STATUS_SANDBOX_UNAVAILABLE = "sandbox_unavailable"
    STATUS_SUBMITTED = "submitted"

    STATUS_CHOICES = (
        (STATUS_DRAFT, pgettext_lazy("exams.model.coding_submission.choice.status", "draft")),
        (STATUS_SUCCESS, pgettext_lazy("exams.model.coding_submission.choice.status", "success")),
        (STATUS_RUNTIME_ERROR, pgettext_lazy("exams.model.coding_submission.choice.status", "runtime_error")),
        (STATUS_COMPILE_ERROR, pgettext_lazy("exams.model.coding_submission.choice.status", "compile_error")),
        (STATUS_TIMEOUT, pgettext_lazy("exams.model.coding_submission.choice.status", "timeout")),
        (
            STATUS_EXECUTION_DISABLED,
            pgettext_lazy("exams.model.coding_submission.choice.status", "execution_disabled"),
        ),
        (
            STATUS_SANDBOX_UNAVAILABLE,
            pgettext_lazy("exams.model.coding_submission.choice.status", "sandbox_unavailable"),
        ),
        (STATUS_SUBMITTED, pgettext_lazy("exams.model.coding_submission.choice.status", "submitted")),
    )

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="coding_submissions",
        verbose_name=pgettext_lazy("exams.model.coding_submission.field", "student"),
    )
    exam = models.ForeignKey(
        "exams.Exam",
        on_delete=models.CASCADE,
        related_name="coding_submissions",
        verbose_name=pgettext_lazy("exams.model.coding_submission.field", "exam"),
    )
    attempt = models.ForeignKey(
        "exams.ExamAttempt",
        on_delete=models.CASCADE,
        related_name="coding_submissions",
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.coding_submission.field", "attempt"),
    )
    question = models.ForeignKey(
        "exams.CodingExamQuestion",
        on_delete=models.CASCADE,
        related_name="submissions",
        verbose_name=pgettext_lazy("exams.model.coding_submission.field", "question"),
    )
    selected_language = models.CharField(
        max_length=30,
        choices=CodingExamQuestion.LANGUAGE_CHOICES,
        verbose_name=pgettext_lazy("exams.model.coding_submission.field", "selected_language"),
    )
    submitted_code = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.coding_submission.field", "submitted_code"),
    )
    files = models.JSONField(
        default=list,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.coding_submission.field", "files"),
    )
    output = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.coding_submission.field", "output"),
    )
    error_message = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.coding_submission.field", "error_message"),
    )
    execution_status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        verbose_name=pgettext_lazy("exams.model.coding_submission.field", "execution_status"),
    )
    score = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.coding_submission.field", "score"),
    )
    test_results = models.JSONField(
        default=list,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.coding_submission.field", "test_results"),
    )
    execution_time_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.coding_submission.field", "execution_time_ms"),
    )
    memory_usage_kb = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.coding_submission.field", "memory_usage_kb"),
    )
    is_final = models.BooleanField(
        default=False,
        verbose_name=pgettext_lazy("exams.model.coding_submission.field", "is_final"),
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = pgettext_lazy("exams.model.coding_submission.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.coding_submission.meta", "plural")
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(fields=["student", "exam", "-submitted_at"]),
            models.Index(fields=["attempt", "question", "is_final"]),
            models.Index(fields=["execution_status"]),
        ]
        constraints = [
            # EXAM-P1-13: bir (attempt, question) üçün ən çoxu BİR final
            # submission ola bilər — paralel submit dublikat final yarada
            # bilməz. attempt NULL ola bildiyi üçün şərtə daxil edilir.
            models.UniqueConstraint(
                fields=["attempt", "question"],
                condition=models.Q(is_final=True, attempt__isnull=False),
                name="uniq_final_coding_submission_per_attempt_question",
            ),
        ]

    def __str__(self):
        return f"{self.student.username} - {self.question.title} ({self.execution_status})"


class CodingFile(models.Model):
    submission = models.ForeignKey(
        "exams.CodingSubmission",
        on_delete=models.CASCADE,
        related_name="code_files",
        verbose_name=pgettext_lazy("exams.model.coding_file.field", "submission"),
    )
    name = models.CharField(
        max_length=180,
        verbose_name=pgettext_lazy("exams.model.coding_file.field", "name"),
    )
    content = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.coding_file.field", "content"),
    )
    language = models.CharField(
        max_length=30,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.coding_file.field", "language"),
    )
    is_main = models.BooleanField(
        default=False,
        verbose_name=pgettext_lazy("exams.model.coding_file.field", "is_main"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = pgettext_lazy("exams.model.coding_file.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.coding_file.meta", "plural")
        ordering = ["-is_main", "name"]
        unique_together = ("submission", "name")

    def __str__(self):
        return f"{self.name} ({self.submission_id})"


__all__ = [
    "CodingExamQuestion",
    "CodingFile",
    "CodingSubmission",
    "CodingTestCase",
]
