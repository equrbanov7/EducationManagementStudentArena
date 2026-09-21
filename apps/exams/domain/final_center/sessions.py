"""Final imtahan mərkəzi — ``ExamRoomSession`` (zal oturumu) modeli.

``final_center.py``-dan paketə bölünüb (modul-ölçü qapısı, 2026-09-21).
"""

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import pgettext_lazy

from .states import (
    ROOM_SESSION_STATE_ACTIVE,
    ROOM_SESSION_STATE_CANCELLED,
    ROOM_SESSION_STATE_ENDED,
    ROOM_SESSION_STATE_ENTRY_OPEN,
    ROOM_SESSION_STATE_PREPARED,
)

User = get_user_model()


class ExamRoomSession(models.Model):
    """
    Bir ZALDA keçirilən oturum (sitting) — imtahandan ASILI DEYİL.

    Universitet qaydası (2026-07): imtahan zaldan asılı deyil — istənilən imtahan
    istənilən zalda verilə bilər. Ona görə oturum artıq konkret imtahana yox,
    yalnız **zala** bağlıdır: nəzarətçi ZALI (oradakı qeydli kompüterləri)
    açıb-başladır, otaqda fiziki oturan hər tələbə (kim hansı imtahana təyin
    olunubsa) öz imtahanına başlayır. Tələbənin hansı imtahana təyin olunması
    ``FinalExamTicket.exam``-da saxlanır; tələbə giriş anında (kompüter IP-si →
    zal) həmin oturuma qoşulur (``ticket.session`` set olunur).

    Rəsmi start/son vaxtının YEGANƏ mənbəyi backend-dir: ``started_at`` /
    ``ended_at`` yalnız server timestamp-i ilə, şərti (idempotent) UPDATE
    vasitəsilə yazılır.
    """

    STATE_CHOICES = (
        (ROOM_SESSION_STATE_PREPARED, pgettext_lazy("exams.model.room_session.choice.state", "prepared")),
        (ROOM_SESSION_STATE_ENTRY_OPEN, pgettext_lazy("exams.model.room_session.choice.state", "entry_open")),
        (ROOM_SESSION_STATE_ACTIVE, pgettext_lazy("exams.model.room_session.choice.state", "active")),
        (ROOM_SESSION_STATE_ENDED, pgettext_lazy("exams.model.room_session.choice.state", "ended")),
        (ROOM_SESSION_STATE_CANCELLED, pgettext_lazy("exams.model.room_session.choice.state", "cancelled")),
    )

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="exam_room_sessions",
        verbose_name=pgettext_lazy("exams.model.room_session.field", "organization"),
    )
    # Zal tarixçəsi hesabatlar üçün qorunmalıdır — oturumu olan zal silinmir.
    room = models.ForeignKey(
        "exams.ExamRoom",
        on_delete=models.PROTECT,
        related_name="sessions",
        verbose_name=pgettext_lazy("exams.model.room_session.field", "room"),
    )
    invigilator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invigilated_room_sessions",
        verbose_name=pgettext_lazy("exams.model.room_session.field", "invigilator"),
    )
    staff = models.ManyToManyField(
        User,
        blank=True,
        related_name="staffed_room_sessions",
        verbose_name=pgettext_lazy("exams.model.room_session.field", "staff"),
        help_text=pgettext_lazy("exams.model.room_session.help", "staff"),
    )
    scheduled_start = models.DateTimeField(
        verbose_name=pgettext_lazy("exams.model.room_session.field", "scheduled_start"),
    )
    scheduled_end = models.DateTimeField(
        verbose_name=pgettext_lazy("exams.model.room_session.field", "scheduled_end"),
    )
    state = models.CharField(
        max_length=20,
        choices=STATE_CHOICES,
        default=ROOM_SESSION_STATE_PREPARED,
        verbose_name=pgettext_lazy("exams.model.room_session.field", "state"),
    )
    entry_opened_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.room_session.field", "started_at"),
    )
    started_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="started_room_sessions",
        verbose_name=pgettext_lazy("exams.model.room_session.field", "started_by"),
    )
    # Start anında qoşulu tələbə sayı — tarixi hesabat üçün snapshot.
    start_connected_count = models.PositiveIntegerField(default=0)
    ended_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.room_session.field", "ended_at"),
    )
    ended_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ended_room_sessions",
        verbose_name=pgettext_lazy("exams.model.room_session.field", "ended_by"),
    )
    notes = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.room_session.field", "notes"),
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_room_sessions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = pgettext_lazy("exams.model.room_session.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.room_session.meta", "plural")
        ordering = ["-scheduled_start", "-id"]
        constraints = [
            # QEYD: bir zalda EYNİ ANDA çoxlu aktiv oturum ola bilər — imtahan
            # zalı bir neçə fərqli fənn/imtahanı paralel keçirə bilir (nəzarətçi
            # zaldakı hamısını birlikdə idarə edir). Ona görə "bir zal = bir
            # aktiv oturum" məhdudiyyəti YOXDUR. Tələbənin ikiqat təyinatı
            # ``assign_students`` konflikt yoxlaması ilə əngəllənir.
            models.CheckConstraint(
                check=models.Q(scheduled_end__gt=models.F("scheduled_start")),
                name="room_session_end_after_start",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "state", "-scheduled_start"], name="roomsess_org_state_sched_idx"),
            models.Index(fields=["room", "-scheduled_start"], name="roomsess_room_sched_idx"),
            models.Index(fields=["invigilator", "state"], name="roomsess_invig_state_idx"),
        ]

    def __str__(self):
        return f"{self.room.name} oturumu [{self.state}]"

    @property
    def is_live(self) -> bool:
        return self.state in (ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE)

    @property
    def is_finished(self) -> bool:
        return self.state in (ROOM_SESSION_STATE_ENDED, ROOM_SESSION_STATE_CANCELLED)
