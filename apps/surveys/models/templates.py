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
