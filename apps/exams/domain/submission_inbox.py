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

from apps.exams.constants import (
    DEFAULT_EXAM_LANGUAGE,
    EXAM_LANGUAGE_CHOICES,
    QUESTION_EXAM_KIND_CHOICES,
)

User = settings.AUTH_USER_MODEL


class QuestionSubmission(models.Model):
    # ── Vəziyyət maşını (2026-09, sahibin qərarı: KAFEDRA TƏSDİQİ) ──────────
    # draft → submitted_to_chair → (chair_revision ↺ | rejected)
    #                            → chair_approved → center_review
    #                            → (accepted | rejected | center_revision ↺)
    # Köhnə `pending` dəyəri miqrasiya ilə `center_review`-a köçürülüb.
    STATUS_DRAFT = "draft"
    STATUS_SUBMITTED_TO_CHAIR = "submitted_to_chair"
    STATUS_CHAIR_REVISION = "chair_revision"
    STATUS_CHAIR_APPROVED = "chair_approved"
    STATUS_CENTER_REVIEW = "center_review"
    STATUS_CENTER_REVISION = "center_revision"
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = (
        (STATUS_DRAFT, pgettext_lazy("exams.model.question_submission.choice.status", "draft")),
        (
            STATUS_SUBMITTED_TO_CHAIR,
            pgettext_lazy("exams.model.question_submission.choice.status", "submitted_to_chair"),
        ),
        (STATUS_CHAIR_REVISION, pgettext_lazy("exams.model.question_submission.choice.status", "chair_revision")),
        (STATUS_CHAIR_APPROVED, pgettext_lazy("exams.model.question_submission.choice.status", "chair_approved")),
        (STATUS_CENTER_REVIEW, pgettext_lazy("exams.model.question_submission.choice.status", "center_review")),
        (STATUS_CENTER_REVISION, pgettext_lazy("exams.model.question_submission.choice.status", "center_revision")),
        (STATUS_ACCEPTED, pgettext_lazy("exams.model.question_submission.choice.status", "accepted")),
        (STATUS_REJECTED, pgettext_lazy("exams.model.question_submission.choice.status", "rejected")),
    )

    #: Kafedra müdirinin qərarını GÖZLƏYƏN vəziyyətlər.
    CHAIR_STAGE_STATUSES = (STATUS_SUBMITTED_TO_CHAIR,)
    #: İmtahan mərkəzinin qərar VERƏ BİLDİYİ vəziyyətlər (kafedra təsdiqindən sonra).
    CENTER_STAGE_STATUSES = (STATUS_CHAIR_APPROVED, STATUS_CENTER_REVIEW)
    #: Müəllimin redaktə edə bildiyi vəziyyətlər. Qəbul olunmuş və kafedra
    #: təsdiqindən keçmiş göndəriş DONDURULUR (mərkəzin gördüyü məzmun dəyişməsin).
    TEACHER_EDITABLE_STATUSES = (
        STATUS_DRAFT,
        STATUS_SUBMITTED_TO_CHAIR,
        STATUS_CHAIR_REVISION,
        STATUS_CENTER_REVISION,
        STATUS_REJECTED,
    )

    # Kafedra qərarının növü (`chair_decision` sahəsi).
    CHAIR_DECISION_APPROVED = "approved"
    CHAIR_DECISION_REVISION = "revision"
    CHAIR_DECISION_REJECTED = "rejected"
    CHAIR_DECISION_CHOICES = (
        (CHAIR_DECISION_APPROVED, pgettext_lazy("exams.model.question_submission.choice.chair_decision", "approved")),
        (CHAIR_DECISION_REVISION, pgettext_lazy("exams.model.question_submission.choice.chair_decision", "revision")),
        (CHAIR_DECISION_REJECTED, pgettext_lazy("exams.model.question_submission.choice.chair_decision", "rejected")),
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
    # Fənn kataloq bağlantısı (registrar.Subject) — müəllimin ÖZ fənlərindən
    # seçilir; `subject` (ad) görünüş/geriyə-uyğunluq üçün sinxron saxlanır.
    subject_ref = models.ForeignKey(
        "registrar.Subject",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="question_submissions",
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "subject_ref"),
    )
    # Suallar hansı imtahan növü üçün göndərilir (final/midterm/quiz) — qəbul
    # zamanı bank bu təyinatla yaradılır. Yeni göndərişlərdə view məcburi edir.
    exam_kind = models.CharField(
        max_length=20,
        choices=QUESTION_EXAM_KIND_CHOICES,
        blank=True,
        default="",
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "exam_kind"),
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
    # ÇOX qrup seçimi (2026-07): müəllim bir göndərişi bir neçə qrup üçün göndərə
    # bilər. ``student_group`` (tək FK) geriyə-uyğunluq üçün qalır (birinci qrup).
    student_groups = models.ManyToManyField(
        "exams.StudentGroup",
        blank=True,
        related_name="question_submissions_multi",
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "student_groups"),
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
    # Visual-first PDF/image import bundle-ının private, 128-bit token-i.
    # Qəbul zamanı canonical crop-lar banka köçürülür, sonra bundle silinir.
    import_token = models.CharField(max_length=32, blank=True, default="", editable=False)
    question_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_SUBMITTED_TO_CHAIR,
        db_index=True,
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "status"),
    )
    # Rədd → düzəliş → yenidən göndərmə dövrlərinin sayı.
    resubmission_count = models.PositiveIntegerField(default=0)

    # ── Kafedra mərhələsi ──────────────────────────────────────────────────
    # Göndərişin bağlı olduğu KAFEDRA: qrupun struktur əcdadından, o yoxdursa
    # müəllimin öz kafedra üzvlüyündən həll olunur (bax
    # ``apps/exams/services/question_chair_units.py``). Kafedra müdiri
    # növbəni məhz bu bölmə üzrə görür (fail-closed).
    chair_unit = models.ForeignKey(
        "organizations.OrgUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="question_submissions",
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "chair_unit"),
    )
    # Kafedra müdiri tapılmadığı halda göndəriş DEKANLIĞA yönləndirilir —
    # heç vaxt səssizcə birbaşa mərkəzə getmir.
    routed_to_dean = models.BooleanField(default=False)
    chair_reviewer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chair_reviewed_question_submissions",
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "chair_reviewer"),
    )
    chair_reviewed_at = models.DateTimeField(null=True, blank=True)
    chair_decision = models.CharField(
        max_length=20,
        choices=CHAIR_DECISION_CHOICES,
        blank=True,
        default="",
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "chair_decision"),
    )
    chair_note = models.TextField(
        blank=True,
        default="",
        verbose_name=pgettext_lazy("exams.model.question_submission.field", "chair_note"),
    )
    # Kafedra təsdiqi ilə göndərişin İMTAHAN MƏRKƏZİNƏ çatdığı an. Mərkəzin
    # görünürlük qapısı MƏHZ budur: boşdursa mərkəz göndərişi ÜMUMİYYƏTLƏ
    # görmür (mövcudluq sızması olmasın).
    reached_center_at = models.DateTimeField(null=True, blank=True)

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
            models.Index(fields=["chair_unit", "status", "-created_at"], name="qsub_chair_status_idx"),
        ]

    def __str__(self):
        return f"QuestionSubmission#{self.pk} · {self.title} · {self.status}"

    @property
    def is_at_chair(self):
        """Kafedra müdirinin qərarını gözləyir."""
        return self.status in self.CHAIR_STAGE_STATUSES

    @property
    def is_at_center(self):
        """İmtahan mərkəzi qərar verə bilər (kafedra təsdiqindən SONRA)."""
        return self.status in self.CENTER_STAGE_STATUSES

    #: Köhnə şablon/kod uyğunluğu — «mərkəz hələ qərar verməyib» mənasında.
    @property
    def is_pending(self):
        return self.is_at_center

    @property
    def has_reached_center(self):
        return self.reached_center_at is not None

    @property
    def can_be_edited_by_teacher(self):
        """Müəllim yalnız kafedraya/geri qaytarılmış göndərişi düzəldə bilər."""
        return self.status in self.TEACHER_EDITABLE_STATUSES


__all__ = ["QuestionSubmission"]
