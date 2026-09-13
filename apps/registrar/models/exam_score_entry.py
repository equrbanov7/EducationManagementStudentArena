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
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel
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
    # 2026-09-12: sətir hansı köçürmə partiyasına (vərəqə) aiddir — opsional,
    # köhnə sətirlər üçün NULL. Partiya sənədi (skan) ``sheet.evidence``-dədir;
    # sətir-səviyyə ``evidence`` boş olsa da partiya sənədi düzəlişin sübutu
    # sayılır (servis: ``_require_justification``).
    sheet = models.ForeignKey(
        "registrar.ExamScoreSheet",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="entries",
        help_text="Köçürmə partiyası (vərəq/protokol) — varsa.",
    )

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

    def clean(self):
        """Tenant/əlaqə invariantları Python-da; PostgreSQL eyni qaydanı trigger-də təkrarlayır.

        2026-09-13, Codex audit P2-09: sətir ↔ qeydiyyat ↔ vərəq zənciri yalnız
        servis qatında qorunurdu. İndi üç qat var — bu ``clean()`` (adi axında
        xəta ``ValidationError`` kimi üzə çıxır), servis (``record_exam_score``)
        və ``0073`` migrasiyasının ``registrar_exam_score_entry_sheet_guard``
        trigger-i (xam SQL / ``QuerySet.update()`` üçün son sədd).
        """
        super().clean()
        errors = {}
        enrollment = self.enrollment if self.enrollment_id else None
        if enrollment is not None and self.organization_id and enrollment.organization_id != self.organization_id:
            errors["enrollment"] = "Qeydiyyat sətrin təşkilatına aid olmalıdır."
        if self.sheet_id:
            sheet = self.sheet
            if self.organization_id and sheet.organization_id != self.organization_id:
                errors["sheet"] = "Köçürmə vərəqi sətrin təşkilatına aid olmalıdır."
            elif enrollment is not None and sheet.offering_id != enrollment.offering_id:
                errors["sheet"] = "Köçürmə vərəqi qeydiyyatın açılışına aid olmalıdır."
        if errors:
            raise ValidationError(errors)


# ── Köçürmə vərəqi (batch) — 2026-09-12, sahibin tələbi ──────────────────────
#
# Sahib (2026-09-12): «yazılı imtahan verən tələbələrin imtahan ballarını
# sistemə köçürmək üçün panel olsun. Orada qrup seçilsin, müəllim, tarix və s.
# lazımlı nə info varsa; tələbələrin balları sistemə yüklənsin.»
#
# Mövcud modellərin heç birində KAĞIZ imtahanın tarixi/nəzarətçisi/protokol
# nömrəsi yoxdur (``CourseOffering``-də yalnız müəllim var; ``exams.Exam``
# rəqəmsal imtahandır və registrar onu statik import etmir). Bu metadata
# ``FinalGrade``-ə YOX, köçürmə PARTİYASINA aiddir: bir vərəq/protokol =
# bir batch. Ona görə kiçik ``ExamScoreSheet`` modeli yaradılır; hər
# ``ExamScoreEntry`` sətri (opsional) öz vərəqinə bağlanır.


class ExamScoreSheetSource(models.TextChoices):
    """Partiyanın mənbəyi — əl ilə siyahı forması, yoxsa fayl idxalı."""

    MANUAL = "manual", pgettext_lazy("registrar.exam_score_sheet_source", "Manual roster entry")
    IMPORT = "import", pgettext_lazy("registrar.exam_score_sheet_source", "File import (XLSX/CSV)")


#: Vərəq skanının media prefiksi. ``core.media_policies`` eyni prefiksi öz
#: checker cədvəlində LİTERAL kimi saxlayır (core registrar-ı import etmir) —
#: ikisi sinxron qalmalıdır. Org-prefiks invariantı (aşağıda ``clean()`` +
#: ``0073`` trigger-i) bu sabitə söykənir.
EXAM_SCORE_SHEET_MEDIA_PREFIX = "exam_score_sheets/"


def exam_score_sheet_evidence_prefix(organization_id) -> str:
    """``exam_score_sheets/<organization_id>/`` — vərəqin skanının icazəli kök yolu."""
    return f"{EXAM_SCORE_SHEET_MEDIA_PREFIX}{organization_id}/"


def exam_score_sheet_path(instance, filename: str) -> str:
    """Skan edilmiş protokol/vərəq — qorunan media altında org-scoped yol."""
    return f"{exam_score_sheet_evidence_prefix(instance.organization_id)}{filename}"


