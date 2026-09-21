"""Final imtahan mərkəzi — ``ExamRoom`` və ``ExamRoomComputer`` modelləri.

``final_center.py``-dan paketə bölünüb (modul-ölçü qapısı, 2026-09-21). Modellər
``apps.exams`` app-ına aiddir (app label modul yolundan çıxır); migrasiyalar və
``apps.exams.models`` import yolu dəyişmir.
"""

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import pgettext_lazy

User = get_user_model()


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
