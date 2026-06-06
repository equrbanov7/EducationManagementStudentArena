"""
Çoxdilli imtahan dəstəyi — dil variantları.

Bir ``Exam`` konteyner kimi qalır; hər dil ayrıca ``ExamLanguageVariant``
kimi saxlanılır. Müəllim eyni imtahan altında müxtəlif dillərdə sual dəstləri
yükləyə bilər, student isə imtahana başlayarkən dil seçir və yalnız həmin dilin
sualları yüklənir.

Modellər ``apps.exams.models`` altında köhnə import-ları pozmamaq üçün shim
vasitəsilə də əlçatandır.
"""

from django.db import models
from django.utils.translation import pgettext_lazy

from apps.exams.constants import DEFAULT_EXAM_LANGUAGE, EXAM_LANGUAGE_CHOICES


class ExamLanguageVariant(models.Model):
    """Bir imtahanın konkret dildəki versiyası (məs. AZ / RU / EN)."""

    exam = models.ForeignKey(
        "exams.Exam",
        on_delete=models.CASCADE,
        related_name="language_variants",
        verbose_name=pgettext_lazy("exams.model.language_variant.field", "exam"),
    )
    language = models.CharField(
        max_length=10,
        choices=EXAM_LANGUAGE_CHOICES,
        default=DEFAULT_EXAM_LANGUAGE,
        verbose_name=pgettext_lazy("exams.model.language_variant.field", "language"),
    )
    display_name = models.CharField(
        max_length=120,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.language_variant.field", "display_name"),
        help_text=pgettext_lazy("exams.model.language_variant.help", "display_name"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=pgettext_lazy("exams.model.language_variant.field", "is_active"),
        help_text=pgettext_lazy("exams.model.language_variant.help", "is_active"),
    )
    # Bu dil üçün student-ə veriləcək sual sayı. Boşdursa, imtahanın ümumi
    # ``random_question_count`` dəyəri istifadə olunur.
    question_count_override = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.language_variant.field", "question_count_override"),
        help_text=pgettext_lazy("exams.model.language_variant.help", "question_count_override"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = pgettext_lazy("exams.model.language_variant.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.language_variant.meta", "plural")
        ordering = ["language", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "language"],
                name="exam_language_variant_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["exam", "is_active"], name="exam_lang_variant_active_idx"),
        ]

    def __str__(self):
        label = self.display_name or self.get_language_display()
        return f"{self.exam_id} · {label}"

    @property
    def effective_question_count(self):
        """Bu dil üçün veriləcək sual sayı (override → exam default)."""
        if self.question_count_override:
            return self.question_count_override
        return getattr(self.exam, "random_question_count", None)

    @property
    def question_count(self):
        """Bu dil variantına bağlı aktiv sualların sayı."""
        return self.questions.filter(is_active=True).count()


__all__ = [
    "ExamLanguageVariant",
]