class ExamScoreSheet(UUIDModel, TimeStampedModel):
    """Bir köçürmə partiyası: açılış + imtahan metadatası + nəticə sayğacları.

    Sətirlərin özü (köhnə → yeni bal, kim, nə vaxt) ``ExamScoreEntry``-dədir;
    burada yalnız partiya-səviyyəli məlumat saxlanılır — imtahan tarixi,
    yoxlayan müəllim, nəzarətçi, protokol nömrəsi, skan (opsional) və
    «neçə sətir yazıldı / ötürüldü / rədd olundu» xülasəsi. Sayğaclar
    partiya bitəndə YENİLƏNİR, ona görə model append-only deyil (sətirlər
    isə append-only qalır).
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="exam_score_sheets"
    )
    offering = models.ForeignKey("registrar.CourseOffering", on_delete=models.PROTECT, related_name="exam_score_sheets")
    source = models.CharField(max_length=12, choices=ExamScoreSheetSource.choices, default=ExamScoreSheetSource.MANUAL)
    exam_date = models.DateField(null=True, blank=True, help_text="Kağız imtahanın keçirildiyi tarix.")
    examiner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="examined_score_sheets",
        help_text="Vərəqi yoxlayan müəllim (default: açılışın müəllimi).",
    )
    examiner_name = models.CharField(max_length=200, blank=True, help_text="Yoxlayan müəllimin adı (snapshot).")
    invigilator_name = models.CharField(max_length=200, blank=True, help_text="Nəzarətçi (sərbəst mətn).")
    protocol_number = models.CharField(max_length=64, blank=True, help_text="Protokol / vərəq nömrəsi.")
    note = models.TextField(blank=True, help_text="Partiya qeydi (opsional).")
    evidence = models.FileField(
        upload_to=exam_score_sheet_path,
        blank=True,
        validators=[FileUploadValidator(allowed_extensions=EVIDENCE_EXTENSIONS, max_size_mb=_MAX_EVIDENCE_MB)],
        help_text="Skan edilmiş protokol / vərəq (PDF və ya şəkil) — opsional.",
    )
    original_filename = models.CharField(max_length=255, blank=True, help_text="İdxal faylının adı (varsa).")
    rows_total = models.PositiveIntegerField(default=0)
    rows_written = models.PositiveIntegerField(default=0)
    rows_skipped = models.PositiveIntegerField(default=0)
    rows_failed = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="exam_score_sheets"
    )
    created_by_name = models.CharField(max_length=200, editable=False)

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = pgettext_lazy("registrar.model.exam_score_sheet.meta", "exam score sheet")
        verbose_name_plural = pgettext_lazy("registrar.model.exam_score_sheet.meta", "exam score sheets")
        indexes = [
            models.Index(fields=["organization", "offering", "-created_at"], name="reg_ess_org_off_created_idx"),
            models.Index(fields=["organization", "-created_at"], name="reg_ess_org_created_idx"),
        ]

    def __str__(self):
        return f"exam-score-sheet<{self.offering_id}> {self.source} {self.exam_date or '—'}"

    def clean(self):
        """Vərəq ↔ açılış tenant uyğunluğu və skanın org-prefiksi (Codex audit P2-09, 2026-09-13).

        PostgreSQL eyni iki qaydanı ``0073`` migrasiyasının
        ``registrar_exam_score_sheet_integrity_guard`` trigger-ində təkrarlayır;
        burada məqsəd adi axında xətanın ``ValidationError`` kimi trigger-dən
        ƏVVƏL görünməsidir. ``examiner``-in aktiv üzvlüyü QƏSDƏN burada deyil —
        üzvlüklər dəyişir, vərəq isə tarixi snapshot-dur (servis:
        ``exam_score_sheets.create_sheet``).
        """
        super().clean()
        errors = {}
        if self.offering_id and self.organization_id and self.offering.organization_id != self.organization_id:
            errors["offering"] = "Açılış vərəqin təşkilatına aid olmalıdır."
        # Yeni yüklənən fayl (``_committed`` = False) hələ ``upload_to``-dan
        # keçməyib — adı prefikssizdir; yol yalnız ``save()``-də qurulur. Yoxlama
        # artıq saxlanmış (və ya birbaşa sətir kimi verilmiş) ada aiddir.
        if (
            self.evidence
            and self.organization_id
            and getattr(self.evidence, "_committed", True)
            and not str(self.evidence.name).startswith(exam_score_sheet_evidence_prefix(self.organization_id))
        ):
            errors["evidence"] = "Skan faylı vərəqin öz təşkilat prefiksi altında olmalıdır."
        if errors:
            raise ValidationError(errors)
