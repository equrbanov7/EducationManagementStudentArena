"""
Final imtahan mərkəzi domain modelləri.

Mərkəzləşdirilmiş universitet final imtahanları üçün:

* ``ExamRoom``          — fiziki imtahan zalı (org-scoped resurs).
* ``ExamRoomSession``   — bir imtahanın bir zalda keçirilən oturumu
                          (nəzarətçi, rəsmi start/son, state machine).
* ``FinalExamTicket``   — tələbənin oturuma təyinatı + şəxsi PIN +
                          həyat dövrü (waiting → active → completed).

Mövcud sistemlə inteqrasiya: sual/attempt/nəticə axını üçün ``Exam`` və
``ExamAttempt`` modelləri OLDUĞU KİMİ istifadə olunur — burada yalnız
zal/oturum/PIN qatı əlavə edilir. Supervision (anti-cheat) qatı da mövcud
``ExamSupervisionConfig``/``SupervisionIncident`` üzərində qalır.
"""

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import pgettext_lazy

from apps.exams.constants import EXAM_LANGUAGE_CHOICES

User = get_user_model()

# ---------------------------------------------------------------------------
# State machine sabitləri — DB-də saxlanan yeganə mənbə.
# Keçidlər backend-də ``transition_*`` helper-ləri ilə şərti UPDATE kimi
# tətbiq olunur (yarış şəraitində idempotent).
# ---------------------------------------------------------------------------

ROOM_SESSION_STATE_PREPARED = "prepared"
ROOM_SESSION_STATE_ENTRY_OPEN = "entry_open"
ROOM_SESSION_STATE_ACTIVE = "active"
ROOM_SESSION_STATE_ENDED = "ended"
ROOM_SESSION_STATE_CANCELLED = "cancelled"

ROOM_SESSION_STATES = (
    ROOM_SESSION_STATE_PREPARED,
    ROOM_SESSION_STATE_ENTRY_OPEN,
    ROOM_SESSION_STATE_ACTIVE,
    ROOM_SESSION_STATE_ENDED,
    ROOM_SESSION_STATE_CANCELLED,
)

# İcazəli keçidlər: mənbə → mümkün hədəflər.
ROOM_SESSION_TRANSITIONS = {
    ROOM_SESSION_STATE_PREPARED: {ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_CANCELLED},
    ROOM_SESSION_STATE_ENTRY_OPEN: {ROOM_SESSION_STATE_ACTIVE, ROOM_SESSION_STATE_CANCELLED},
    ROOM_SESSION_STATE_ACTIVE: {ROOM_SESSION_STATE_ENDED},
    ROOM_SESSION_STATE_ENDED: set(),
    ROOM_SESSION_STATE_CANCELLED: set(),
}

TICKET_STATUS_ASSIGNED = "assigned"
TICKET_STATUS_WAITING = "waiting"
TICKET_STATUS_READY = "ready"
TICKET_STATUS_ACTIVE = "active"
TICKET_STATUS_COMPLETED = "completed"
TICKET_STATUS_REMOVED = "removed"
TICKET_STATUS_ABSENT = "absent"

TICKET_STATUSES = (
    TICKET_STATUS_ASSIGNED,
    TICKET_STATUS_WAITING,
    TICKET_STATUS_READY,
    TICKET_STATUS_ACTIVE,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_REMOVED,
    TICKET_STATUS_ABSENT,
)

TICKET_TRANSITIONS = {
    TICKET_STATUS_ASSIGNED: {TICKET_STATUS_WAITING, TICKET_STATUS_REMOVED, TICKET_STATUS_ABSENT},
    TICKET_STATUS_WAITING: {
        TICKET_STATUS_READY,
        TICKET_STATUS_ASSIGNED,  # tələbə gözləmə otağından imtina etdi (attempt yanmır)
        TICKET_STATUS_ACTIVE,
        TICKET_STATUS_REMOVED,
        TICKET_STATUS_ABSENT,
    },
    TICKET_STATUS_READY: {
        TICKET_STATUS_WAITING,
        TICKET_STATUS_ACTIVE,
        TICKET_STATUS_REMOVED,
        TICKET_STATUS_ABSENT,
    },
    TICKET_STATUS_ACTIVE: {TICKET_STATUS_COMPLETED, TICKET_STATUS_REMOVED},
    TICKET_STATUS_COMPLETED: set(),
    # Yenidən buraxılma yalnız imtahan mərkəzi qərarı ilə (re-admit).
    TICKET_STATUS_REMOVED: {TICKET_STATUS_ASSIGNED},
    TICKET_STATUS_ABSENT: set(),
}

