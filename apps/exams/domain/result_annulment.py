"""İmtahan nəticəsinin ləğvi qeydi (sahib 2026-11-16 / 2026-11-17).

Sahib 2026-11-17: «tələbə “Bitir” vurub çıxıbsa, sonradan köçürmə aşkarlanarsa nəticəsi ləğv edilsin — səbəb
siyahıdan, izahat, tarix, istəyə görə sənəd; təsdiq pəncərəsi ilə. Səhv də ola bilər — bərpa da olsun».

Hər ləğv əməli BİR sətirdir: kim, nə vaxt, səbəb, izahat, hadisə tarixi, sənəd, cəhdin ləğvdən əvvəlki
``supervision_status``-u. Bərpa sətri silmir — ``restored_at`` / ``restored_by`` / ``restore_note`` doldurulur
(tarixçə tam qalır, təkrar ləğv yeni sətirdir). Aktiv ləğv = ``restored_at IS NULL`` (cəhd başına ən çox biri).
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import pgettext_lazy

from apps.exams.validators import validate_file_size

ANNUL_DOCUMENT_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx")


def annul_document_path(instance, filename):
    """Sənəd yolu — tələbənin adı/FİN-i fayl adına düşmür (yalnız cəhd id-si + uzantı)."""
    import os
    import uuid

    ext = os.path.splitext(filename or "")[1].lower()[:8]
    return f"exam_annulments/{instance.attempt_id}/{uuid.uuid4().hex}{ext}"


class ExamResultAnnulment(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="+", db_index=False
    )
    attempt = models.ForeignKey("exams.ExamAttempt", on_delete=models.CASCADE, related_name="result_annulments")
    reason_key = models.CharField(max_length=20)
    note = models.TextField(max_length=1000)
    incident_date = models.DateField(null=True, blank=True)
    document = models.FileField(
        upload_to=annul_document_path, max_length=255, blank=True, validators=[validate_file_size]
    )
    previous_supervision_status = models.CharField(max_length=20, blank=True, default="")
    annulled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    annulled_at = models.DateTimeField(auto_now_add=True)
    restored_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    restored_at = models.DateTimeField(null=True, blank=True)
    restore_note = models.TextField(max_length=1000, blank=True, default="")

    class Meta:
        verbose_name = pgettext_lazy("exams.model.result_annulment", "İmtahan nəticəsinin ləğvi")
        verbose_name_plural = pgettext_lazy("exams.model.result_annulment", "İmtahan nəticələrinin ləğvi")
        ordering = ["-annulled_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["attempt"],
                condition=Q(restored_at__isnull=True),
                name="uniq_active_result_annulment_per_attempt",
            )
        ]

    def __str__(self):
        return f"annul #{self.pk} attempt={self.attempt_id} ({self.reason_key})"

    @property
    def is_active(self) -> bool:
        return self.restored_at is None


__all__ = ["ANNUL_DOCUMENT_EXTENSIONS", "ExamResultAnnulment", "annul_document_path"]
