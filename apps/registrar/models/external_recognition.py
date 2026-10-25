"""«Xarici nəticənin tanınması» — Erasmus+ / mübadilə / başqa ali məktəbdə keçilmiş fənn (sahib 2026-10-25).

Sahib: «Tələbə Erasmus-da və ya başqa universitetdə fənn keçmiş ola bilər — akademik nəticəni göstərə bilər və
o fəndən AZAD oluna».

Bir sətir = bir tanınma qərarı: xarici fənn (qurum, ölkə, ad, kredit, xarici qiymət) → bizim kurrikulumdakı fənn
+ semestr (``subject`` + ``period``, qərar anındakı jurnal qeydiyyatı ``enrollment``) və bizim 100 ballıq şkalada
qarşılığı (``recognized_score``). Əsas sənəd (transkript / Learning Agreement / əmr) MƏCBURİDİR.

* Azadlıq YENİ mexanizm deyil — «Fəndən azad et» qərar qatı (``JournalHygieneDecision``, kateqoriya
  ``subject_exempt``, səbəb kodu ``external_recognition``) işlədilir; ``exempt_decision`` ona bağlantıdır
  (jurnal bağlı / keçmiş dövrdədirsə boş qalır — transkriptdə tanınmış nəticə yenə qüvvədədir).
* APPEND-ONLY: sətir dəyişmir, silinmir; YALNIZ bir dəfə «Ləğv et» (``revoked_*`` sahələri + səbəb). DB
  qoruyucusu miqrasiya ``0099``-dadır (``0086`` naxışı).
* Eyni tələbə + fənn + semestr üçün qüvvədə olan (ləğv edilməmiş) tanınma yalnız BİRDİR.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

from .retake import _random_name, retake_file_validators

_CTX = "registrar.recognition"

#: Qorunan media prefiksi (``core.media_policies`` runtime reyestri, ``apps.registrar.apps``).
RECOGNITION_DOCUMENT_PREFIX = "credit_recognition_documents/"

#: Ləğv zamanı dəyişə bilən YEGANƏ sahələr (DB trigger-i ilə eyni siyahı).
REVOKE_FIELDS = ("revoked_at", "revoked_by", "revoked_by_name", "revoke_reason", "updated_at")


def recognition_document_path(instance, filename: str) -> str:
    """``credit_recognition_documents/<org>/<təsadüfi ad>`` — orijinal ad ``document_name`` sahəsindədir."""
    return f"{RECOGNITION_DOCUMENT_PREFIX}{instance.organization_id}/{_random_name(filename)}"


class RecognitionProgram(models.TextChoices):
    ERASMUS = "erasmus", pgettext_lazy(_CTX, "Erasmus+")
    EXCHANGE = "exchange", pgettext_lazy(_CTX, "Mübadilə proqramı")
    OTHER_UNIVERSITY = "other_university", pgettext_lazy(_CTX, "Başqa ali məktəb")
    OTHER = "other", pgettext_lazy(_CTX, "Digər")


class ExternalCreditRecognition(UUIDModel, TimeStampedModel):
    """Xarici akademik nəticənin bizim fənn üzrə tanınması (bir dəfə ləğv oluna bilir)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+", db_index=False
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="external_credit_recognitions"
    )
    #: Bizim kurrikulumdakı fənn + semestr — transkriptdə tanınmış sətir MƏHZ bu cütə düşür.
    subject = models.ForeignKey("registrar.Subject", on_delete=models.PROTECT, related_name="+")
    period = models.ForeignKey("organizations.AcademicPeriod", on_delete=models.PROTECT, related_name="+")
    #: Qərar anındakı jurnal qeydiyyatı (sonradan köçürülsə də iz qalır).
    enrollment = models.ForeignKey(
        "registrar.Enrollment", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    #: «Fəndən azad» qərarı — jurnal açıq idisə; bağlı / keçmiş dövrdə boşdur.
    exempt_decision = models.ForeignKey(
        "registrar.JournalHygieneDecision", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    program = models.CharField(max_length=24, choices=RecognitionProgram.choices)
    institution = models.CharField(max_length=255)
    country = models.CharField(max_length=100)
    foreign_subject = models.CharField(max_length=300)
    foreign_credit = models.DecimalField(max_digits=5, decimal_places=2)
    foreign_grade = models.CharField(max_length=32)
    #: Xarici təhsil dövrü (məs. «2025/2026 yaz semestri»).
    study_period = models.CharField(max_length=100)
    #: Bizim 100 ballıq şkalada qarşılığı (tam ədəd, keçid həddindən aşağı deyil — servis yoxlayır).
    recognized_score = models.PositiveSmallIntegerField()
    #: Transkriptdə yazılan kredit (bizim tədris planının krediti; qərar anında snapshot).
    credit = models.PositiveSmallIntegerField(default=0)
    note = models.TextField(blank=True)
    document = models.FileField(
        upload_to=recognition_document_path, max_length=200, validators=retake_file_validators()
    )
    document_name = models.CharField(max_length=255, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_by_name = models.CharField(max_length=200, blank=True, default="")

    # ── Ləğv (bir dəfə) ───────────────────────────────────────────────────────
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    revoked_by_name = models.CharField(max_length=200, blank=True, default="")
    revoke_reason = models.TextField(blank=True, default="")

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = pgettext_lazy("registrar.model.recognition.meta", "external credit recognition")
        verbose_name_plural = pgettext_lazy("registrar.model.recognition.meta", "external credit recognitions")
        indexes = [
            models.Index(fields=["organization", "-created_at"], name="reg_recog_org_created"),
            models.Index(fields=["organization", "student", "period"], name="reg_recog_student_period"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "student", "subject", "period"],
                condition=Q(revoked_at__isnull=True),
                name="reg_recog_one_active",
            ),
            models.CheckConstraint(
                condition=Q(recognized_score__gte=0, recognized_score__lte=100), name="reg_recog_score_range"
            ),
            models.CheckConstraint(condition=Q(foreign_credit__gt=0), name="reg_recog_foreign_credit_positive"),
            models.CheckConstraint(
                condition=Q(program__in=[choice.value for choice in RecognitionProgram]), name="reg_recog_program"
            ),
            # Ləğv ya tam yoxdur, ya da vaxtı + səbəbi ilə birlikdədir.
            models.CheckConstraint(
                condition=(
                    Q(revoked_at__isnull=True, revoke_reason="") | (Q(revoked_at__isnull=False) & ~Q(revoke_reason=""))
                ),
                name="reg_recog_revoke_complete",
            ),
        ]

    def __str__(self):
        return f"recognition<{self.student_id}:{self.subject_id}@{self.period_id}> {self.recognized_score}"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def save(self, *args, **kwargs):
        """Tətbiq qatının qapısı (PG trigger-i əsasdır): yeni sətir və ya yalnız bir dəfəlik ləğv sahələri."""
        if not self._state.adding:
            update_fields = kwargs.get("update_fields")
            if not update_fields or not set(update_fields) <= set(REVOKE_FIELDS):
                raise ValidationError("External credit recognitions are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("External credit recognitions cannot be deleted.")


__all__ = [
    "RECOGNITION_DOCUMENT_PREFIX",
    "REVOKE_FIELDS",
    "ExternalCreditRecognition",
    "RecognitionProgram",
    "recognition_document_path",
]
