"""İmtahan balının əl ilə daxil edilməsi — append-only sübut jurnalı.

SAHİBİN QƏRARI (2026-08): yazılı və praktiki imtahan KAĞIZ üzərində (praktikidə
kodda) keçir, sistemdən getmir. Balları sonradan İMTAHAN MƏRKƏZİ sistemə köçürür
(``final_score.entry`` icazəsi). Hər daxiletmə burada bir sətir kimi qalır:

* **İLK daxiletmə** sərbəstdir — sübut (imtahan vərəqinin şəkli/PDF-i + mətn
  qeydi) FAKULTATİVdir, çünki bu düzəliş deyil, ilkin köçürmədir;
* **SONRAKI DƏYİŞİKLİK** (artıq yazılmış balın dəyişdirilməsi) sahibin qaydası
  ilə TƏQDİMATLIDIR: səbəb + qeyd + SƏNƏD üçü də məcburi
  (``apps/registrar/corrections.py`` ilə eyni müqavilə).

Sətirlər ``ImmutableCorrectionEvidence``-dən miras alır: yaradıldıqdan sonra nə
dəyişdirilir, nə silinir — jurnal düzəlişi sənədləri ilə eyni zəmanət.

Servis qatı: ``apps/registrar/exam_score_entry.py``.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from core.upload_security import FileUploadValidator

from .corrections import CorrectionReason, ImmutableCorrectionEvidence

#: Sübut faylının ölçü limiti — jurnal düzəliş sənədləri ilə EYNİ (10 MB).
_MAX_EVIDENCE_MB = 10

#: İcazəli sübut uzantıları: imtahan vərəqinin foto/skanı + PDF.
#: (``corrections`` yalnız PDF qəbul edir; burada şəkil də lazımdır — sahibin
#: sözü: «onu əlavə edərkən ŞƏKİLDƏ əlavə etmək, TEXT və s. də olsun».)
EVIDENCE_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


def exam_score_evidence_path(instance, filename: str) -> str:
    """Qorunan media altında org-scoped saxlama yolu."""
    return f"exam_score_entries/{instance.organization_id}/{filename}"


class ExamScoreEntryKind(models.TextChoices):
    """Sətrin növü — ilkin köçürmə, yoxsa sonrakı sənədli düzəliş."""

    INITIAL = "initial", pgettext_lazy("registrar.exam_score_entry_kind", "Initial entry")
    CORRECTION = "correction", pgettext_lazy("registrar.exam_score_entry_kind", "Documented change")


class ExamScoreEntry(ImmutableCorrectionEvidence):
    """İmtahan balının bir daxiletməsi (köhnə → yeni, kim, nə vaxt, sübut).

    ENROLLMENT əsaslıdır — ``ExamAttempt`` obyektindən ASILI DEYİL: kağız
    imtahanda sistem daxilində cəhd yoxdur (spec E8)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="exam_score_entries"
    )
    enrollment = models.ForeignKey("registrar.Enrollment", on_delete=models.PROTECT, related_name="exam_score_entries")
    kind = models.CharField(max_length=12, choices=ExamScoreEntryKind.choices, default=ExamScoreEntryKind.INITIAL)
    old_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    new_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    reason = models.CharField(
        max_length=12,
        choices=CorrectionReason.choices,
        blank=True,
        help_text="Dəyişiklik səbəbi — yalnız sonrakı düzəlişdə məcburi.",
    )
    note = models.TextField(blank=True, help_text="Mətn qeydi (ilkin daxiletmədə opsional).")
    evidence = models.FileField(
        upload_to=exam_score_evidence_path,
        blank=True,
        validators=[FileUploadValidator(allowed_extensions=EVIDENCE_EXTENSIONS, max_size_mb=_MAX_EVIDENCE_MB)],
        help_text="İmtahan vərəqinin şəkli / PDF-i — ilkin daxiletmədə opsional, düzəlişdə məcburi.",
    )
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="exam_score_entries"
    )
    entered_by_name = models.CharField(max_length=200, editable=False)

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = pgettext_lazy("registrar.model.exam_score_entry.meta", "exam score entry")
        verbose_name_plural = pgettext_lazy("registrar.model.exam_score_entry.meta", "exam score entries")
        indexes = [
            models.Index(fields=["organization", "enrollment"]),
            models.Index(fields=["organization", "-created_at"]),
        ]

    def __str__(self):
        return f"exam-score-entry<{self.enrollment_id}> {self.old_score}→{self.new_score}"
