"""
Müəllim → İmtahan mərkəzi sual göndərişi (elektron proses).

Axın:
1. Müəllim sual mətnini yazır/yükləyir → parser xəbərdarlıqlarını GÖRÜR
   (preview), istəsə düzəldir, istəsə elə beləcə göndərir.
2. Göndəriş imtahan mərkəzinin qutusuna düşür (``pending``); mərkəz üzvlərinə
   bildiriş gedir.
3. İmtahan mərkəzi eyni xəbərdarlıqları görərək baxır:
   * qəbul → suallar avtomatik seçilmiş/yeni sual bankına əlavə olunur;
   * rədd → qeyd ilə müəllimə qaytarılır; müəllim düzəldib YENİDƏN göndərə
     bilər (eyni qeyd üzərində, ``resubmission_count`` artır).

``parsed_snapshot`` göndəriş anındakı parse nəticəsidir (suallar + hər sualın
xəbərdarlıqları) — mərkəz müəllimin gördüyü eyni mənzərəni görür və qəbul
zamanı banka məhz bu snapshot yazılır (raw mətn sonradan dəyişsə belə).
"""

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from apps.exams.constants import DEFAULT_EXAM_LANGUAGE, EXAM_LANGUAGE_CHOICES

User = settings.AUTH_USER_MODEL


class QuestionSubmission(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = (
        (STATUS_PENDING, pgettext_lazy("exams.model.question_submission.choice.status", "pending")),
        (STATUS_ACCEPTED, pgettext_lazy("exams.model.question_submission.choice.status", "accepted")),
        (STATUS_REJECTED, pgettext_lazy("exams.model.question_submission.choice.status", "rejected")),
    )

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="question_submissions",
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "organization"),
    )
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="question_submissions",
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "teacher"),
    )
    title = models.CharField(
        max_length=200,
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "title"),
        help_text=pgettext_lazy("exams.model.question_submission.help", "title"),
    )
    # Hansı fənn üçündür — mərkəz bankları fənn üzrə qruplaşdırır.
    # Boş olmaması servis qatında (submit/resubmit) tələb olunur.
    subject = models.CharField(
        max_length=200,
        default="",
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "subject"),
    )
    # Hansı qrup üçündür. FK müəllimin seçdiyi qrupdursa dolur; qrup siyahıda
    # yoxdursa sərbəst mətn `group_label`-də saxlanır (akademik struktur
    # universitetdən-universitetə dəyişir — sərt FK məcburiyyəti qoymuruq).
    student_group = models.ForeignKey(
        "exams.StudentGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="question_submissions",
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "student_group"),
    )
    group_label = models.CharField(
        max_length=200,
        default="",
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "group_label"),
    )
    language = models.CharField(
        max_length=10,
        choices=EXAM_LANGUAGE_CHOICES,
        default=DEFAULT_EXAM_LANGUAGE,
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "language"),
    )
    raw_text = models.TextField(
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "raw_text"),
    )
    # Müəllimin imtahan mərkəzinə əlavə qeydi/mesajı (opsional).
    teacher_note = models.TextField(
        blank=True,
        default="",
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "teacher_note"),
    )
    # Göndəriş anındakı parse nəticəsi: [{q_no, text, options, correct,
    # answer_mode, warnings: [{type, msg, severity}]}, ...]
    parsed_snapshot = models.JSONField(default=list, blank=True)
    question_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "status"),
    )
    # Rədd → düzəliş → yenidən göndərmə dövrlərinin sayı.
    resubmission_count = models.PositiveIntegerField(default=0)

    reviewer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_question_submissions",
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "reviewer"),
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewer_note = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "reviewer_note"),
    )
    # Qəbul zamanı sualların yazıldığı bank (audit üçün saxlanır).
    accepted_bank = models.ForeignKey(
        "exams.QuestionBank",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accepted_submissions",
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "accepted_bank"),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = pgettext_lazy("exams.model.question_submission.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.question_submission.meta", "plural")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["organization", "status", "-created_at"], name="qsub_org_status_idx"),
            models.Index(fields=["teacher", "-created_at"], name="qsub_teacher_created_idx"),
        ]

    def __str__(self):
        return f"QuestionSubmission#{self.pk} · {self.title} · {self.status}"

    @property
    def is_pending(self):
        return self.status == self.STATUS_PENDING

    @property
    def can_be_edited_by_teacher(self):
        """Müəllim yalnız hələ baxılmamış və ya rədd edilmiş göndərişi düzəldə bilər."""
        return self.status in (self.STATUS_PENDING, self.STATUS_REJECTED)


__all__ = ["QuestionSubmission"]
