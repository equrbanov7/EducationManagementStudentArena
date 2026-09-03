"""Sual göndərişinin ƏLAVƏ-ONLY hadisə lentı (kafedra → imtahan mərkəzi izi).

Niyə ayrıca cədvəl
------------------
``QuestionSubmission`` yalnız CARİ vəziyyəti saxlayır: kim, nə vaxt, hansı
səbəblə hansı addımı atdı — sual GÖNDƏRİŞİN ÖZÜNDƏ görünmür (köhnə qərar
sahələri yenidən göndərişdə təmizlənirdi).  Sahibin tələbi «bütün yol izlənə
bilsin» olduğu üçün hər keçid burada AYRICA sətir kimi qeyd olunur və UI-də
zaman xətti (timeline) kimi göstərilir.

Müqavilə
--------
* Sətirlər YALNIZ əlavə olunur — redaktə/silmə YOXDUR (servis qatı yalnız
  ``record_event`` ilə yazır; ``delete`` yalnız göndərişin özü silinəndə
  kaskadla baş verir).
* ``organization`` BİRBAŞA saxlanılır ki, RLS siyasəti sadə (``organization_id``)
  qalsın — alt-sorğu ilə tenant həlli lazım gəlməsin.
* ``actor`` ``SET_NULL``-dur: hesab sonradan silinsə belə iz İTMİR
  (``actor_label`` anlıq görünən adı dondurur).
"""

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

User = settings.AUTH_USER_MODEL


class QuestionSubmissionEvent(models.Model):
    ACTION_SUBMITTED_TO_CHAIR = "submitted_to_chair"
    ACTION_RESUBMITTED_TO_CHAIR = "resubmitted_to_chair"
    ACTION_CHAIR_APPROVED = "chair_approved"
    ACTION_CHAIR_REVISION = "chair_revision"
    ACTION_CHAIR_REJECTED = "chair_rejected"
    ACTION_CENTER_OPENED = "center_opened"
    ACTION_CENTER_ACCEPTED = "center_accepted"
    ACTION_CENTER_REVISION = "center_revision"
    ACTION_CENTER_REJECTED = "center_rejected"
    ACTION_CHOICES = (
        (ACTION_SUBMITTED_TO_CHAIR, pgettext_lazy("exams.model.question_submission_event.choice", "submitted")),
        (ACTION_RESUBMITTED_TO_CHAIR, pgettext_lazy("exams.model.question_submission_event.choice", "resubmitted")),
        (ACTION_CHAIR_APPROVED, pgettext_lazy("exams.model.question_submission_event.choice", "chair_approved")),
        (ACTION_CHAIR_REVISION, pgettext_lazy("exams.model.question_submission_event.choice", "chair_revision")),
        (ACTION_CHAIR_REJECTED, pgettext_lazy("exams.model.question_submission_event.choice", "chair_rejected")),
        (ACTION_CENTER_OPENED, pgettext_lazy("exams.model.question_submission_event.choice", "center_opened")),
        (ACTION_CENTER_ACCEPTED, pgettext_lazy("exams.model.question_submission_event.choice", "center_accepted")),
        (ACTION_CENTER_REVISION, pgettext_lazy("exams.model.question_submission_event.choice", "center_revision")),
        (ACTION_CENTER_REJECTED, pgettext_lazy("exams.model.question_submission_event.choice", "center_rejected")),
    )

    submission = models.ForeignKey(
        "exams.QuestionSubmission",
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name=pgettext_lazy("exams.model.question_submission_event.field", "submission"),
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="question_submission_events",
        verbose_name=pgettext_lazy("exams.model.question_submission_event.field", "organization"),
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="question_submission_events",
        verbose_name=pgettext_lazy("exams.model.question_submission_event.field", "actor"),
    )
    # Hesab silinsə belə lentdə görünən ad qalsın.
    actor_label = models.CharField(max_length=200, blank=True, default="")
    # Aktorun HANSI SİFƏTLƏ hərəkət etdiyi (teacher / chair_head / dean /
    # exam_center / …) — audit üçün rol adı DONDURULUR.
    actor_role = models.CharField(max_length=64, blank=True, default="")
    action = models.CharField(max_length=32, choices=ACTION_CHOICES, db_index=True)
    from_status = models.CharField(max_length=20, blank=True, default="")
    to_status = models.CharField(max_length=20, blank=True, default="")
    # Düzəliş/rədd üçün MƏCBURİ (servis qatı ≥20 simvol tələb edir).
    reason = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = pgettext_lazy("exams.model.question_submission_event.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.question_submission_event.meta", "plural")
        ordering = ["id"]
        indexes = [
            models.Index(fields=["submission", "id"], name="qsubev_submission_idx"),
            models.Index(fields=["organization", "-created_at"], name="qsubev_org_created_idx"),
        ]

    def __str__(self):
        return f"QuestionSubmissionEvent#{self.pk} · {self.submission_id} · {self.action}"


__all__ = ["QuestionSubmissionEvent"]
