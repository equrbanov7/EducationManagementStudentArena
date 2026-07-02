"""Sual importu üçün asinxron mətn-çıxarma job modeli (P3, 2026-07-02).

OCR-lı PDF-lərin sinxron sorğuda parse olunması worker-i uzun müddət tutur
(nginx 900s timeout-un kökü). Bu model yüklənmiş faylı müvəqqəti saxlayır,
Celery task (`exams.run_text_extraction_job`) mətn çıxarıb nəticəni yazır,
frontend isə status endpointini poll edir. Fayl task bitən kimi silinir.

Tenant izolyasiyası: cədvəl RLS altındadır (organizations migration —
direct NULLABLE org pattern); əlavə olaraq view qatı yalnız job sahibinə
(user) icazə verir.
"""

import uuid

from django.conf import settings
from django.db import models


def extraction_job_upload_path(instance: "TextExtractionJob", filename: str) -> str:
    """Müvəqqəti çıxarma faylının saxlama yolu (il/ay bölgüsü ilə).

    Fayl adı view qatında ``randomize_uploaded_filename`` ilə təsadüfiləşir;
    orijinal ad ``source_name`` sahəsində saxlanır. ``created_at`` ilk save-də
    hələ boş olduğundan bölgü üçün cari vaxt işlədilir.
    """
    from django.utils import timezone

    return f"import_jobs/{timezone.now():%Y/%m}/{filename}"


class TextExtractionJob(models.Model):
    """Bir yüklənmiş faylın (txt/pdf/png/jpg) asinxron mətn çıxarması."""

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Gözləyir"),
        (STATUS_PROCESSING, "İcra olunur"),
        (STATUS_SUCCESS, "Hazır"),
        (STATUS_FAILED, "Xəta"),
    ]

    KIND_EXTRACT = "extract"
    KIND_AI_GENERATE = "ai_generate"
    KIND_EXPORT = "export"
    KIND_CHOICES = [
        (KIND_EXTRACT, "Mətn çıxarma"),
        (KIND_AI_GENERATE, "AI sual generasiyası"),
        (KIND_EXPORT, "Fayl exportu"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="text_extraction_jobs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="text_extraction_jobs",
    )
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default=KIND_EXTRACT)
    # AI generasiya üçün servis kwarg-ları (JSON-safe); extract üçün boş.
    payload = models.JSONField(default=dict, blank=True)
    # Nəticə metadatası (question_count, remaining, limit, ok...).
    result_meta = models.JSONField(default=dict, blank=True)
    source_name = models.CharField(max_length=255, blank=True, default="")
    file = models.FileField(upload_to=extraction_job_upload_path, blank=True, null=True)
    # Export job-larının nəticə faylı (docx/xlsx) — download endpointi verir.
    result_file = models.FileField(upload_to=extraction_job_upload_path, blank=True, null=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    text = models.TextField(blank=True, default="")
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "-created_at"], name="exams_extjob_user_created")]

    def __str__(self):
        return f"TextExtractionJob({self.pk}, {self.status}, {self.source_name})"
