"""Sorğu şablonu və sualları (tenant-səviyyəli, versiyalı).

Şablon kampaniyaya ``PROTECT`` ilə bağlanır: bir dəfə istifadə olunmuş sual
dəsti silinmir — keçmiş dövrlərin nəticələri öz sual mətnləri ilə qalır. Sual
dəsti dəyişəndə YENİ versiya yaradılır (bax ``services.templates``).

Sual mətni AZ mənbə mətnidir; ekranda ``pgettext("surveys.question", text)``
ilə göstərilir — defolt dəstin tərcümələri kataloqdan gəlir, tenantın öz
yazdığı mətn isə olduğu kimi qalır.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import pgettext, pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

from ..constants import QuestionKind, Section

_CTX = "surveys.model"


class SurveyTemplate(UUIDModel, TimeStampedModel):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="survey_templates"
    )
    name = models.CharField(max_length=200)
    version = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    #: Yeni kampaniyaların defolt şablonu (təşkilatda ən çoxu BİR).
    is_default = models.BooleanField(default=False)

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "sorğu şablonu")
        verbose_name_plural = pgettext_lazy(_CTX, "sorğu şablonları")
        ordering = ["-is_default", "name", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name", "version"], name="surveys_template_name_version_uniq"
            ),
            models.UniqueConstraint(
                fields=["organization"], condition=models.Q(is_default=True), name="surveys_template_one_default"
            ),
        ]

    def __str__(self):
        return f"{self.name} v{self.version}"


class SurveyPage(UUIDModel):
    """Sorğu qurucusu (2026-09-30): ümumi sorğunun BÖLMƏSİ (başlıq + izah, sıra).

    Müəllim qiymətləndirməsində bölmələr sabitdir (``SurveyQuestion.section`` — müəllim /
    ümumi); səhifə yalnız ümumi sorğularda işlənir.
    """

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="+")
    template = models.ForeignKey("SurveyTemplate", on_delete=models.CASCADE, related_name="pages")
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "sorğu bölməsi")
        verbose_name_plural = pgettext_lazy(_CTX, "sorğu bölmələri")
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.template_id}:page{self.order}"


class SurveyQuestion(UUIDModel):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="+")
    template = models.ForeignKey(SurveyTemplate, on_delete=models.CASCADE, related_name="questions")
    #: Ölçü açarı (məs. ``clarity``) — analitika sual mətnini deyil, bu açarı işlədir.
    code = models.SlugField(max_length=64)
    section = models.CharField(max_length=16, choices=Section.choices)
    kind = models.CharField(max_length=16, choices=QuestionKind.choices)
    text = models.TextField()
    help_text = models.CharField(max_length=300, blank=True)
    required = models.BooleanField(default=True)
    #: Likert indeksinə daxildir? (iş yükü / tövsiyə kimi nəticə göstəriciləri — yox).
    in_index = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)
    #: Sorğu qurucusu (2026-09-30): ümumi sorğunun bölməsi (müəllim qiymətləndirməsində boş).
    page = models.ForeignKey(SurveyPage, null=True, blank=True, on_delete=models.SET_NULL, related_name="questions")
    #: Növə görə parametrlər: ``choices`` [{"key", "label"}], ``labels`` (Likert 1–5),
    #: ``anchors`` (NPS 0/10), ``min``/``max`` (çox seçim). Bax ``services/questions.py``.
    options = models.JSONField(default=dict, blank=True)
    #: Kilidli (cavablanmış) sualın mətn düzəlişləri — ``[{"at", "by", "text", "help", "choices"}]``.
    history = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "sorğu sualı")
        verbose_name_plural = pgettext_lazy(_CTX, "sorğu sualları")
        ordering = ["order", "code"]
        constraints = [
            models.UniqueConstraint(fields=["template", "code"], name="surveys_question_code_uniq"),
        ]

    def __str__(self):
        return f"{self.template_id}:{self.code}"

    @property
    def display_text(self) -> str:
        return pgettext("surveys.question", self.text)

    @property
    def display_help_text(self) -> str:
        return pgettext("surveys.question", self.help_text) if self.help_text else ""

    @property
    def is_scored(self) -> bool:
        return self.kind in (QuestionKind.LIKERT5, QuestionKind.SCALE10)
