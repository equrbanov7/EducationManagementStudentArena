"""``DocumentSeal`` — sistemin verdiyi rəsmi sənədin «möhürü» (sahib 2026-10-18).

Hər möhürlənmiş sənəd (bu gün: akademik transkript PDF-i) QR + qısa kod daşıyır; istənilən şəxs
``/yoxla/<kod>/`` açıb sənədin **etibarlı / ləğv edilmiş / tapılmayan** olduğunu görür.

Cədvəl **append-only**-dir (DB trigger ``verification_documentseal_guard``, miqrasiya ``0001``):

* DELETE qadağandır;
* yeganə icazəli UPDATE — **birdəfəlik ləğv** (``revoked_at`` NULL → dolu, ``revoked_by``, ``revoke_reason``);
  qalan bütün sütunlar dəyişməz qalmalıdır;
* hesab silinəndə Django-nun ``SET_NULL`` emulyasiyası istifadəçi FK-larını NULL edə bilər.

``payload`` — publik səhifədə göstərilən MİNİMAL faktlardır (sahibin adı maskalı, ixtisas, kredit/ÜOMG
yekunu). ``payload_sha256`` onun kanonik JSON-unun, ``file_sha256`` isə verilmiş faylın DƏQİQ baytlarının
həşidir (yükləyib-müqayisə üçün). RLS: standart ``organization_id`` tenant siyasəti; publik oxu yalnız
``lookup.find_by_code`` ilə (dar ``bypass_rls``).
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import pgettext_lazy

from .codes import CODE_MAX_LENGTH


class DocType(models.TextChoices):
    TRANSCRIPT = "transcript", pgettext_lazy("verification.doc_type", "Akademik transkript")
    #: «Təhsil aldığı yer haqqında arayış» (sahib 2026-10-19) — ``registrar.enrollment_certificate``.
    ENROLLMENT_CERTIFICATE = "enrollment_certificate", pgettext_lazy(
        "verification.doc_type", "Təhsil aldığı yer haqqında arayış"
    )


class DocumentSeal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="document_seals"
    )
    code = models.CharField(max_length=CODE_MAX_LENGTH, unique=True)
    doc_type = models.CharField(max_length=32, choices=DocType.choices)
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="document_seals",
    )
    title = models.CharField(max_length=200)
    issued_at = models.DateTimeField()
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    #: Sahibin struktur yolu (məs. tələbənin qrupu) — vahid əhatəli əməkdaş yalnız öz alt-ağacını görür.
    scope_path = models.CharField(max_length=1000, blank=True, default="")
    #: Sənədin dili — eyni məzmun fərqli dildə fərqli fayldır.
    language = models.CharField(max_length=8, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    payload_sha256 = models.CharField(max_length=64)
    file_sha256 = models.CharField(max_length=64, blank=True, default="")
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    revoke_reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-issued_at"]
        verbose_name = "document seal"
        verbose_name_plural = "document seals"
        indexes = [
            models.Index(fields=["organization", "-issued_at"], name="verif_seal_org_issued_idx"),
            models.Index(
                fields=["organization", "doc_type", "subject_user", "-issued_at"], name="verif_seal_subject_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(revoked_at__isnull=True, revoke_reason="")
                | (Q(revoked_at__isnull=False) & ~Q(revoke_reason="")),
                name="verif_seal_revocation_has_reason",
            ),
            models.CheckConstraint(condition=Q(payload_sha256__regex=r"^[0-9a-f]{64}$"), name="verif_seal_payload_hex"),
            models.CheckConstraint(
                condition=Q(file_sha256="") | Q(file_sha256__regex=r"^[0-9a-f]{64}$"), name="verif_seal_file_hex"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} · {self.get_doc_type_display()}"

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None


__all__ = ["DocType", "DocumentSeal"]
