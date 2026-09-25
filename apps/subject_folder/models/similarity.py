"""Plagiat (oxşarlıq) yoxlamasının saxlanan nəticələri.

``SubmissionFingerprint`` — bir cəhdin normallaşdırılmış mətni və MinHash
imzası. Ayrı cədvəldədir ki, siyahı sorğuları ağır mətn sütununu oxumasın.
``SimilarityMatch`` — iki cəhd arasında tapılmış oxşarlıq (cüt KANONİK
sıralanır: ``submission_a_id < submission_b_id``, cüt UNİKALDIR).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

from ..constants import MatchMethod, PlagiarismStatus
from .submission import Submission

_CTX = "subject_folder.model"


class SubmissionFingerprint(UUIDModel, TimeStampedModel):
    """Cəhdin mətn barmaq izi (normallaşdırılmış mətn + MinHash)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="subject_folder_fingerprints"
    )
    submission = models.OneToOneField(Submission, on_delete=models.CASCADE, related_name="fingerprint")
    status = models.CharField(max_length=16, choices=PlagiarismStatus.choices, default=PlagiarismStatus.PENDING)
    text = models.TextField(blank=True, default="", help_text="Normallaşdırılmış (kiçik hərf, işarəsiz) mətn.")
    text_sha256 = models.CharField(max_length=64, blank=True, default="", db_index=True)
    shingle_count = models.PositiveIntegerField(default=0)
    minhash = models.JSONField(default=list, blank=True)
    file_hashes = models.JSONField(default=list, blank=True, help_text="Faylların sha256 siyahısı.")
    extracted_chars = models.PositiveIntegerField(default=0)
    skipped_files = models.JSONField(default=list, blank=True, help_text="Mətni çıxarılmayan fayllar və səbəbi.")
    error = models.CharField(max_length=500, blank=True, default="")
    checked_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "göndəriş barmaq izi")
        verbose_name_plural = pgettext_lazy(_CTX, "göndəriş barmaq izləri")
        indexes = [models.Index(fields=["organization", "text_sha256"], name="sf_fp_org_text_sha")]

    def __str__(self):
        return f"{self.submission_id} · {self.status}"


class SimilarityMatch(UUIDModel, TimeStampedModel):
    """İki göndəriş arasında aşkarlanmış oxşarlıq."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="subject_folder_similarity_matches"
    )
    submission_a = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="similarity_as_a")
    submission_b = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="similarity_as_b")
    score = models.DecimalField(max_digits=4, decimal_places=3)
    method = models.CharField(max_length=16, choices=MatchMethod.choices)
    is_flagged = models.BooleanField(default=False, db_index=True)
    detail = models.JSONField(default=dict, blank=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)
    dismissed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    dismiss_note = models.CharField(max_length=500, blank=True, default="")

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "oxşarlıq uyğunluğu")
        verbose_name_plural = pgettext_lazy(_CTX, "oxşarlıq uyğunluqları")
        ordering = ["-score", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["submission_a", "submission_b"], name="sf_match_uniq_pair"),
            models.CheckConstraint(condition=Q(submission_a__lt=F("submission_b")), name="sf_match_canonical_pair"),
            models.CheckConstraint(condition=Q(score__gte=0) & Q(score__lte=1), name="sf_match_score_range"),
        ]
        # ``submission_b`` üzrə axtarışı FK-nın öz indeksi örtür (ayrıca indeks dublikat idi — 0004).
        indexes = [models.Index(fields=["organization", "is_flagged"], name="sf_match_org_flagged")]

    def __str__(self):
        return f"{self.submission_a_id} ~ {self.submission_b_id} ({self.score})"

    def other(self, submission_id):
        """Cütün «o biri» tərəfinin id-si."""
        return self.submission_b_id if str(self.submission_a_id) == str(submission_id) else self.submission_a_id


__all__ = ["SimilarityMatch", "SubmissionFingerprint"]
