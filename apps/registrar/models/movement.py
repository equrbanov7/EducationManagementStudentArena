"""Tələbə hərəkəti reyestri — APPEND-ONLY əmr jurnalı (handoff ekran 09).

Nə üçün ayrı model?
-------------------
Köçürmə və akademik status dəyişikliyi ARTIQ işləyir
(``apps.registrar.transfer`` + ``apps.registrar.status``), amma izi yalnız
``audit_auditlog``-da qalırdı: orada ƏMR NÖMRƏSİ, əmr tarixi və sənəd sahəsi
yoxdur, sətir isə sərbəst mətndir. Tələbə şöbəsi üçün hərəkət RƏSMİ SƏNƏDDİR —
«hansı əmrlə köçürülüb?» sualı sorğu ilə cavablanmalıdır (handoff §5/09:
«Hər hərəkət: əmr nömrəsi, tarix, səbəb, icraçı ilə audit-ə yazılır»).

Müqavilələr
-----------
* **APPEND-ONLY.** ``ImmutableCorrectionEvidence``-dən miras alır (tətbiq
  qatının qapısı) + PG trigger (``0066`` migrasiyası) UPDATE/DELETE-i bloklayır.
  §8/5 «status dəyişikliyi silinmir — tarixçə yazısıdır».
* **Etiketlər DONDURULUR.** ``from_label`` / ``to_label`` yazıldığı andakı
  mətndir: qrup sonradan adını dəyişsə belə köhnə əmr öz mətnini saxlayır
  (akademik tarixçə səssizcə yenilənmir).
* **String-ref FK** (``"organizations.OrgUnit"``) — ``registrar``
  ``organizations``-ı statik import ETMİR (``scripts/module_deps.py``).
* Servis qatı: :mod:`apps.registrar.movements` (state maşını, validasiya).
"""

from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils.text import slugify
from django.utils.translation import pgettext_lazy

from core.ui import status_catalog
from core.upload_security import FileUploadValidator

from .corrections import ImmutableCorrectionEvidence

#: Əmr sənədinin ölçü limiti — jurnal düzəliş sənədləri ilə EYNİ (10 MB).
_MAX_DOCUMENT_MB = 10

#: İcazəli sənəd uzantıları: ərizə/arayış/protokol (skan və ya PDF).
MOVEMENT_DOCUMENT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}

#: Səbəbin minimum uzunluğu — handoff §8/6 («≥20 simvol»).
MOVEMENT_REASON_MIN_LENGTH = 20


def movement_document_path(instance, filename: str) -> str:
    """Qorunan media altında org-scoped saxlama yolu — ad TƏSADÜFİLƏŞİR.

    ⚠️ Ad qəsdən istifadəçidən GƏLMİR (audit 2026-09-03): «ərizə.pdf» kimi
    təxmin edilə bilən ad yolu praktikada açıq açara çevirirdi.  Prefiks
    ``core.media_policies``-də private-dır (icazə yoxlanılır), amma müdafiə
    ikiqat olmalıdır — Django ``upload_to``-nun qaytardığı adı olduğu kimi
    işlədir, ona görə random UUID burada verilir.
    """
    extension = ""
    _, _, tail = str(filename or "").rpartition(".")
    if tail and tail != str(filename or ""):
        extension = "." + slugify(tail)[:10]
    return f"student_movements/{instance.organization_id}/{uuid4().hex}{extension}"


class MovementKind(models.TextChoices):
    """6 hərəkət növü — etiketlər TƏK mənbədən (``core.ui.status_catalog``).

    Enum burada TƏKRAR YAZILMIR: kataloq həm badge-in, həm modelin, həm də
    filtr seçicisinin mənbəyidir — əks halda etiket üç yerdə sürüşərdi.
    """

    GROUP_TRANSFER = "group_transfer", status_catalog.label("student_movement", "group_transfer")
    PROGRAM_TRANSFER = "program_transfer", status_catalog.label("student_movement", "program_transfer")
    FORM_CHANGE = "form_change", status_catalog.label("student_movement", "form_change")
    ACADEMIC_LEAVE = "academic_leave", status_catalog.label("student_movement", "academic_leave")
    REINSTATEMENT = "reinstatement", status_catalog.label("student_movement", "reinstatement")
    EXPULSION = "expulsion", status_catalog.label("student_movement", "expulsion")


class StudentMovement(ImmutableCorrectionEvidence):
    """Bir akademik hərəkət əmri (yazıldıqdan sonra dəyişmir və silinmir)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="student_movements"
    )
    record = models.ForeignKey("registrar.StudentAcademicRecord", on_delete=models.PROTECT, related_name="movements")
    kind = models.CharField(max_length=24, choices=MovementKind.choices, db_index=True)

    # ── Rəsmi əsas ────────────────────────────────────────────────────────
    order_number = models.CharField(max_length=64, help_text="Rektor/dekanlıq əmrinin nömrəsi.")
    order_date = models.DateField(help_text="Əmrin tarixi.")
    reason = models.TextField(help_text="Əsaslandırma — ən azı 20 simvol (handoff §8/6).")
    document = models.FileField(
        upload_to=movement_document_path,
        blank=True,
        validators=[FileUploadValidator(allowed_extensions=MOVEMENT_DOCUMENT_EXTENSIONS, max_size_mb=_MAX_DOCUMENT_MB)],
        help_text="Ərizə / arayış / protokol — opsional.",
    )

    # ── Nədən → nəyə ──────────────────────────────────────────────────────
    from_group = models.ForeignKey(
        "organizations.OrgUnit", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    to_group = models.ForeignKey(
        "organizations.OrgUnit", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    from_program = models.ForeignKey(
        "registrar.Program", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    to_program = models.ForeignKey(
        "registrar.Program", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    from_status = models.CharField(max_length=20, blank=True, default="")
    to_status = models.CharField(max_length=20, blank=True, default="")
    #: Yazıldığı andakı insan-oxunaqlı mətn — SONRADAN DƏYİŞMİR.
    from_label = models.CharField(max_length=255, blank=True, default="")
    to_label = models.CharField(max_length=255, blank=True, default="")
    #: Akademik məzuniyyətin bitmə tarixi (handoff: «müddət tələb olunur»).
    effective_until = models.DateField(null=True, blank=True)

    # ── İcraçı ────────────────────────────────────────────────────────────
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="student_movements"
    )
    #: Aktorun adı yazıldığı anda dondurulur (hesab sonradan silinsə də qalır).
    actor_name = models.CharField(max_length=200, blank=True, default="")

    objects = models.Manager()

    class Meta:
        ordering = ["-order_date", "-created_at"]
        verbose_name = pgettext_lazy("registrar.model.student_movement.meta", "student movement")
        verbose_name_plural = pgettext_lazy("registrar.model.student_movement.meta", "student movements")
        indexes = [
            models.Index(fields=["organization", "-order_date"]),
            models.Index(fields=["organization", "record"]),
            models.Index(fields=["organization", "kind"]),
        ]

    def __str__(self):
        return f"{self.kind}<{self.record_id}> {self.order_number}"

    @property
    def kind_label(self):
        return status_catalog.label("student_movement", self.kind)


__all__ = [
    "MOVEMENT_DOCUMENT_EXTENSIONS",
    "MOVEMENT_REASON_MIN_LENGTH",
    "MovementKind",
    "StudentMovement",
    "movement_document_path",
]
