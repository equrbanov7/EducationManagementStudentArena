"""Final imtahan mərkəzi — ``FinalExamTicket`` (təyinat + PIN + həyat dövrü) modeli.

``final_center.py``-dan paketə bölünüb (modul-ölçü qapısı, 2026-09-21).
"""

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import pgettext_lazy

from apps.exams.constants import EXAM_LANGUAGE_CHOICES

from .states import (
    TICKET_STATUS_ABSENT,
    TICKET_STATUS_ACTIVE,
    TICKET_STATUS_ASSIGNED,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_READY,
    TICKET_STATUS_REMOVED,
    TICKET_STATUS_WAITING,
)

User = get_user_model()


class FinalExamTicket(models.Model):
    """
    Tələbənin final oturumuna təyinatı: şəxsi PIN + yer + həyat dövrü.

    PIN saxlanması:
    * ``pin_hash``   — doğrulama üçün salted hash (``check_password``).
    * ``pin_cipher`` — icazəli göstərmə üçün Fernet ilə şifrələnmiş nüsxə;
      oturum bitdikdə/PIN ləğv olunduqda TƏMİZLƏNİR. Xam PIN heç vaxt
      log/audit/URL-lərə düşmür.
    """

    STATUS_CHOICES = (
        (TICKET_STATUS_ASSIGNED, pgettext_lazy("exams.model.final_ticket.choice.status", "assigned")),
        (TICKET_STATUS_WAITING, pgettext_lazy("exams.model.final_ticket.choice.status", "waiting")),
        (TICKET_STATUS_READY, pgettext_lazy("exams.model.final_ticket.choice.status", "ready")),
        (TICKET_STATUS_ACTIVE, pgettext_lazy("exams.model.final_ticket.choice.status", "active")),
        (TICKET_STATUS_COMPLETED, pgettext_lazy("exams.model.final_ticket.choice.status", "completed")),
        (TICKET_STATUS_REMOVED, pgettext_lazy("exams.model.final_ticket.choice.status", "removed")),
        (TICKET_STATUS_ABSENT, pgettext_lazy("exams.model.final_ticket.choice.status", "absent")),
    )

    REMOVAL_ACTION_CHOICES = (
        ("removed", pgettext_lazy("exams.model.final_ticket.choice.removal", "removed")),
        ("suspended", pgettext_lazy("exams.model.final_ticket.choice.removal", "suspended")),
        ("technical", pgettext_lazy("exams.model.final_ticket.choice.removal", "technical")),
    )

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="final_exam_tickets",
        verbose_name=pgettext_lazy("exams.model.final_ticket.field", "organization"),
    )
    # Tələbənin təyin olunduğu İMTAHAN — biletin ƏSAS bağıdır (zal yox).
    # Bilet təyinat anında yaradılır: "bu tələbə bu finala PIN-lə buraxılır".
    exam = models.ForeignKey(
        "exams.Exam",
        on_delete=models.CASCADE,
        related_name="final_tickets",
        verbose_name=pgettext_lazy("exams.model.final_ticket.field", "exam"),
    )
    # Zal oturumu GİRİŞ anında bağlanır: tələbə qeydli kompüterdən (IP → zal)
    # girəndə həmin zalın açıq oturumuna qoşulur. Təyinat anında NULL olur.
    # Oturum silinsə bilet qalır (imtahan-scoped, oturumdan asılı deyil).
    session = models.ForeignKey(
        "exams.ExamRoomSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tickets",
        verbose_name=pgettext_lazy("exams.model.final_ticket.field", "session"),
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="final_exam_tickets",
        verbose_name=pgettext_lazy("exams.model.final_ticket.field", "student"),
    )
    attempt = models.ForeignKey(
        "exams.ExamAttempt",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="final_tickets",
        verbose_name=pgettext_lazy("exams.model.final_ticket.field", "attempt"),
    )
    seat_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.final_ticket.field", "seat_number"),
    )
    language = models.CharField(
        max_length=10,
        choices=EXAM_LANGUAGE_CHOICES,
        blank=True,
        default="",
        verbose_name=pgettext_lazy("exams.model.final_ticket.field", "language"),
        help_text=pgettext_lazy("exams.model.final_ticket.help", "language"),
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=TICKET_STATUS_ASSIGNED,
        verbose_name=pgettext_lazy("exams.model.final_ticket.field", "status"),
    )

    # ── PIN sahələri ────────────────────────────────────────────────────────
    pin_hash = models.CharField(max_length=192, blank=True, default="")
    pin_cipher = models.TextField(blank=True, default="")
    pin_issued_at = models.DateTimeField(null=True, blank=True)
    pin_expires_at = models.DateTimeField(null=True, blank=True)
    pin_revoked_at = models.DateTimeField(null=True, blank=True)
    pin_failed_attempts = models.PositiveIntegerField(default=0)
    pin_locked_until = models.DateTimeField(null=True, blank=True)
    pin_generated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_final_pins",
    )

    # Son xatırlatma bildirişinin göndərildiyi eşik (gün). 0 = heç göndərilməyib.
    # Dublikat xatırlatmaların qarşısını alır (bax: notify_upcoming_final_exams).
    reminder_stage = models.PositiveSmallIntegerField(default=0)

    # ── Həyat dövrü timestamp-ləri (tarixi hesabat üçün) ───────────────────
    entry_validated_at = models.DateTimeField(null=True, blank=True)
    rules_accepted_at = models.DateTimeField(null=True, blank=True)
    waiting_since = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    removed_at = models.DateTimeField(null=True, blank=True)
    removed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="removed_final_tickets",
    )
    removal_action = models.CharField(
        max_length=20,
        choices=REMOVAL_ACTION_CHOICES,
        blank=True,
        default="",
    )
    removal_reason = models.TextField(blank=True, default="")
    reconnect_count = models.PositiveIntegerField(default=0)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = pgettext_lazy("exams.model.final_ticket.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.final_ticket.meta", "plural")
        ordering = ["seat_number", "id"]
        constraints = [
            # ƏSAS: bir tələbəyə bir imtahana yalnız bir bilet (təyinatın vahidi).
            models.UniqueConstraint(fields=["exam", "student"], name="uniq_ticket_per_exam_student"),
            # Bir zal oturumunda bir seat yalnız bir tələbədə (giriş anında set olur);
            # yalnız oturum və seat təyin olunduqda tətbiq edilir.
            models.UniqueConstraint(
                fields=["session", "seat_number"],
                condition=models.Q(seat_number__isnull=False, session__isnull=False),
                name="uniq_seat_per_session",
            ),
        ]
        indexes = [
            models.Index(fields=["session", "status"], name="finticket_session_status_idx"),
            models.Index(fields=["student", "status"], name="finticket_student_status_idx"),
            models.Index(fields=["organization", "-created_at"], name="finticket_org_created_idx"),
        ]

    def __str__(self):
        return f"{self.student.username} → {self.exam.title} [{self.status}]"

    @property
    def has_valid_pin(self) -> bool:
        from django.utils import timezone as _tz

        if not self.pin_hash or self.pin_revoked_at:
            return False
        if self.pin_expires_at and _tz.now() >= self.pin_expires_at:
            return False
        return True

    @property
    def is_pin_locked(self) -> bool:
        from django.utils import timezone as _tz

        return bool(self.pin_locked_until and _tz.now() < self.pin_locked_until)
