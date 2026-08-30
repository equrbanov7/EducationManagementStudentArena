"""Kafedra baxışının QƏRAR qeydi.

Hər qərar (təsdiq / düzəliş / rədd) bir ``SyllabusReview`` sətri yaradır; bölmə
şərhləri həmin sətrin ``section_comments`` xəritəsindədir ({section_id: mətn}).
Geri çağırma (müəllimin öz təqdimatını qaytarması) da burada saxlanılır ki,
tarixçə tam olsun.

⚠️ Bu cədvəl AUDİT JURNALI DEYİL — o mövcud ``audit_auditlog``-dur. Burada
qərarın DOMEN qeydi saxlanılır (kafedra paneli, tarixçə, bildiriş mətni).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

_CTX = "syllabus.model"


class ReviewDecision(models.TextChoices):
    """Baxış qeydinin növü."""

    SUBMITTED = "submitted", pgettext_lazy(_CTX, "Təsdiqə göndərildi")
    WITHDRAWN = "withdrawn", pgettext_lazy(_CTX, "Geri çağırıldı")
    OPENED = "opened", pgettext_lazy(_CTX, "Baxışa götürüldü")
    APPROVED = "approved", pgettext_lazy(_CTX, "Təsdiqləndi")
    REVISION = "revision", pgettext_lazy(_CTX, "Düzəliş üçün geri qaytarıldı")
    REJECTED = "rejected", pgettext_lazy(_CTX, "Rədd edildi")


#: Səbəbin MƏCBURİ olduğu qərarlar (README §3.1 və §3.3 dialoqları).
REASON_REQUIRED_DECISIONS = (
    ReviewDecision.WITHDRAWN.value,
    ReviewDecision.REVISION.value,
    ReviewDecision.REJECTED.value,
)


class SyllabusReview(UUIDModel, TimeStampedModel):
    """Bir versiyaya verilmiş bir qərar/baxış qeydi."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="syllabus_reviews"
    )
    version = models.ForeignKey("syllabus.SyllabusVersion", on_delete=models.CASCADE, related_name="reviews")
    decision = models.CharField(max_length=16, choices=ReviewDecision.choices, db_index=True)
    reason = models.TextField(
        blank=True,
        help_text="Geri çağırma / düzəliş / rədd səbəbi — bu üç qərar üçün MƏCBURİDİR (DB check).",
    )
    comment = models.TextField(blank=True, help_text="Ümumi şərh (səbəbdən ayrı, opsional).")
    section_comments = models.JSONField(
        default=dict,
        blank=True,
        help_text="Bölmə-bölmə şərhlər: {'week': 'saatlar uyğun deyil', …}.",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="syllabus_reviews",
        help_text="Qərarı verən şəxs (köçürmə qeydlərində NULL).",
    )

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "sillabus baxışı")
        verbose_name_plural = pgettext_lazy(_CTX, "sillabus baxışları")
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(decision__in=REASON_REQUIRED_DECISIONS) | ~Q(reason=""),
                name="syllabus_review_reason_required",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "version"]),
            models.Index(fields=["organization", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.version_id} · {self.decision}"
