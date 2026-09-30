"""Sorğu qurucusu (2026-09-30) — ümumi sorğunun iştirak qəbzi, cavabı, buferi, qaralaması.

ANONİMLİK MÜQAVİLƏSİ (``responses.py`` ilə eyni prinsip; dəyişdirməzdən əvvəl oxu):

* ``SurveyParticipation`` KİMİN doldurduğunu sübut edir («1 istifadəçi — 1 cavab» DB
  məhdudiyyəti), cavabın MƏZMUNU burada YOXDUR.
* ANONİM sorğuda ``SurveySubmission`` / ``SurveySubmissionAnswer`` şəxssizdir:
  ``respondent`` və ``submitted_at`` BOŞDUR (xidmət qatı yazmır, testlə sabitlənib), PK-lar
  təsadüfi UUID-dir, vaxt damğası yoxdur. Cavab əvvəl şəxssiz BUFERƏ
  (``SurveyPendingSubmission``) düşür və qəbzdən AYRI tranzaksiyada ≥ k partiya ilə,
  təsadüfi sıra ilə köçürülür (``services/survey_buffer.py``; Audit 2026-09-28 SV-3 qaydası).
  Server qaralaması (``SurveyDraft``) anonim sorğuda YAZILMIR — avtomatik saxlama brauzerin
  ``sessionStorage``-ındadır (tab bağlananda silinir).
* ŞƏXSLİ (anonim olmayan) sorğuda cavab birbaşa ``respondent`` + ``submitted_at`` ilə yazılır;
  şəxsləri yalnız ``survey.manage`` daşıyan idarəçi görür.
* ``SurveyGateSkip`` — «bir dəfə keç» izi (şəxsli, məzmunsuz).
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from .builder import Survey
from .templates import SurveyQuestion

_CTX = "surveys.model"


class SurveyParticipation(models.Model):
    """Tamamlanma sübutu — cavabın məzmunu YOXDUR."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="+")
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="participations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    completed_on = models.DateField()

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "sorğu iştirakı")
        verbose_name_plural = pgettext_lazy(_CTX, "sorğu iştirakları")
        constraints = [models.UniqueConstraint(fields=["survey", "user"], name="surveys_participation_once")]

    def __str__(self):
        return f"participation<{self.survey_id}>"


class SurveySubmission(models.Model):
    """Cavab — ANONİM sorğuda ``respondent``/``submitted_at`` QƏSDƏN boşdur."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="+")
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="submissions")
    respondent = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "sorğu cavabı (forma)")
        verbose_name_plural = pgettext_lazy(_CTX, "sorğu cavabları (forma)")
        # FK artıq indekslidir — ayrıca ``Index(fields=["survey"])`` dublikat olardı (test_w2_indexes).

    def __str__(self):
        return f"submission<{self.survey_id}>"


class SurveySubmissionAnswer(models.Model):
    """Bir sualın cavabı: ``number`` (Likert 1–5, NPS 0–10, bəli 1 / xeyr 0), ``choices``
    (seçim açarları), ``text`` (qısa/uzun mətn)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="+")
    submission = models.ForeignKey(SurveySubmission, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(SurveyQuestion, on_delete=models.PROTECT, related_name="+")
    number = models.SmallIntegerField(null=True, blank=True)
    choices = models.JSONField(default=list, blank=True)
    text = models.TextField(blank=True)

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "sual cavabı")
        verbose_name_plural = pgettext_lazy(_CTX, "sual cavabları")
        constraints = [
            models.UniqueConstraint(fields=["submission", "question"], name="surveys_subanswer_once"),
            models.CheckConstraint(
                condition=models.Q(number__isnull=True) | models.Q(number__gte=0, number__lte=10),
                name="surveys_subanswer_number_range",
            ),
        ]
        indexes = [models.Index(fields=["question", "number"], name="surveys_subanswer_q_number")]

    def __str__(self):
        return f"subanswer<{self.question_id}>"


class SurveyPendingSubmission(models.Model):
    """Anonim sorğunun dərc gözləyən cavabı (bufer) — şəxs, vaxt, qəbz bağı YOXDUR.

    ``payload = {"answers": [[question_id, number, choices, text], …]}``.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="+")
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="pending_submissions")
    payload = models.JSONField(default=dict)

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "dərc gözləyən sorğu cavabı")
        verbose_name_plural = pgettext_lazy(_CTX, "dərc gözləyən sorğu cavabları")

    def __str__(self):
        return f"pending-submission<{self.survey_id}>"


class SurveyDraft(models.Model):
    """ŞƏXSLİ sorğunun avtomatik saxlanan qaralaması (göndərişdə silinir)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="+")
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="drafts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    data = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "sorğu qaralaması")
        verbose_name_plural = pgettext_lazy(_CTX, "sorğu qaralamaları")
        constraints = [models.UniqueConstraint(fields=["survey", "user"], name="surveys_draft_once")]

    def __str__(self):
        return f"draft<{self.survey_id}>"


class SurveyGateSkip(models.Model):
    """«Bir dəfə keç» — istifadəçi məcburi sorğunu bir dəfə keçib (növbəti girişdə qapı sərtdir)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="+")
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="gate_skips")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    skipped_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "sorğu keçidi")
        verbose_name_plural = pgettext_lazy(_CTX, "sorğu keçidləri")
        constraints = [models.UniqueConstraint(fields=["survey", "user"], name="surveys_gate_skip_once")]

    def __str__(self):
        return f"skip<{self.survey_id}>"