# Gözləmə otağında "canlı" sayılan ticket statusları (monitor sayğacları üçün).
TICKET_LIVE_STATUSES = (TICKET_STATUS_WAITING, TICKET_STATUS_READY, TICKET_STATUS_ACTIVE)


class ExamRoom(models.Model):
    """Fiziki imtahan zalı — imtahan mərkəzinin idarə etdiyi org-scoped resurs."""

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="exam_rooms",
        verbose_name=pgettext_lazy("exams.model.exam_room.field", "organization"),
    )
    name = models.CharField(
        max_length=120,
        verbose_name=pgettext_lazy("exams.model.exam_room.field", "name"),
    )
    code = models.CharField(
        max_length=32,
        verbose_name=pgettext_lazy("exams.model.exam_room.field", "code"),
        help_text=pgettext_lazy("exams.model.exam_room.help", "code"),
    )
    building = models.CharField(
        max_length=120,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.exam_room.field", "building"),
    )
    floor = models.CharField(
        max_length=32,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.exam_room.field", "floor"),
    )
    capacity = models.PositiveIntegerField(
        default=0,
        verbose_name=pgettext_lazy("exams.model.exam_room.field", "capacity"),
        help_text=pgettext_lazy("exams.model.exam_room.help", "capacity"),
    )
    computer_count = models.PositiveIntegerField(
        default=0,
        verbose_name=pgettext_lazy("exams.model.exam_room.field", "computer_count"),
    )
    notes = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.exam_room.field", "notes"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=pgettext_lazy("exams.model.exam_room.field", "is_active"),
    )
    # Zal səviyyəli nəzarətçilər: zala təyin olunan müəllim/mərkəz işçiləri
    # HƏMİN zaldakı BÜTÜN oturumları monitor edib idarə edə bilir (icazə
    # ``can_supervise_session`` içində zal→nəzarətçilər üzərindən yoxlanır).
    # Nəzarətçi artıq ayrı-ayrı oturumlara yox, zala təyin olunur.
    invigilators = models.ManyToManyField(
        User,
        blank=True,
        related_name="invigilated_rooms",
        verbose_name=pgettext_lazy("exams.model.exam_room.field", "invigilators"),
        help_text=pgettext_lazy("exams.model.exam_room.help", "invigilators"),
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_exam_rooms",
        verbose_name=pgettext_lazy("exams.model.exam_room.field", "created_by"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = pgettext_lazy("exams.model.exam_room.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.exam_room.meta", "plural")
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "code"], name="uniq_exam_room_code_per_org"),
        ]
        indexes = [
            models.Index(fields=["organization", "is_active", "name"], name="examroom_org_active_name_idx"),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class ExamRoomComputer(models.Model):
    """
    Zala təyin olunmuş fiziki kompüter — MAC + sabit IP ilə qeyd.

    Təhlükəsizlik qeydi (bax ``exam_center_gate.py``): MAC ünvanı HTTP sorğusu
    ilə serverə çatmır, ona görə giriş məhdudiyyəti server tərəfində **IP**
    (``ip_address``) üzərindən tətbiq olunur; MAC yalnız etibarlı
    identifikasiya/inventar sahəsidir. ``seat_number`` zal monitorunun kompüter
    xəritəsindəki yeri (ticket ``seat_number`` ilə uyğunlaşır) təyin edir.
    """

    # Denormalizasiya: RLS tenant izolyasiyası birbaşa NOT NULL ``organization_id``
    # tələb edir (bax organizations 0015). Zalın təşkilatı yaradılışda kopyalanır.
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="exam_room_computers",
        verbose_name=pgettext_lazy("exams.model.room_computer.field", "organization"),
    )
    room = models.ForeignKey(
        "exams.ExamRoom",
        on_delete=models.CASCADE,
        related_name="computers",
        verbose_name=pgettext_lazy("exams.model.room_computer.field", "room"),
    )
    label = models.CharField(
        max_length=64,
        verbose_name=pgettext_lazy("exams.model.room_computer.field", "label"),
        help_text=pgettext_lazy("exams.model.room_computer.help", "label"),
    )
    seat_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.room_computer.field", "seat_number"),
        help_text=pgettext_lazy("exams.model.room_computer.help", "seat_number"),
    )
    mac_address = models.CharField(
        max_length=17,
        verbose_name=pgettext_lazy("exams.model.room_computer.field", "mac_address"),
        help_text=pgettext_lazy("exams.model.room_computer.help", "mac_address"),
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.room_computer.field", "ip_address"),
        help_text=pgettext_lazy("exams.model.room_computer.help", "ip_address"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=pgettext_lazy("exams.model.room_computer.field", "is_active"),
    )
    notes = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.room_computer.field", "notes"),
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registered_room_computers",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = pgettext_lazy("exams.model.room_computer.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.room_computer.meta", "plural")
        ordering = ["seat_number", "label", "id"]
        constraints = [
            models.UniqueConstraint(fields=["room", "mac_address"], name="uniq_room_computer_mac"),
            models.UniqueConstraint(fields=["room", "label"], name="uniq_room_computer_label"),
            models.UniqueConstraint(
                fields=["room", "seat_number"],
                condition=models.Q(seat_number__isnull=False),
                name="uniq_room_computer_seat",
            ),
        ]
        indexes = [
            models.Index(fields=["room", "is_active"], name="roomcomp_room_active_idx"),
            # Final-exam entry gate: org_computer_access_allowed() by (org, MAC).
            models.Index(fields=["organization", "mac_address"], name="roomcomp_org_mac_idx"),
            models.Index(fields=["organization", "is_active"], name="roomcomp_org_active_idx"),
        ]

    def __str__(self):
        return f"{self.label} @ {self.room.name} [{self.mac_address}]"

    @staticmethod
    def normalize_mac(raw: str) -> str:
        """MAC-ı kanonik böyük-hərf iki-nöqtəli formata gətirir (``AA:BB:...``).

        Ayırıcıları (``:``, ``-``, ``.``, boşluq) təmizləyir, 12 hex rəqəmini
        cütləyir. Yanlış uzunluq/format olduqda ``ValueError`` atır — validasiya
        forma/servis qatında tutulur.
        """
        import re

        cleaned = re.sub(r"[^0-9A-Fa-f]", "", raw or "")
        if len(cleaned) != 12:
            raise ValueError("invalid_mac_length")
        cleaned = cleaned.upper()
        return ":".join(cleaned[i : i + 2] for i in range(0, 12, 2))


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


__all__ = [
    "ExamRoom",
    "ExamRoomComputer",
    "ExamRoomSession",
    "FinalExamTicket",
    "ROOM_SESSION_STATES",
    "ROOM_SESSION_STATE_PREPARED",
    "ROOM_SESSION_STATE_ENTRY_OPEN",
    "ROOM_SESSION_STATE_ACTIVE",
    "ROOM_SESSION_STATE_ENDED",
    "ROOM_SESSION_STATE_CANCELLED",
    "ROOM_SESSION_TRANSITIONS",
    "TICKET_STATUSES",
    "TICKET_STATUS_ASSIGNED",
    "TICKET_STATUS_WAITING",
    "TICKET_STATUS_READY",
    "TICKET_STATUS_ACTIVE",
    "TICKET_STATUS_COMPLETED",
    "TICKET_STATUS_REMOVED",
    "TICKET_STATUS_ABSENT",
    "TICKET_TRANSITIONS",
    "TICKET_LIVE_STATUSES",
]
