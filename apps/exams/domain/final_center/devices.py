"""Final imtahan mərkəzi — davam edən final cəhdinin CİHAZ bağlantısı (təhlükəsizlik dizaynı 2026-10-08).

Audit 2026-10-07 «Dizayn riskləri»: qeydli zal kompüteri olmayan təşkilatda final cəhdi
istənilən cihazdan davam etdirilə bilirdi. Cəhd ilk açıldığı brauzerə bağlanır: brauzerdə
imzalı, HttpOnly cihaz cookie-si (təsadüfi id) saxlanılır, burada isə yalnız
``sha256(attempt_id:cihaz_id)`` — xam id bazaya yazılmır. Başqa cihazdan davam yalnız
nəzarətçi/imtahan mərkəzinin «cihaz dəyişikliyi» təsdiqi ilə (qısa pəncərə, birdəfəlik).

Ayrıca cədvəldir (``ExamAttempt``-ə sütun deyil): sətir yalnız final cəhdlərində yaranır,
qaynar autosave yolunun SELECT-i dəyişmir. Tenant izolyasiyası: ``organization_id`` +
RLS siyasəti (miqrasiya 0073); servis oxuları açıq ``attempt_id`` süzgəcli dar bypass-dadır.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import pgettext_lazy


class FinalAttemptDevice(models.Model):
    attempt = models.OneToOneField(
        "exams.ExamAttempt",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="device_binding",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="+",
    )
    #: ``sha256(f"{attempt_id}:{device_id}")`` — cihaz id-si yalnız brauzerdədir.
    token_hash = models.CharField(max_length=64)
    bound_at = models.DateTimeField(default=timezone.now)
    #: Nəzarətçinin «cihaz dəyişikliyi» təsdiqi — pəncərə daxilində növbəti YENİ cihaz
    #: cəhdi özünə köçürür; köçürmə təsdiqi sıfırlayır (birdəfəlik).
    change_approved_at = models.DateTimeField(null=True, blank=True)
    change_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    rebind_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = pgettext_lazy("exams.model.final_device.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.final_device.meta", "plural")

    def __str__(self):
        return f"FinalAttemptDevice(attempt={self.attempt_id})"


__all__ = ["FinalAttemptDevice"]
