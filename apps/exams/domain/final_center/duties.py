"""Final imtahan mərkəzi — ZAL NƏZARƏTÇİSİ NÖVBƏSİ (``InvigilatorDuty``).

2026-10-13 (gecə), sahib: «nəzarətçinin təyin olunması, təyin olunandan sonra onun
da müəyyən accessləri olması kabinetində, amma imtahan sessiyası ya da gün bitəndə
onun itməsi». Əvvəl nəzarətçi zala ``ExamRoom.invigilators`` M2M-i ilə DAİMİ təyin
olunurdu — imtahan bitəndən aylar sonra da zal monitoruna, tələbə şəkillərinə və
canlı cəhdlərə çıxışı qalırdı (ən az səlahiyyət prinsipinin pozulması).

Növbə = (zal, istifadəçi, planlaşdırılmış başlanğıc/son). Giriş hüququ SORĞU ANINDA
hesablanır (cron lazım deyil), bax ``services/final_center/duties.py``:

* başlanğıcdan ``DUTY_LEAD_MINUTES`` əvvəl açılır (zalı hazırlamaq üçün);
* başlanğıc gününün sonunda (Asia/Baku, 23:59:59) HƏMİŞƏ bağlanır;
* planlaşdırılmış sondan ``DUTY_GRACE_MINUTES`` sonra, zalda canlı oturum qalmayıbsa,
  dərhal bağlanır («sessiya bitəndə itsin»); imtahan uzanıbsa (canlı oturum var)
  gün sonuna qədər açıq qalır — nəzarətçi gedən imtahanın ortasında atılmır;
* ``revoked_at`` dolu → dərhal bağlanır (rəhbər ləğv edib).

Sətir silinmir (audit izi) — ləğv ``revoked_at`` ilə qeyd olunur.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy


class InvigilatorDuty(models.Model):
    # RLS tenant izolyasiyası birbaşa NOT NULL ``organization_id`` tələb edir
    # (organizations 0015/0016 forması) — zalın təşkilatı yaradılışda kopyalanır.
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name=pgettext_lazy("exams.model.invigilator_duty.field", "organization"),
    )
    room = models.ForeignKey(
        "exams.ExamRoom",
        on_delete=models.CASCADE,
        related_name="duties",
        verbose_name=pgettext_lazy("exams.model.invigilator_duty.field", "room"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="invigilator_duties",
        verbose_name=pgettext_lazy("exams.model.invigilator_duty.field", "user"),
    )
    starts_at = models.DateTimeField(
        verbose_name=pgettext_lazy("exams.model.invigilator_duty.field", "starts_at"),
    )
    ends_at = models.DateTimeField(
        verbose_name=pgettext_lazy("exams.model.invigilator_duty.field", "ends_at"),
    )
    note = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.invigilator_duty.field", "note"),
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = pgettext_lazy("exams.model.invigilator_duty.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.invigilator_duty.meta", "plural")
        ordering = ["starts_at", "id"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(ends_at__gt=models.F("starts_at")),
                name="invigilator_duty_end_after_start",
            ),
        ]
        indexes = [
            # Hər sorğuda «bu istifadəçinin indi aktiv növbəsi varmı» — (user, starts_at).
            models.Index(fields=["user", "starts_at"], name="invduty_user_start_idx"),
            models.Index(fields=["room", "starts_at"], name="invduty_room_start_idx"),
        ]

    def __str__(self):
        return f"InvigilatorDuty(room={self.room_id}, user={self.user_id}, {self.starts_at:%Y-%m-%d %H:%M})"


__all__ = ["InvigilatorDuty"]
